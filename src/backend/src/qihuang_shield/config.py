from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os


TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    storage_backend: str
    db_auto_init: bool
    enable_demo_seed: bool
    postgres_dsn: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    cors_allow_origin_regex: str
    llm_enabled: bool
    llm_base_url: str
    llm_endpoint: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_pool_size: int
    postgres_max_overflow: int
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_embedding_model: str
    openai_embedding_dimension: int
    openai_embedding_base_url: str
    milvus_host: str
    milvus_port: int
    milvus_user: str
    milvus_password: str
    milvus_collection_name: str
    milvus_dimension: int
    milvus_index_type: str
    milvus_metric_type: str
    allow_insecure_dev_secret: bool = False

    @property
    def use_database(self) -> bool:
        return self.storage_backend.lower() == "database"

    @property
    def llm_ready(self) -> bool:
        return self.llm_enabled and bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def openai_chat_ready(self) -> bool:
        return bool(self.openai_base_url and self.openai_api_key and self.openai_model)

    @property
    def embedding_ready(self) -> bool:
        return bool(self.openai_embedding_base_url and self.openai_api_key and self.openai_embedding_model)

    @property
    def milvus_ready(self) -> bool:
        return bool(self.milvus_host and self.milvus_port and self.milvus_collection_name)

    @property
    def postgres_structured_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    enable_demo_seed = os.getenv("QHS_ENABLE_DEMO_SEED", "false").strip().lower() in TRUE_VALUES
    return Settings(
        storage_backend=os.getenv("QHS_STORAGE_BACKEND", "memory").strip().lower() or "memory",
        db_auto_init=os.getenv("QHS_DB_AUTO_INIT", "true").strip().lower() in TRUE_VALUES,
        enable_demo_seed=enable_demo_seed,
        postgres_dsn=os.getenv(
            "QHS_POSTGRES_DSN",
            os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/qihuang_shield"),
        ).strip(),
        neo4j_uri=os.getenv("QHS_NEO4J_URI", "bolt://127.0.0.1:7687").strip(),
        neo4j_user=os.getenv("QHS_NEO4J_USER", "neo4j").strip(),
        neo4j_password=os.getenv("QHS_NEO4J_PASSWORD", "neo4j_password").strip(),
        neo4j_database=os.getenv("QHS_NEO4J_DATABASE", "neo4j").strip(),
        cors_allow_origin_regex=os.getenv(
            "QHS_CORS_ALLOW_ORIGIN_REGEX",
            r"http://(127\.0\.0\.1|localhost)(:\d+)?",
        ).strip(),
        llm_enabled=os.getenv("QHS_LLM_ENABLED", "false").strip().lower() in TRUE_VALUES,
        llm_base_url=os.getenv(
            "QHS_LLM_BASE_URL",
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ).strip(),
        llm_endpoint=os.getenv("QHS_LLM_ENDPOINT", "/chat/completions").strip() or "/chat/completions",
        llm_api_key=os.getenv(
            "QHS_LLM_API_KEY",
            os.getenv("OPENAI_API_KEY", ""),
        ).strip(),
        llm_model=os.getenv(
            "QHS_LLM_MODEL",
            os.getenv("OPENAI_MODEL", ""),
        ).strip(),
        llm_timeout_seconds=float(os.getenv("QHS_LLM_TIMEOUT_SECONDS", "60").strip() or "60"),
        postgres_host=os.getenv("POSTGRES_HOST", "127.0.0.1").strip(),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432").strip() or "5432"),
        postgres_user=os.getenv("POSTGRES_USER", "postgres").strip(),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "postgres").strip(),
        postgres_db=os.getenv("POSTGRES_DB", "qihuang_shield").strip(),
        postgres_pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "10").strip() or "10"),
        postgres_max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "20").strip() or "20"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "").strip(),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "").strip(),
        openai_embedding_dimension=int(os.getenv("OPENAI_EMBEDDING_DIMENSION", "1024").strip() or "1024"),
        openai_embedding_base_url=os.getenv(
            "OPENAI_EMBEDDING_BASE_URL",
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ).strip(),
        milvus_host=os.getenv("MILVUS_HOST", "127.0.0.1").strip(),
        milvus_port=int(os.getenv("MILVUS_PORT", "19530").strip() or "19530"),
        milvus_user=os.getenv("MILVUS_USER", "").strip(),
        milvus_password=os.getenv("MILVUS_PASSWORD", "").strip(),
        milvus_collection_name=os.getenv("MILVUS_COLLECTION_NAME", "vectors").strip(),
        milvus_dimension=int(os.getenv("MILVUS_DIMENSION", "1024").strip() or "1024"),
        milvus_index_type=os.getenv("MILVUS_INDEX_TYPE", "IVF_FLAT").strip(),
        milvus_metric_type=os.getenv("MILVUS_METRIC_TYPE", "L2").strip(),
        allow_insecure_dev_secret=os.getenv(
            "QHS_ALLOW_INSECURE_DEV_SECRET",
            "true" if enable_demo_seed else "false",
        ).strip().lower() in TRUE_VALUES,
    )


def _load_dotenv() -> None:
    current = Path(__file__).resolve()
    env_path = current.parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
