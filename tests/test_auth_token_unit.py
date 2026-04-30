from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from autoopshub import auth_service
from autoopshub.auth_service import AuthPrincipal, AuthService, pwd_context
from autoopshub.settings import AppSettings


client = TestClient(main.app)


class _FakeCursor:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.last_sql = ""
        self.last_params: tuple[object, ...] = ()

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.last_sql = sql
        self.last_params = params
        self.state["last_sql"] = sql
        self.state["last_params"] = params
        if sql.startswith("INSERT INTO auth_jwt_sessions"):
            self.state["sessions"][str(params[0])] = {"revoked_at": None}
        if sql.startswith("UPDATE auth_jwt_sessions"):
            self.state["sessions"].setdefault(str(params[1]), {})["revoked_at"] = params[0]
        if sql.startswith("INSERT INTO auth_api_keys"):
            self.state["api_keys"].append(
                {"id": str(params[0]), "name": str(params[1]), "key_prefix": str(params[2]), "key_hash": str(params[3]), "revoked_at": None}
            )
        if sql.startswith("UPDATE auth_api_keys"):
            for row in self.state["api_keys"]:
                if row["id"] == str(params[1]) and not row["revoked_at"]:
                    row["revoked_at"] = params[0]

    def fetchone(self) -> dict[str, Any] | None:
        sql = self.state["last_sql"]
        params = self.state["last_params"]
        if sql.startswith("SELECT password_hash"):
            user = self.state["users"].get(str(params[0]))
            return {"password_hash": user} if user else None
        if sql.startswith("SELECT revoked_at FROM auth_jwt_sessions"):
            return self.state["sessions"].get(str(params[0]))
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        sql = self.state["last_sql"]
        params = self.state["last_params"]
        if sql.startswith("SELECT id, key_hash"):
            return [row for row in self.state["api_keys"] if row["key_prefix"] == str(params[0])]
        if sql.startswith("SELECT id, name"):
            return self.state["api_keys"]
        return []


class _FakeConnection:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.state)

    def close(self) -> None:
        return None


def _settings() -> AppSettings:
    settings = AppSettings()
    settings.jwt.secret = "unit-secret"
    settings.jwt.expire_minutes = 5
    return settings


def _state() -> dict[str, Any]:
    return {
        "users": {"admin": pwd_context.hash("correct-password")},
        "sessions": {},
        "api_keys": [],
    }


def test_local_auth_success_failure_user_missing_and_password_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    monkeypatch.setattr(auth_service, "mysql_connect", lambda settings: _FakeConnection(state))
    svc = AuthService(_settings())

    ok = svc.login("local", "admin", "correct-password")
    assert ok["access_token"]
    assert ok["principal"] == {"username": "admin", "auth_mode": "local"}

    with pytest.raises(HTTPException) as wrong_password:
        svc.login("local", "admin", "wrong")
    with pytest.raises(HTTPException) as missing_user:
        svc.login("local", "missing", "correct-password")

    assert wrong_password.value.status_code == 401
    assert missing_user.value.status_code == 401


def test_jwt_valid_expired_and_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    monkeypatch.setattr(auth_service, "mysql_connect", lambda settings: _FakeConnection(state))
    svc = AuthService(_settings())

    token = svc.login("local", "admin", "correct-password")["access_token"]
    principal = svc.decode_and_validate_jwt(token)
    assert principal.subject == "admin"

    expired = jwt.encode(
        {"sub": "admin", "jti": "expired", "amr": "local", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        "unit-secret",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as expired_error:
        svc.decode_and_validate_jwt(expired)
    assert expired_error.value.status_code == 401

    svc.revoke_jwt_for_token(token)
    with pytest.raises(HTTPException) as revoked_error:
        svc.decode_and_validate_jwt(token)
    assert revoked_error.value.status_code == 401


def test_api_key_valid_invalid_and_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    monkeypatch.setattr(auth_service, "mysql_connect", lambda settings: _FakeConnection(state))
    svc = AuthService(_settings())

    created = svc.create_api_key("ci")
    assert svc.validate_api_key(created["api_key"]) is not None
    assert svc.validate_api_key("aoh_invalid") is None

    svc.revoke_api_key(created["id"])

    assert svc.validate_api_key(created["api_key"]) is None


def test_auth_middleware_accepts_jwt_or_api_key_and_rejects_missing_invalid_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAuth:
        def validate_api_key(self, raw_key: str) -> AuthPrincipal | None:
            if raw_key == "valid-key":
                return AuthPrincipal(subject="apikey:1", auth_mode="local")
            return None

        def decode_and_validate_jwt(self, token: str) -> AuthPrincipal:
            if token == "valid-jwt":
                return AuthPrincipal(subject="admin", auth_mode="local")
            raise HTTPException(status_code=401, detail="JWT 已撤销或无效")

    original_require_auth = main.settings.require_auth
    main.settings.require_auth = True
    monkeypatch.setattr(main, "auth_svc", FakeAuth())
    try:
        assert client.get("/api/workpieces").status_code == 401
        assert client.get("/api/workpieces", headers={"Authorization": "Bearer valid-jwt"}).status_code == 200
        assert client.get("/api/workpieces", headers={"X-API-Key": "valid-key"}).status_code == 200
        assert client.get("/api/workpieces", headers={"Authorization": "Bearer revoked-jwt"}).status_code == 401
        assert client.get("/api/workpieces", headers={"X-API-Key": "revoked-key"}).status_code == 401
    finally:
        main.settings.require_auth = original_require_auth
