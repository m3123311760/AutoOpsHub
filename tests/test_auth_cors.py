import os
from pathlib import Path

from fastapi.testclient import TestClient
import pymysql


TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)
os.environ["AUTOOPSHUB_REQUIRE_AUTH"] = "false"

from main import app, settings


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
