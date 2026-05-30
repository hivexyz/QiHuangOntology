from __future__ import annotations

from uuid import UUID

from ..exceptions import APIError
from ..schemas import LoginResponseData, UserProfile
from ..store import InMemoryStore
from ..utils import utcnow


class AuthService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def login(self, email: str, password: str) -> LoginResponseData:
        user_id = self.store.user_email_index.get(email)
        if user_id is None:
            raise APIError(status_code=401, code="unauthorized", message="Invalid credentials")
        user = self.store.users[user_id]
        if user["password"] != password:
            raise APIError(status_code=401, code="unauthorized", message="Invalid credentials")
        token = f"demo-token:{user_id}"
        with self.store.lock():
            self.store.tokens[token] = user_id
            user["last_login_at"] = utcnow()
        self.store.persist_user(user)
        self.store.persist_token(token, user_id)
        return LoginResponseData(access_token=token, user=self.get_user_profile(user_id))

    def get_user_profile(self, user_id: UUID) -> UserProfile:
        user = self.store.users.get(user_id)
        if user is None:
            raise APIError(status_code=404, code="not_found", message="User not found")
        roles = [
            membership["role_code"]
            for membership in self.store.memberships.values()
            if membership["user_id"] == user_id and membership["status"] == "active"
        ]
        return UserProfile(
            user_id=user["user_id"],
            email=user["email"],
            display_name=user["display_name"],
            roles=roles,
        )

    def get_user_from_token(self, token: str | None) -> UserProfile:
        if not token:
            raise APIError(status_code=401, code="unauthorized", message="Missing bearer token")
        token = token.removeprefix("Bearer ").strip()
        user_id = self.store.tokens.get(token)
        if user_id is None:
            raise APIError(status_code=401, code="unauthorized", message="Invalid bearer token")
        return self.get_user_profile(user_id)
