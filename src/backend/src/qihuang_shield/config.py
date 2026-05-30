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
    postgres_dsn: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    cors_allow_origin_regex: str

    @property
    def use_database(self) -> bool:
        return self.storage_backend.lower() == "database"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        storage_backend=os.getenv("QHS_STORAGE_BACKEND", "memory").strip().lower() or "memory",
        db_auto_init=os.getenv("QHS_DB_AUTO_INIT", "true").strip().lower() in TRUE_VALUES,
        postgres_dsn=os.getenv(
            "QHS_POSTGRES_DSN",
            "postgresql://postgres:postgres@127.0.0.1:5432/qihuang_shield",
        ).strip(),
        neo4j_uri=os.getenv("QHS_NEO4J_URI", "bolt://127.0.0.1:7687").strip(),
        neo4j_user=os.getenv("QHS_NEO4J_USER", "neo4j").strip(),
        neo4j_password=os.getenv("QHS_NEO4J_PASSWORD", "neo4j_password").strip(),
        neo4j_database=os.getenv("QHS_NEO4J_DATABASE", "neo4j").strip(),
        cors_allow_origin_regex=os.getenv(
            "QHS_CORS_ALLOW_ORIGIN_REGEX",
            r"http://(127\\.0\\.0\\.1|localhost)(:\\d+)?",
        ).strip(),
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
