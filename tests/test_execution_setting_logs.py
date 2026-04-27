import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)

from main import app

client = TestClient(app)


def setup_module() -> None:
    client.delete("/api/workpieces/exec-wp")
    client.post("/api/workpieces/exec-wp", json={"description": "exec tests"})
    client.post(
        "/api/workpieces/exec-wp/runbooks/rb",
        json={
            "type": "Workflow",
            "content": "steps: []\n",
        },
    )


def test_setting_auto_execute_and_render_to_tmp():
    set_resp = client.put(
        "/api/workpieces/exec-wp/setting",
        json={
            "no_variable_strategy": {"action": "auto_execute", "delay_seconds": 0},
            "optional_only_strategy": {"action": "auto_execute", "delay_seconds": 0},
            "ready_strategy": {"action": "auto_execute", "delay_seconds": 0},
            "required_missing_retention_seconds": 3600,
        },
    )
    assert set_resp.status_code == 200

    trig = client.post("/api/workpieces/exec-wp/runbooks/rb/trigger", json={"variables": {}})
    assert trig.status_code == 201
    task = trig.json()["task"]
    assert task["status"] == "success"
    assert task["schedule"]["runtime_dir"].startswith(str(Path(tempfile.gettempdir())))
    assert ".autoopshub" not in task["schedule"]["runtime_dir"]


def test_system_reserved_variables_render_as_nested_jinja_context():
    client.delete("/api/workpieces/exec-system-wp")
    create_wp = client.post("/api/workpieces/exec-system-wp", json={"description": "system vars"})
    assert create_wp.status_code == 201
    create_rb = client.post(
        "/api/workpieces/exec-system-wp/runbooks/rb-system",
        json={
            "type": "Workflow",
            "content": 'output: "{{ system.output }}"\nrunbook: "{{ system.runbook_file }}"\nsteps: []\n',
        },
    )
    assert create_rb.status_code == 201

    trig = client.post("/api/workpieces/exec-system-wp/runbooks/rb-system/trigger", json={"variables": {}})
    assert trig.status_code == 201
    task = trig.json()["task"]
    rendered_file = Path(task["schedule"]["rendered_file"])
    rendered = rendered_file.read_text(encoding="utf-8")

    assert f"output: \"{Path(task['schedule']['runtime_dir']) / 'system.output'}\"" in rendered
    assert f"runbook: \"{rendered_file}\"" in rendered


def test_logs_history_and_stream():
    trig = client.post("/api/workpieces/exec-wp/runbooks/rb/trigger", json={"variables": {}})
    task_id = trig.json()["task"]["task_id"]

    logs = client.get(f"/api/workpieces/exec-wp/tasks/{task_id}/logs?after=0&limit=500")
    assert logs.status_code == 200
    assert len(logs.json()["items"]) >= 2
    assert logs.json()["items"][0]["log_seq"] >= 1

    stream = client.get(
        f"/api/workpieces/exec-wp/tasks/{task_id}/logs/stream",
        headers={"Accept": "text/event-stream"},
    )
    assert stream.status_code == 200
    assert "data:" in stream.text
