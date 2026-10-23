from __future__ import annotations

from fastapi import APIRouter

from .routes import auth, ontology, ontology_base, policies, rules, vector_search

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(rules.router)
api_router.include_router(policies.router)
api_router.include_router(ontology.router)
api_router.include_router(ontology_base.router)
api_router.include_router(vector_search.router)
