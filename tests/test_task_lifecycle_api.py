import os
from pathlib import Path

from fastapi.testclient import TestClient

TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)
os.environ["AUTOOPSHUB_REQUIRE_AUTH"] = "false"

import main
from main import app

client = TestClient(app)


def setup_module() -> None:
    client.delete("/api/workpieces/tasks-wp")
    client.post("/api/workpieces/tasks-wp", json={"description": "task tests"})
    client.put(
        "/api/workpieces/tasks-wp/setting",
        json={
            "no_variable_strategy": {"action": "schedule_execute", "delay_seconds": 60},
            "optional_only_strategy": {"action": "schedule_execute", "delay_seconds": 60},
            "ready_strategy": {"action": "schedule_execute", "delay_seconds": 60},
            "required_missing_retention_seconds": 3600,
        },
    )
    client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-req",
        json={
            "type": "Workflow",
            "content": "title: \"{{ required_var }}-{{ optional_var }}\"\nsteps: []\n",
            "manifest": [
                {"name": "required_var", "direction": "input", "required": True},
                {"name": "optional_var", "direction": "input", "required": False},
            ],
        },
    )
    client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-no-var",
        json={"type": "Workflow", "content": "steps: []\n"},
    )


def test_trigger_validation_branches_and_task_creation():
    missing_required = client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-req/trigger",
        json={"variables": {"optional_var": "x"}},
    )
    assert missing_required.status_code == 202
    body = missing_required.json()
    assert body["task"]["status"] == "pending"
    assert "required_var" in body["missing_required"]

    unknown_var = client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-req/trigger",
        json={"variables": {"required_var": "1", "oops": "2"}},
    )
    assert unknown_var.status_code == 422
    assert "oops" in unknown_var.json()["detail"]["unknown_variables"]

    no_var_with_params = client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-no-var/trigger",
        json={"variables": {"x": "1"}},
    )
    assert no_var_with_params.status_code == 422

    valid = client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-req/trigger",
        json={"variables": {"required_var": "ok"}},
    )
    assert valid.status_code == 201
    assert valid.json()["task"]["variables"]["required_var"] == "ok"


def test_task_list_detail_update_confirm_cancel():
    created = client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-req/trigger",
        json={"variables": {"required_var": "v1"}},
    )
    assert created.status_code == 201
    task_id = created.json()["task"]["task_id"]

    list_resp = client.get("/api/workpieces/tasks-wp/tasks")
    assert list_resp.status_code == 200
    assert any(x["task_id"] == task_id for x in list_resp.json()["items"])

    detail = client.get(f"/api/workpieces/tasks-wp/tasks/{task_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert "logs" not in detail_body
    assert detail_body["task_id"] == task_id

    update = client.put(
        f"/api/workpieces/tasks-wp/tasks/{task_id}/variables",
        json={"variables": {"required_var": "v2", "optional_var": "x"}},
    )
    assert update.status_code == 200
    assert update.json()["variables"]["required_var"] == "v2"

    confirm = client.post(f"/api/workpieces/tasks-wp/tasks/{task_id}/confirm")
    assert confirm.status_code == 202
    confirmed = client.get(f"/api/workpieces/tasks-wp/tasks/{task_id}").json()
    assert confirmed["status"] in ("running", "success")

    reject_update_after_confirm = client.put(
        f"/api/workpieces/tasks-wp/tasks/{task_id}/variables",
        json={"variables": {"required_var": "v3"}},
    )
    assert reject_update_after_confirm.status_code == 409

    cancel_running = client.post(f"/api/workpieces/tasks-wp/tasks/{task_id}/cancel")
    assert cancel_running.status_code in (200, 409)


def test_confirm_ready_task_is_idempotent_and_queues_execution_once(monkeypatch):
    calls: list[str] = []

    def fake_execute(workpiece_name, task):
        calls.append(task.task_id)

    monkeypatch.setattr(main, "_execute_task", fake_execute)
    created = client.post(
        "/api/workpieces/tasks-wp/runbooks/rb-req/trigger",
        json={"variables": {"required_var": "v1"}},
    )
    assert created.status_code == 201
    task_id = created.json()["task"]["task_id"]

    first = client.post(f"/api/workpieces/tasks-wp/tasks/{task_id}/confirm")
    second = client.post(f"/api/workpieces/tasks-wp/tasks/{task_id}/confirm")

    assert first.status_code == 202
    assert second.status_code == 409
    assert calls == [task_id]
