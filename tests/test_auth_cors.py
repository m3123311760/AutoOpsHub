import os
from pathlib import Path

from fastapi.testclient import TestClient
import pymysql


TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)
os.environ["AUTOOPSHUB_REQUIRE_AUTH"] = "false"

from main import app, settings, _startup_check_auth_schema


client = TestClient(app)


def test_unauthenticated_api_response_includes_cors_headers():
    original_require_auth = settings.require_auth
    settings.require_auth = True
    try:
        response = client.get(
            "/api/workpieces",
            headers={"Origin": "http://localhost:3000"},
        )
    finally:
        settings.require_auth = original_require_auth

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_auth_health_reports_when_auth_is_disabled():
    original_require_auth = settings.require_auth
    settings.require_auth = False
    try:
        response = client.get("/api/health/auth")
    finally:
        settings.require_auth = original_require_auth

    assert response.status_code == 200
    assert response.json() == {"require_auth": False}


def test_startup_check_fails_fast_when_auth_schema_is_unreachable(monkeypatch):
    original_require_auth = settings.require_auth
    original_secret = settings.jwt.secret
    settings.require_auth = True
    settings.jwt.secret = "test-secret"

    def fail_schema(_settings):
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr("main.assert_auth_schema_present", fail_schema)
    try:
        try:
            _startup_check_auth_schema()
        except RuntimeError as exc:
            assert "schema unavailable" in str(exc)
        else:
            raise AssertionError("startup check should fail when auth schema is unreachable")
    finally:
        settings.require_auth = original_require_auth
        settings.jwt.secret = original_secret


def test_login_returns_service_unavailable_when_auth_database_is_unreachable(monkeypatch):
    original_require_auth = settings.require_auth
    settings.require_auth = True

    def fail_connect(_settings):
        raise pymysql.err.OperationalError(1045, "Access denied")

    monkeypatch.setattr("autoopshub.db_schema.mysql_connect", fail_connect)
    monkeypatch.setattr("main.mysql_connect", fail_connect, raising=False)
    try:
        response = client.post(
            "/api/auth/login",
            json={"mode": "local", "username": "admin", "password": "bad"},
        )
    finally:
        settings.require_auth = original_require_auth

    assert response.status_code == 503
    assert "认证数据库不可用" in response.json()["detail"]
