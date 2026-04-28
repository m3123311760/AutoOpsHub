import os
from pathlib import Path

from fastapi.testclient import TestClient


TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)

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
