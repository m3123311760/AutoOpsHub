import os
from pathlib import Path

from fastapi.testclient import TestClient


TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)

from main import app


client = TestClient(app)


def test_workpiece_crud_and_setting_flow():
    client.delete("/api/workpieces/devops")
    client.delete("/api/workpieces/platform")

    list_resp = client.get("/api/workpieces")
    assert list_resp.status_code == 200
    assert isinstance(list_resp.json()["items"], list)

    create_resp = client.post("/api/workpieces/devops", json={"description": "team space"})
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "devops"
    assert created["description"] == "team space"
    assert "created_at" in created
    assert "updated_at" in created

    setting_resp = client.get("/api/workpieces/devops/setting")
    assert setting_resp.status_code == 200
    setting = setting_resp.json()
    assert setting["no_variable_strategy"]["action"] == "auto_execute"
    assert setting["required_missing_retention_seconds"] == 86400

    detail_resp = client.get("/api/workpieces/devops")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["name"] == "devops"
    assert detail["stats"]["runbooks"] == 0

    update_resp = client.put(
        "/api/workpieces/devops",
        json={"name": "platform", "description": "platform team"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "platform"
    assert updated["description"] == "platform team"

    setting_update = client.put(
        "/api/workpieces/platform/setting",
        json={
            "no_variable_strategy": {"action": "auto_cancel", "delay_seconds": 60},
            "optional_only_strategy": {"action": "schedule_execute", "delay_seconds": 90},
            "ready_strategy": {"action": "schedule_cancel", "delay_seconds": 120},
            "required_missing_retention_seconds": 7200,
        },
    )
    assert setting_update.status_code == 200
    assert setting_update.json()["ready_strategy"]["action"] == "schedule_cancel"

    bad_setting_update = client.put(
        "/api/workpieces/platform/setting",
        json={
            "no_variable_strategy": {"action": "oops", "delay_seconds": 10},
            "optional_only_strategy": {"action": "auto_execute", "delay_seconds": 0},
            "ready_strategy": {"action": "auto_cancel", "delay_seconds": 0},
            "required_missing_retention_seconds": 10,
        },
    )
    assert bad_setting_update.status_code == 422

    delete_resp = client.delete("/api/workpieces/platform")
    assert delete_resp.status_code == 204

    after_delete_resp = client.get("/api/workpieces/platform")
    assert after_delete_resp.status_code == 404
