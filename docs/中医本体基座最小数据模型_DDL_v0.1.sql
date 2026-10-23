-- 中医本体基座最小数据模型 DDL v0.1
-- 说明：本文件用于 PostgreSQL，服务于中医本体基座而非下游业务系统。

CREATE TABLE ontology_versions (
    version_id            VARCHAR(64) PRIMARY KEY,
    version_type          VARCHAR(32) NOT NULL,
    version_name          VARCHAR(255) NOT NULL,
    based_on_version      VARCHAR(64),
    change_summary        TEXT,
    change_scope_json     JSONB NOT NULL DEFAULT '[]',
    created_at            TIMESTAMP NOT NULL,
    created_by            VARCHAR(64) NOT NULL,
    review_status         VARCHAR(32) NOT NULL,
    reviewed_by           VARCHAR(64),
    published_at          TIMESTAMP,
    status                VARCHAR(32) NOT NULL
);

CREATE TABLE concepts (
    concept_id            VARCHAR(64) PRIMARY KEY,
    concept_type          VARCHAR(64) NOT NULL,
    canonical_name        VARCHAR(255) NOT NULL,
    display_name_zh       VARCHAR(255) NOT NULL,
    definition            TEXT NOT NULL,
    boundary_note         TEXT,
    example_positive_json JSONB NOT NULL DEFAULT '[]',
    example_negative_json JSONB NOT NULL DEFAULT '[]',
    parent_concept_id     VARCHAR(64),
    source_note           TEXT,
    ontology_version      VARCHAR(64) NOT NULL,
    status                VARCHAR(32) NOT NULL,
    created_at            TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL
);

CREATE INDEX idx_concepts_type ON concepts(concept_type);
CREATE INDEX idx_concepts_name ON concepts(canonical_name);
CREATE INDEX idx_concepts_version ON concepts(ontology_version);

CREATE TABLE concept_aliases (
    alias_id              VARCHAR(64) PRIMARY KEY,
    concept_id            VARCHAR(64) NOT NULL REFERENCES concepts(concept_id),
    alias_text            VARCHAR(255) NOT NULL,
    alias_type            VARCHAR(64) NOT NULL,
    source_document_id    VARCHAR(64),
    note                  TEXT,
    ontology_version      VARCHAR(64) NOT NULL,
    status                VARCHAR(32) NOT NULL,
    created_at            TIMESTAMP NOT NULL
);

CREATE INDEX idx_aliases_text ON concept_aliases(alias_text);
CREATE INDEX idx_aliases_concept ON concept_aliases(concept_id);

CREATE TABLE mentions (
    mention_id            VARCHAR(64) PRIMARY KEY,
    raw_text              VARCHAR(255) NOT NULL,
    normalized_text       VARCHAR(255),
    source_text_id        VARCHAR(128) NOT NULL,
    source_text_type      VARCHAR(32),
    context_window        TEXT,
    start_offset          INT,
    end_offset            INT,
    created_at            TIMESTAMP NOT NULL
);

CREATE TABLE normalization_decisions (
    decision_id           VARCHAR(64) PRIMARY KEY,
    mention_id            VARCHAR(64) NOT NULL REFERENCES mentions(mention_id),
    raw_text              VARCHAR(255) NOT NULL,
    normalized_text       VARCHAR(255),
    candidate_list_json   JSONB NOT NULL,
    chosen_concept_id     VARCHAR(64),
    chosen_concept_type   VARCHAR(64),
    decision_method       VARCHAR(64) NOT NULL,
    confidence            NUMERIC(5,4),
    rationale             TEXT,
    review_status         VARCHAR(32) NOT NULL,
    ontology_version      VARCHAR(64) NOT NULL,
    created_at            TIMESTAMP NOT NULL
);

CREATE TABLE relation_definitions (
    relation_code         VARCHAR(64) PRIMARY KEY,
    display_name_zh       VARCHAR(255) NOT NULL,
    definition            TEXT NOT NULL,
    domain_json           JSONB NOT NULL,
    range_json            JSONB NOT NULL,
    semantic_direction    TEXT,
    inverse_relation      VARCHAR(64),
    boundary_note         TEXT,
    condition_note        TEXT,
    schema_version        VARCHAR(64) NOT NULL,
    status                VARCHAR(32) NOT NULL
);

CREATE TABLE condition_sets (
    condition_set_id      VARCHAR(64) PRIMARY KEY,
    logic_json            JSONB NOT NULL,
    note                  TEXT
);

CREATE TABLE assertions (
    assertion_id          VARCHAR(64) PRIMARY KEY,
    subject_concept_id    VARCHAR(64) NOT NULL REFERENCES concepts(concept_id),
    predicate_code        VARCHAR(64) NOT NULL REFERENCES relation_definitions(relation_code),
    object_concept_id     VARCHAR(64) REFERENCES concepts(concept_id),
    object_literal        TEXT,
    condition_set_id      VARCHAR(64) REFERENCES condition_sets(condition_set_id),
    qualifier_json        JSONB NOT NULL DEFAULT '{}',
    confidence            NUMERIC(5,4),
    source_document       VARCHAR(64),
    ontology_version      VARCHAR(64) NOT NULL,
    status                VARCHAR(32) NOT NULL,
    created_at            TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL,
    CHECK (
        (object_concept_id IS NOT NULL AND object_literal IS NULL)
        OR (object_concept_id IS NULL AND object_literal IS NOT NULL)
    )
);

CREATE INDEX idx_assertions_subject ON assertions(subject_concept_id);
CREATE INDEX idx_assertions_predicate ON assertions(predicate_code);
CREATE INDEX idx_assertions_object ON assertions(object_concept_id);
CREATE INDEX idx_assertions_version ON assertions(ontology_version);

CREATE TABLE source_documents (
    document_id           VARCHAR(64) PRIMARY KEY,
    document_type         VARCHAR(64) NOT NULL,
    title                 VARCHAR(500) NOT NULL,
    source_uri            TEXT,
    source_reference      TEXT,
    publisher_or_issuer   VARCHAR(255),
    edition_or_version    VARCHAR(128),
    published_at          DATE,
    language              VARCHAR(32),
    document_scope_note   TEXT,
    ontology_version      VARCHAR(64),
    status                VARCHAR(32) NOT NULL
);

CREATE TABLE evidence_fragments (
    evidence_id           VARCHAR(64) PRIMARY KEY,
    document_id           VARCHAR(64) NOT NULL REFERENCES source_documents(document_id),
    evidence_type         VARCHAR(32) NOT NULL,
    quoted_text           TEXT NOT NULL,
    offset_start          INT,
    offset_end            INT,
    section_ref           VARCHAR(255),
    context_window        TEXT,
    language              VARCHAR(32),
    evidence_scope_note   TEXT,
    status                VARCHAR(32) NOT NULL
);

CREATE TABLE evidence_links (
    link_id               VARCHAR(64) PRIMARY KEY,
    target_type           VARCHAR(64) NOT NULL,
    target_id             VARCHAR(64) NOT NULL,
    evidence_id           VARCHAR(64) NOT NULL REFERENCES evidence_fragments(evidence_id),
    support_role          VARCHAR(64) NOT NULL,
    support_strength      VARCHAR(32) NOT NULL,
    note                  TEXT
);

CREATE TABLE change_records (
    change_id             VARCHAR(64) PRIMARY KEY,
    object_type           VARCHAR(64) NOT NULL,
    object_id             VARCHAR(64) NOT NULL,
    change_type           VARCHAR(32) NOT NULL,
    from_version          VARCHAR(64),
    to_version            VARCHAR(64) NOT NULL,
    change_summary        TEXT NOT NULL,
    reason                TEXT,
    impact_note           TEXT,
    created_at            TIMESTAMP NOT NULL,
    created_by            VARCHAR(64) NOT NULL,
    review_status         VARCHAR(32) NOT NULL
);
