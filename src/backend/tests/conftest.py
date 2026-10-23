from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("QHS_STORAGE_BACKEND", "memory")
os.environ.setdefault("QHS_DB_AUTO_INIT", "false")
os.environ.setdefault("QHS_ENABLE_DEMO_SEED", "true")

from qihuang_shield.app import app
from qihuang_shield.dependencies import (
    auth_service,
    cache_control_service,
    store,
)


@pytest.fixture(autouse=True)
def reset_backend_state():
    if hasattr(store, "_init_state"):
        store._init_state()
    if hasattr(store, "_seed_demo_data"):
        store._seed_demo_data()
    auth_service._failed_login_attempts.clear()
    cache_control_service.clear()
    yield
    auth_service._failed_login_attempts.clear()
    cache_control_service.clear()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
