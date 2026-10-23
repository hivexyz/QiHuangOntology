from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from ..config import Settings
from ..exceptions import APIError
from ..store import InMemoryStore


@dataclass(slots=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    dimension: int


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_ready(self) -> bool:
        return self._settings.embedding_ready

    def embed_text(self, text: str) -> EmbeddingResult:
        cleaned = (text or "").strip()
        if not cleaned:
            raise APIError(status_code=400, code="invalid_request", message="text is required")
        if not self.is_ready():
            raise APIError(status_code=503, code="embedding_unavailable", message="Embedding service is not configured")

        payload = {
            "model": self._settings.openai_embedding_model,
            "input": cleaned,
        }
        url = self._settings.openai_embedding_base_url.rstrip("/") + "/embeddings"
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.openai_api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            raise APIError(status_code=502, code="embedding_http_error", message=f"Embedding HTTP {exc.code}: {detail[:200]}") from exc
        except URLError as exc:
            raise APIError(status_code=502, code="embedding_connection_error", message=f"Embedding connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise APIError(status_code=504, code="embedding_timeout", message="Embedding request timed out") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise APIError(status_code=502, code="embedding_invalid_response", message="Embedding response is not valid JSON") from exc

        data = parsed.get("data") or []
        if not isinstance(data, list) or not data:
            raise APIError(status_code=502, code="embedding_invalid_response", message="Embedding response missing data")
        embedding = data[0].get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise APIError(status_code=502, code="embedding_invalid_response", message="Embedding vector missing")
        vector = [float(v) for v in embedding]
        return EmbeddingResult(
            vector=vector,
            model=str(parsed.get("model") or self._settings.openai_embedding_model),
            dimension=len(vector),
        )


class VectorStoreService:
    def __init__(self, settings: Settings, store: InMemoryStore) -> None:
        self._settings = settings
        self._store = store
        self._memory_vectors: dict[str, dict[str, Any]] = {}
        self._milvus_client = None

    def is_ready(self) -> bool:
        return self._settings.milvus_ready

    def upsert_document(self, *, doc_id: str, text: str, vector: list[float], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not doc_id:
            raise APIError(status_code=400, code="invalid_request", message="doc_id is required")
        if not vector:
            raise APIError(status_code=400, code="invalid_request", message="vector is required")

        record = {
            "doc_id": doc_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {},
            "dimension": len(vector),
            "backend": "memory",
        }
        self._memory_vectors[doc_id] = record

        if self.is_ready():
            try:
                self._ensure_milvus_collection(dim=len(vector))
                client = self._get_milvus_client()
                client.upsert(
                    collection_name=self._settings.milvus_collection_name,
                    data=[{
                        "id": doc_id,
                        "vector": vector,
                        "text": text,
                        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                    }],
                )
                record["backend"] = "milvus"
            except Exception:
                # fallback to memory silently for local resilience
                pass
        return {
            "doc_id": doc_id,
            "dimension": len(vector),
            "backend": record["backend"],
            "metadata": metadata or {},
        }

    def search(self, *, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        if not query_vector:
            raise APIError(status_code=400, code="invalid_request", message="query_vector is required")
        if top_k < 1:
            raise APIError(status_code=400, code="invalid_request", message="top_k must be >= 1")

        if self.is_ready():
            try:
                client = self._get_milvus_client()
                result = client.search(
                    collection_name=self._settings.milvus_collection_name,
                    data=[query_vector],
                    limit=top_k,
                    output_fields=["text", "metadata"],
                )
                hits = []
                for item in result[0]:
                    entity = item.get("entity", {}) if isinstance(item, dict) else getattr(item, "entity", {})
                    doc_id = entity.get("id") if isinstance(entity, dict) else None
                    metadata_raw = entity.get("metadata") if isinstance(entity, dict) else None
                    try:
                        metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) and metadata_raw else {}
                    except json.JSONDecodeError:
                        metadata = {}
                    score = float(item.get("distance", 0.0)) if isinstance(item, dict) else float(getattr(item, "distance", 0.0))
                    hits.append({
                        "doc_id": doc_id,
                        "text": entity.get("text") if isinstance(entity, dict) else None,
                        "score": score,
                        "metadata": metadata,
                        "backend": "milvus",
                    })
                if hits:
                    return hits
            except Exception:
                pass

        scored: list[dict[str, Any]] = []
        for record in self._memory_vectors.values():
            if len(record["vector"]) != len(query_vector):
                continue
            score = self._l2_distance(query_vector, record["vector"])
            scored.append({
                "doc_id": record["doc_id"],
                "text": record["text"],
                "score": score,
                "metadata": record["metadata"],
                "backend": "memory",
            })
        scored.sort(key=lambda item: item["score"])
        return scored[:top_k]

    def collection_status(self) -> dict[str, Any]:
        status = {
            "configured": self.is_ready(),
            "collection": self._settings.milvus_collection_name,
            "dimension": self._settings.milvus_dimension,
            "memory_doc_count": len(self._memory_vectors),
            "backend": "memory",
        }
        if self.is_ready():
            try:
                client = self._get_milvus_client()
                exists = client.has_collection(collection_name=self._settings.milvus_collection_name)
                status["milvus_collection_exists"] = bool(exists)
                status["backend"] = "milvus" if exists else "memory"
            except Exception:
                status["milvus_collection_exists"] = False
        return status

    def _get_milvus_client(self):
        if self._milvus_client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise APIError(status_code=503, code="milvus_dependency_missing", message="pymilvus is not installed") from exc
            uri = f"http://{self._settings.milvus_host}:{self._settings.milvus_port}"
            token = None
            if self._settings.milvus_user:
                token = f"{self._settings.milvus_user}:{self._settings.milvus_password}"
            self._milvus_client = MilvusClient(uri=uri, token=token)
        return self._milvus_client

    def _ensure_milvus_collection(self, *, dim: int) -> None:
        client = self._get_milvus_client()
        if client.has_collection(collection_name=self._settings.milvus_collection_name):
            return
        client.create_collection(
            collection_name=self._settings.milvus_collection_name,
            dimension=dim,
            metric_type=self._settings.milvus_metric_type,
            index_type=self._settings.milvus_index_type,
            id_type="string",
            auto_id=False,
            consistency_level="Strong",
        )

    @staticmethod
    def _l2_distance(a: list[float], b: list[float]) -> float:
        return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


class VectorSearchService:
    def __init__(self, embedding_service: EmbeddingService, vector_store_service: VectorStoreService) -> None:
        self._embedding_service = embedding_service
        self._vector_store = vector_store_service

    def index_knowledge_assets(
        self,
        *,
        guide_title: str,
        guide_text: str,
        kb_version: str,
        knowledge_cards: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        indexed_docs: list[dict[str, Any]] = []
        chunks = self._split_text_chunks(guide_text)
        for idx, chunk in enumerate(chunks, start=1):
            doc_id = f"guide::{kb_version}::chunk::{idx}"
            indexed_docs.append(
                self.upsert_text(
                    doc_id=doc_id,
                    text=chunk,
                    metadata={
                        "asset_type": "guide_chunk",
                        "guide_title": guide_title,
                        "kb_version": kb_version,
                        "chunk_index": idx,
                    },
                )
            )

        for entity_id, card in knowledge_cards.items():
            card_text = self._serialize_knowledge_card(card)
            legacy_doc_id = f"knowledge_card::{kb_version}::{entity_id}"
            projection_doc_id = f"knowledge_card_projection::{kb_version}::{entity_id}"
            indexed_docs.append(
                self.upsert_text(
                    doc_id=projection_doc_id,
                    text=card_text,
                    metadata={
                        "asset_type": "knowledge_card_projection",
                        "legacy_asset_type": "knowledge_card",
                        "legacy_doc_id": legacy_doc_id,
                        "projection_asset_type": "knowledge_card_projection",
                        "projection_type": "knowledge_card",
                        "entity_id": entity_id,
                        "guide_title": guide_title,
                        "kb_version": kb_version,
                        "standard_name": card.get("entity", {}).get("standard_name"),
                    },
                )
            )

        return {
            "indexed_count": len(indexed_docs),
            "guide_chunk_count": len(chunks),
            "knowledge_card_count": len(knowledge_cards),
            "documents": indexed_docs,
        }

    def rag_search(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        result = self.semantic_search(query=query, top_k=top_k)
        evidence_pack = []
        for hit in result["hits"]:
            metadata = hit.get("metadata", {}) or {}
            evidence_pack.append(
                {
                    "doc_id": hit["doc_id"],
                    "legacy_doc_id": metadata.get("legacy_doc_id"),
                    "asset_type": metadata.get("asset_type"),
                    "legacy_asset_type": metadata.get("legacy_asset_type"),
                    "text": hit.get("text"),
                    "score": hit.get("score"),
                    "projection_asset_type": metadata.get("projection_asset_type"),
                    "projection_type": metadata.get("projection_type"),
                    "metadata": metadata,
                }
            )
        result["evidence_pack"] = evidence_pack
        return result

    def upsert_text(self, *, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        embedding = self._embedding_service.embed_text(text)
        stored = self._vector_store.upsert_document(
            doc_id=doc_id,
            text=text,
            vector=embedding.vector,
            metadata={
                **(metadata or {}),
                "embedding_model": embedding.model,
                "embedding_dimension": embedding.dimension,
            },
        )
        return {
            **stored,
            "embedding_model": embedding.model,
            "embedding_dimension": embedding.dimension,
        }

    def semantic_search(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        embedding = self._embedding_service.embed_text(query)
        hits = self._vector_store.search(query_vector=embedding.vector, top_k=top_k)
        return {
            "query": query,
            "top_k": top_k,
            "embedding_model": embedding.model,
            "embedding_dimension": embedding.dimension,
            "hits": hits,
        }

    def health(self) -> dict[str, Any]:
        return {
            "embedding_ready": self._embedding_service.is_ready(),
            "vector_store": self._vector_store.collection_status(),
        }


    def _split_text_chunks(self, text: str, *, max_chunk_size: int = 180) -> list[str]:
        normalized = (text or "").strip()
        if not normalized:
            return []
        segments = [seg.strip() for seg in normalized.replace("\r", "\n").split("\n") if seg.strip()]
        if not segments:
            return [normalized[:max_chunk_size]]
        chunks: list[str] = []
        current = ""
        for segment in segments:
            candidate = f"{current}\n{segment}".strip() if current else segment
            if len(candidate) <= max_chunk_size:
                current = candidate
                continue
            if current:
                chunks.append(current)
            if len(segment) <= max_chunk_size:
                current = segment
            else:
                for idx in range(0, len(segment), max_chunk_size):
                    part = segment[idx: idx + max_chunk_size].strip()
                    if part:
                        chunks.append(part)
                current = ""
        if current:
            chunks.append(current)
        return chunks

    def _serialize_knowledge_card(self, card: dict[str, Any]) -> str:
        entity = card.get("entity", {})
        standard_name = entity.get("standard_name", "")
        aliases = "、".join(card.get("aliases", []) or [])
        effects = "、".join(card.get("effects", []) or [])
        prohibited_contexts = "、".join(card.get("prohibited_contexts", []) or [])
        allowed_contexts = "、".join(card.get("allowed_contexts", []) or [])
        not_for = "、".join(card.get("not_for_populations", []) or [])
        contraindications = "、".join(
            item.get("target_name", "") for item in (card.get("contraindications", []) or []) if item.get("target_name")
        )
        lines = [
            f"实体：{standard_name}",
            f"别名：{aliases}" if aliases else "",
            f"功效：{effects}" if effects else "",
            f"适用场景：{allowed_contexts}" if allowed_contexts else "",
            f"禁用场景：{prohibited_contexts}" if prohibited_contexts else "",
            f"禁用人群：{not_for}" if not_for else "",
            f"配伍禁忌：{contraindications}" if contraindications else "",
        ]
        return "\n".join(line for line in lines if line)
