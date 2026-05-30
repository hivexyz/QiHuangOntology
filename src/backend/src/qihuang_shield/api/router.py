from __future__ import annotations

from fastapi import APIRouter

from .routes import auth, moderation, ontology, policies, reports, review_tasks, rules

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(moderation.router)
api_router.include_router(review_tasks.router)
api_router.include_router(rules.router)
api_router.include_router(policies.router)
api_router.include_router(ontology.router)
api_router.include_router(reports.router)
