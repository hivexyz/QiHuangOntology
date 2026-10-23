"""OWL / RDF ontology importer.

Uses RDFlib and Owlready2 to parse OWL/RDF ontology files and convert them into
the internal ``GuidelineOntologyBundle`` format consumable by the existing
import pipeline.

Supported formats:
- RDF/XML (``.owl``, ``.rdf``)
- Turtle (``.ttl``)
- JSON-LD (``.jsonld``)

The importer extracts:
- Class hierarchy (``SUBCLASS_OF`` relationships)
- Object properties (relationships between classes)
- Data properties (class attributes)

The results are converted to ``Entity`` nodes and ``SUBCLASS_OF`` relationships
in Neo4j, alongside the standard ``HAS_EFFECT``, ``CONTRAINDICATED_WITH``,
``PROHIBITED_IN_CONTEXT``, ``ALLOWED_IN_CONTEXT``, ``NOT_FOR_POPULATION``
relationships where applicable.

MVP scope (v2.0):
- RDF/XML, Turtle, JSON-LD parsing
- Class hierarchy extraction
- Object property extraction
- Data property extraction

Out of scope (v2.1+):
- OWL Restriction reasoning (someValuesFrom, allValuesFrom)
- HermiT/Pellet reasoner integration
- SPARQL query endpoint
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Lazy imports to avoid hard dependency on optional packages
_RDFLIB_AVAILABLE = False
_OWLREADY2_AVAILABLE = False

try:
    import rdflib  # noqa: F401

    _RDFLIB_AVAILABLE = True
except ImportError:
    pass

try:
    import owlready2  # noqa: F401

    _OWLREADY2_AVAILABLE = True
except ImportError:
    pass


@dataclass(slots=True)
class OwlClass:
    """Represents a parsed OWL class."""

    name: str
    iri: str
    label: str | None = None
    comment: str | None = None
    superclasses: list[str] = field(default_factory=list)  # parent class IRIs
    subclasses: list[str] = field(default_factory=list)  # child class IRIs
    object_properties: list[OwlProperty] = field(default_factory=list)
    data_properties: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class OwlProperty:
    """Represents an OWL object property relationship."""

    name: str
    iri: str
    domain_class_iri: str
    range_class_iri: str | None = None


@dataclass(slots=True)
class OwlParseResult:
    """Result of parsing an OWL/RDF ontology file."""

    classes: list[OwlClass] = field(default_factory=list)
    properties: list[OwlProperty] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    format: str = ""


class OwlOntologyImporter:
    """Parse OWL/RDF ontology files and convert to internal ontology format.

    Supports RDF/XML, Turtle, and JSON-LD via RDFlib. Optionally uses Owlready2
    for enhanced OWL 2.0 parsing including class hierarchy and restrictions.
    """

    # OWL/RDF namespace URIs
    RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    RDFS_SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
    RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
    RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
    OWL_CLASS = "http://www.w3.org/2002/07/owl#Class"
    OWL_OBJECT_PROPERTY = "http://www.w3.org/2002/07/owl#ObjectProperty"
    OWL_DATATYPE_PROPERTY = "http://www.w3.org/2002/07/owl#DatatypeProperty"
    OWL_RESTRICTION = "http://www.w3.org/2002/07/owl#Restriction"
    OWL_ON_PROPERTY = "http://www.w3.org/2002/07/owl#onProperty"
    OWL_SOME_VALUES_FROM = "http://www.w3.org/2002/07/owl#someValuesFrom"
    OWL_ALL_VALUES_FROM = "http://www.w3.org/2002/07/owl#allValuesFrom"

    # Format mapping
    _FORMAT_MAP = {
        "owl": "xml",
        "rdf": "xml",
        "ttl": "turtle",
        "turtle": "turtle",
        "jsonld": "json-ld",
        "json-ld": "json-ld",
    }

    def __init__(self) -> None:
        if not _RDFLIB_AVAILABLE:
            logger.warning(
                "RDFlib is not installed. OWL/RDF import will not be available. "
                "Install with: uv sync --extra dev  (adding rdflib to dependencies)"
            )

    def parse_owl_content(
        self,
        content: bytes,
        source_type: str,
        file_name: str = "",
    ) -> OwlParseResult:
        """Parse OWL/RDF content from bytes.

        Args:
            content: Raw file content bytes.
            source_type: Format hint (``owl``, ``rdf``, ``ttl``, ``jsonld``).
            file_name: Optional file name for format detection.

        Returns:
            An OwlParseResult with parsed classes and properties.
        """
        suffix = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
        fmt = self._resolve_format(source_type, suffix)

        result = OwlParseResult(format=fmt)

        if not _RDFLIB_AVAILABLE:
            result.warnings.append("RDFlib is not installed; OWL import skipped.")
            return result

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="ignore")
            result.warnings.append("File was not valid UTF-8; decoded with substitutions.")

        # Try Owlready2 first for richer parsing
        if _OWLREADY2_AVAILABLE and fmt == "xml":
            try:
                return self._parse_with_owlready2(text, result)
            except Exception as exc:
                result.warnings.append(f"Owlready2 parsing failed, falling back to RDFlib: {exc}")

        # Fallback: RDFlib basic parsing
        try:
            return self._parse_with_rdflib(text, fmt, result)
        except Exception as exc:
            result.warnings.append(f"RDFlib parsing failed: {exc}")
            return result

    def parse_owl_file(self, content: bytes, fmt: str = "xml") -> OwlParseResult:
        """Convenience wrapper for parse_owl_content."""
        return self.parse_owl_content(content, fmt)

    def to_ontology_bundle(
        self,
        result: OwlParseResult,
        kb_version: str,
        guide_title: str = "",
    ) -> Any:
        """Convert OwlParseResult to GuidelineOntologyBundle.

        This creates Entity nodes for each OWL class and SUBCLASS_OF relationships
        in Neo4j. Class labels become standard_names, and object properties become
        relationship edges.

        Args:
            result: The parsed OWL result.
            kb_version: The knowledge base version string.
            guide_title: Optional title for the imported ontology.

        Returns:
            A GuidelineOntologyBundle compatible with the existing import pipeline.
        """
        from .guideline_import import GuidelineOntologyBundle, GuidelineOntologyExtractor

        extractor = GuidelineOntologyExtractor()

        if not result.classes:
            return GuidelineOntologyBundle(
                ontology_entities={},
                knowledge_cards={},
                ontology_assertions={},
                evidence_sources={},
                concept_aliases={},
                guideline_documents={},
                mentions={},
                normalization_decisions={},
                warnings=[*result.warnings, "No OWL classes found in the ontology file."],
                extracted_materials=[],
                relationship_count=0,
                extractor_engine="owl_import",
            )

        ontology_entities: dict[str, dict[str, Any]] = {}
        knowledge_cards: dict[str, dict[str, Any]] = {}
        ontology_assertions: dict[str, dict[str, Any]] = {}
        evidence_sources: dict[str, dict[str, Any]] = {}
        concept_aliases: dict[str, dict[str, Any]] = {}
        guideline_documents: dict[str, dict[str, Any]] = {}
        relationship_count = 0
        iri_to_entity_id: dict[str, str] = {}
        document_id = f"guide_{hashlib.md5(((guide_title or 'OWL Import') + kb_version).encode('utf-8')).hexdigest()[:16]}"
        guideline_documents[document_id] = {
            "document_id": document_id,
            "kb_version": kb_version,
            "source_uri": guide_title or "OWL Import",
            "title": guide_title or "OWL Import",
            "source_type": "owl_import",
            "status": "draft",
        }

        # Map entity types from OWL to our internal labels
        for owl_class in result.classes:
            entity_id = self._owl_entity_id(owl_class.iri)
            iri_to_entity_id[owl_class.iri] = entity_id

            standard_name = owl_class.label or owl_class.name or self._iri_local_name(owl_class.iri)
            entity_label, class_warning = self._map_owl_class_to_entity_label(owl_class)
            if class_warning:
                result.warnings.append(class_warning)

            ontology_entities[entity_id] = {
                "entity_id": entity_id,
                "label": entity_label,
                "standard_name": standard_name,
                "aliases": [],
                "kb_version": kb_version,
                "attributes": {
                    "source_type": "owl",
                    "source_iri": owl_class.iri,
                    "owl_comment": owl_class.comment or "",
                    "guide_title": guide_title or "OWL Import",
                    "owl_superclasses": list(owl_class.superclasses),
                    "semantic_type": entity_label.lower(),
                },
            }

            # Build knowledge card
            card_effects: list[str] = []
            card_populations: list[str] = []
            card_allowed: list[str] = []
            card_prohibited: list[str] = []
            contra_targets: list[dict[str, str]] = []

            for prop in owl_class.object_properties:
                range_name = self._iri_local_name(prop.range_class_iri) if prop.range_class_iri else ""
                prop_name = prop.name or self._iri_local_name(prop.iri)

                # Map OWL properties to our internal relationships
                relation, property_warning = self._map_owl_property_to_relation(prop_name.lower())
                if property_warning:
                    result.warnings.append(property_warning)
                    continue
                if relation == "HAS_EFFECT" and range_name:
                    card_effects.append(range_name)
                elif relation == "NOT_FOR_POPULATION" and range_name:
                    card_populations.append(range_name)
                elif relation == "ALLOWED_IN_CONTEXT" and range_name:
                    card_allowed.append(range_name)
                elif relation == "PROHIBITED_IN_CONTEXT" and range_name:
                    card_prohibited.append(range_name)
                elif relation == "CONTRAINDICATED_WITH":
                    contra_targets.append({
                        "target_entity_id": self._owl_entity_id(prop.range_class_iri or ""),
                        "target_name": range_name,
                        "relation": "CONTRAINDICATED_WITH",
                    })

            # Count relationships
            relationship_count += len(card_effects)
            relationship_count += len(card_populations)
            relationship_count += len(card_allowed)
            relationship_count += len(card_prohibited)
            relationship_count += len(contra_targets)

            # Count SUBCLASS_OF relationships
            relationship_count += len(owl_class.superclasses)

            knowledge_cards[entity_id] = {
                "entity": {
                    "entity_id": entity_id,
                    "standard_name": standard_name,
                    "label": entity_label,
                    "risk_level": "medium",
                },
                "aliases": [],
                "effects": card_effects,
                "not_for_populations": card_populations,
                "allowed_contexts": card_allowed,
                "prohibited_contexts": card_prohibited,
                "contraindications": contra_targets,
                "kb_version": kb_version,
                "source_guide": guide_title or "OWL Import",
                "evidence": [f"OWL class: {owl_class.iri}"],
                "owl_superclasses": owl_class.superclasses,
                "owl_subclasses": owl_class.subclasses,
                "assertion_count": 0,
                "evidence_count": 1,
                "derived_from_assertions": True,
            }

            evidence_id = f"evidence_{hashlib.md5((entity_id + kb_version).encode('utf-8')).hexdigest()[:16]}"
            evidence_sources[evidence_id] = {
                "evidence_id": evidence_id,
                "kb_version": kb_version,
                "source_type": "owl_class",
                "source_uri": owl_class.iri,
                "source_title": guide_title or "OWL Import",
                "source_text": f"OWL class: {owl_class.iri}",
                "entity_id": entity_id,
                "status": "draft",
                "document_id": document_id,
            }

            for superclass_iri in owl_class.superclasses:
                if self._is_generic_superclass(superclass_iri):
                    continue
                parent_id = self._owl_entity_id(superclass_iri)
                parent_name = self._iri_local_name(superclass_iri)
                assertion_id = f"assert_{hashlib.md5((entity_id + 'SUBCLASS_OF' + parent_id + kb_version).encode('utf-8')).hexdigest()[:16]}"
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": entity_id,
                    "predicate_type": "SUBCLASS_OF",
                    "object_entity_id": parent_id,
                    "object_value": parent_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title or "OWL Import",
                    "evidence_ids": [evidence_id],
                    "document_id": document_id,
                }

            for effect_name in card_effects:
                assertion_id = f"assert_{hashlib.md5((entity_id + 'HAS_EFFECT' + effect_name + kb_version).encode('utf-8')).hexdigest()[:16]}"
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": entity_id,
                    "predicate_type": "HAS_EFFECT",
                    "object_entity_id": None,
                    "object_value": effect_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title or "OWL Import",
                    "evidence_ids": [evidence_id],
                    "document_id": document_id,
                }
            for population_name in card_populations:
                assertion_id = f"assert_{hashlib.md5((entity_id + 'NOT_FOR_POPULATION' + population_name + kb_version).encode('utf-8')).hexdigest()[:16]}"
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": entity_id,
                    "predicate_type": "NOT_FOR_POPULATION",
                    "object_entity_id": None,
                    "object_value": population_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title or "OWL Import",
                    "evidence_ids": [evidence_id],
                    "document_id": document_id,
                }
            for context_name in card_allowed:
                assertion_id = f"assert_{hashlib.md5((entity_id + 'ALLOWED_IN_CONTEXT' + context_name + kb_version).encode('utf-8')).hexdigest()[:16]}"
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": entity_id,
                    "predicate_type": "ALLOWED_IN_CONTEXT",
                    "object_entity_id": None,
                    "object_value": context_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title or "OWL Import",
                    "evidence_ids": [evidence_id],
                    "document_id": document_id,
                }
            for context_name in card_prohibited:
                assertion_id = f"assert_{hashlib.md5((entity_id + 'PROHIBITED_IN_CONTEXT' + context_name + kb_version).encode('utf-8')).hexdigest()[:16]}"
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": entity_id,
                    "predicate_type": "PROHIBITED_IN_CONTEXT",
                    "object_entity_id": None,
                    "object_value": context_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title or "OWL Import",
                    "evidence_ids": [evidence_id],
                    "document_id": document_id,
                }
            for contra in contra_targets:
                target_id = contra.get("target_entity_id")
                target_name = contra.get("target_name", "")
                assertion_id = f"assert_{hashlib.md5((entity_id + 'CONTRAINDICATED_WITH' + (target_id or target_name) + kb_version).encode('utf-8')).hexdigest()[:16]}"
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": entity_id,
                    "predicate_type": "CONTRAINDICATED_WITH",
                    "object_entity_id": target_id,
                    "object_value": target_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title or "OWL Import",
                    "evidence_ids": [evidence_id],
                    "document_id": document_id,
                }
            knowledge_cards[entity_id]["assertion_count"] = sum(
                1 for item in ontology_assertions.values() if item["subject_entity_id"] == entity_id
            )

        return GuidelineOntologyBundle(
            ontology_entities=ontology_entities,
            knowledge_cards=knowledge_cards,
            ontology_assertions=ontology_assertions,
            evidence_sources=evidence_sources,
            concept_aliases=concept_aliases,
            guideline_documents=guideline_documents,
            mentions={},
            normalization_decisions={},
            warnings=result.warnings,
            extracted_materials=[e["standard_name"] for e in ontology_entities.values()],
            relationship_count=relationship_count,
            extractor_engine="owl_import",
            extractor_model=f"owl:{result.format}",
        )

    # ------------------------------------------------------------------
    # Owlready2 parsing
    # ------------------------------------------------------------------

    def _parse_with_owlready2(self, text: str, result: OwlParseResult) -> OwlParseResult:
        """Parse OWL using Owlready2 for richer class hierarchy extraction."""
        import tempfile
        from pathlib import Path

        # Owlready2 works with file paths, not strings
        with tempfile.NamedTemporaryFile(suffix=".owl", mode="w", delete=False, encoding="utf-8") as f:
            f.write(text)
            tmp_path = f.name

        try:
            from owlready2 import get_ontology, default_world

            onto = get_ontology(f"file://{tmp_path}").load()

            classes: list[OwlClass] = []
            iri_set: set[str] = set()
            iri_to_class: dict[str, OwlClass] = {}

            for owl_class in onto.classes():
                iri = owl_class.iri or ""
                if not iri or iri in iri_set:
                    continue
                iri_set.add(iri)

                name = owl_class.name or self._iri_local_name(iri)
                label = self._get_owlready2_label(owl_class)
                comment = self._get_owlready2_comment(owl_class)

                # Get superclasses
                superclass_iris: list[str] = []
                try:
                    for parent in owl_class.is_a:
                        if hasattr(parent, "iri") and parent.iri:
                            superclass_iris.append(parent.iri)
                except Exception:
                    pass

                owl_item = OwlClass(
                    name=name,
                    iri=iri,
                    label=label,
                    comment=comment,
                    superclasses=superclass_iris,
                )
                classes.append(owl_item)
                iri_to_class[iri] = owl_item

            # Owlready2 exposes object properties on the ontology more reliably
            # than on individual classes for lightweight OWL files.
            try:
                for prop in onto.object_properties():
                    prop_iri = prop.iri if hasattr(prop, "iri") else ""
                    prop_name = prop.name if hasattr(prop, "name") else self._iri_local_name(prop_iri)
                    domains = list(prop.domain) if hasattr(prop, "domain") and prop.domain else []
                    ranges = list(prop.range) if hasattr(prop, "range") and prop.range else []
                    range_iri = next(
                        (
                            item.iri
                            for item in ranges
                            if hasattr(item, "iri") and item.iri
                        ),
                        None,
                    )
                    for domain in domains:
                        domain_iri = domain.iri if hasattr(domain, "iri") else None
                        if not domain_iri:
                            continue
                        owl_item = iri_to_class.get(domain_iri)
                        if owl_item is None:
                            continue
                        owl_item.object_properties.append(
                            OwlProperty(
                                name=prop_name,
                                iri=prop_iri,
                                domain_class_iri=domain_iri,
                                range_class_iri=range_iri,
                            )
                        )
            except Exception:
                pass

            result.classes = classes
            result.warnings.append("Parsed with Owlready2 (OWL 2.0 support).")

        except Exception as exc:
            result.warnings.append(f"Owlready2 parsing error: {exc}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return result

    # ------------------------------------------------------------------
    # RDFlib fallback parsing
    # ------------------------------------------------------------------

    def _parse_with_rdflib(self, text: str, fmt: str, result: OwlParseResult) -> OwlParseResult:
        """Parse OWL/RDF using RDFlib as fallback."""
        from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal

        g = Graph()
        try:
            g.parse(data=text, format=fmt)
        except Exception as exc:
            result.warnings.append(f"RDFlib parse error: {exc}")
            return result

        # Collect all OWL classes
        classes: list[OwlClass] = []
        iri_to_class: dict[str, OwlClass] = {}
        iri_set: set[str] = set()

        for cls_ref in g.subjects(RDF.type, OWL.Class):
            cls_iri = str(cls_ref)
            if cls_iri in iri_set:
                continue
            iri_set.add(cls_iri)

            name = self._iri_local_name(cls_iri)
            label = self._get_rdf_label(g, cls_ref)
            comment = self._get_rdf_comment(g, cls_ref)

            owl_cls = OwlClass(name=name, iri=cls_iri, label=label, comment=comment)
            classes.append(owl_cls)
            iri_to_class[cls_iri] = owl_cls

        # Collect superclass relationships
        for cls_ref in g.subjects(RDF.type, OWL.Class):
            cls_iri = str(cls_ref)
            owl_cls = iri_to_class.get(cls_iri)
            if owl_cls is None:
                continue

            for parent_ref in g.objects(cls_ref, RDFS.subClassOf):
                parent_iri = str(parent_ref)
                if parent_iri != cls_iri:
                    owl_cls.superclasses.append(parent_iri)
                    # Add reverse relationship
                    parent_cls = iri_to_class.get(parent_iri)
                    if parent_cls is not None:
                        parent_cls.subclasses.append(cls_iri)

        # Collect object properties
        prop_map: dict[str, list[OwlProperty]] = {}
        for prop_ref in g.subjects(RDF.type, OWL.ObjectProperty):
            prop_iri = str(prop_ref)
            prop_name = self._iri_local_name(prop_iri)

            for domain_ref in g.objects(prop_ref, RDFS.domain):
                domain_iri = str(domain_ref)
                range_iri = None
                for range_ref in g.objects(prop_ref, RDFS.range):
                    range_iri = str(range_ref)
                    break

                prop = OwlProperty(
                    name=prop_name,
                    iri=prop_iri,
                    domain_class_iri=domain_iri,
                    range_class_iri=range_iri,
                )
                prop_map.setdefault(domain_iri, []).append(prop)

        # Assign properties to classes
        for cls_iri, props in prop_map.items():
            owl_cls = iri_to_class.get(cls_iri)
            if owl_cls is not None:
                owl_cls.object_properties.extend(props)

        result.classes = classes
        result.warnings.append(f"Parsed {len(classes)} classes with RDFlib.")
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_format(self, source_type: str, suffix: str) -> str:
        """Resolve the RDFlib format string from source type and file suffix."""
        normalized = source_type.lower().strip()
        if normalized in self._FORMAT_MAP:
            return self._FORMAT_MAP[normalized]
        if suffix in self._FORMAT_MAP:
            return self._FORMAT_MAP[suffix]
        return "xml"  # Default to RDF/XML

    def _iri_local_name(self, iri: str) -> str:
        """Extract the local name from an IRI (the part after # or /)."""
        if "#" in iri:
            return iri.rsplit("#", 1)[-1]
        return iri.rsplit("/", 1)[-1]

    def _owl_entity_id(self, iri: str) -> str:
        """Generate a deterministic entity_id from an IRI."""
        digest = hashlib.sha1(iri.encode("utf-8")).hexdigest()[:10]
        return f"owl_{digest}"

    def _get_rdf_label(self, g: Any, subject: Any) -> str | None:
        """Get rdfs:label from an RDF subject."""
        from rdflib import RDFS
        for label in g.objects(subject, RDFS.label):
            return str(label)
        return None

    def _get_rdf_comment(self, g: Any, subject: Any) -> str | None:
        """Get rdfs:comment from an RDF subject."""
        from rdflib import RDFS
        for comment in g.objects(subject, RDFS.comment):
            return str(comment)
        return None

    @staticmethod
    def _get_owlready2_label(owl_class: Any) -> str | None:
        """Get rdfs:label from an Owlready2 class."""
        try:
            lbl = owl_class.label
            if lbl:
                return lbl.first() if hasattr(lbl, "first") else str(lbl)
        except Exception:
            pass
        return None

    @staticmethod
    def _get_owlready2_comment(owl_class: Any) -> str | None:
        """Get rdfs:comment from an Owlready2 class."""
        try:
            cmt = owl_class.comment
            if cmt:
                return cmt.first() if hasattr(cmt, "first") else str(cmt)
        except Exception:
            pass
        return None

    @staticmethod
    def _map_owl_property_to_relation(prop_name: str) -> tuple[str | None, str | None]:
        """Map OWL property names to internal relationship types."""
        normalized = prop_name.replace(" ", "").lower()
        mapping = {
            "haseffect": "HAS_EFFECT",
            "has_effect": "HAS_EFFECT",
            "treats": "HAS_EFFECT",
            "treat": "HAS_EFFECT",
            "contraindicatedwith": "CONTRAINDICATED_WITH",
            "contraindicated_with": "CONTRAINDICATED_WITH",
            "notforpopulation": "NOT_FOR_POPULATION",
            "not_for_population": "NOT_FOR_POPULATION",
            "allowedincontext": "ALLOWED_IN_CONTEXT",
            "allowed_in_context": "ALLOWED_IN_CONTEXT",
            "prohibitedincontext": "PROHIBITED_IN_CONTEXT",
            "prohibited_in_context": "PROHIBITED_IN_CONTEXT",
        }
        relation = mapping.get(normalized)
        if relation is not None:
            return relation, None
        return None, f"Unresolved OWL property mapping: {prop_name}"

    @staticmethod
    def _map_owl_class_to_entity_label(owl_class: OwlClass) -> tuple[str, str | None]:
        superclass_tokens = [item.rsplit("#", 1)[-1].rsplit("/", 1)[-1].lower() for item in (owl_class.superclasses or [])]
        text = " ".join(
            [
                (owl_class.name or "").lower(),
                (owl_class.label or "").lower(),
                *superclass_tokens,
            ]
        )
        if any(token in text for token in ("formula", "decoction", "方", "汤")):
            return "Formula", None
        if any(token in text for token in ("population", "pregnant", "child", "人群")):
            return "Population", None
        if any(token in text for token in ("context", "scenario", "场景")):
            return "Context", None
        if any(token in text for token in ("effect", "功效")):
            return "Effect", None
        if any(token in text for token in ("herb", "materia", "药材")):
            return "Herb", None
        class_name = owl_class.label or owl_class.name or owl_class.iri
        return "Concept", f"Unresolved OWL class mapping: {class_name}"

    @staticmethod
    def _is_generic_superclass(superclass_iri: str) -> bool:
        value = (superclass_iri or "").lower()
        return value.endswith("#thing") or value.endswith("/thing")
