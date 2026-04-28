import os
from pathlib import Path

from fastapi.testclient import TestClient

TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)

from main import app

client = TestClient(app)


def setup_module() -> None:
    client.delete("/api/workpieces/job-wp")
    client.post("/api/workpieces/job-wp", json={"description": "job tests"})
    client.post(
        "/api/workpieces/job-wp/runbooks/job-rb",
        json={
            "type": "Workflow",
            "content": "title: \"{{name}}\"\nsteps: []\n",
            "manifest": [{"name": "name", "direction": "input", "required": True}],
        },
    )


def test_job_crud_and_validation():
    bad_cron = client.post(
        "/api/workpieces/job-wp/jobs/nightly",
        json={"cron": "bad cron", "runbook_name": "job-rb", "variables": {"name": "a"}},
    )
    assert bad_cron.status_code == 422

    missing_rb = client.post(
        "/api/workpieces/job-wp/jobs/nightly",
        json={"cron": "*/5 * * * *", "runbook_name": "missing", "variables": {"name": "a"}},
    )
    assert missing_rb.status_code == 422

    created = client.post(
        "/api/workpieces/job-wp/jobs/nightly",
        json={"cron": "*/5 * * * *", "runbook_name": "job-rb", "variables": {"name": "a"}},
    )
    assert created.status_code == 201
    assert created.json()["job_name"] == "nightly"

    listed = client.get("/api/workpieces/job-wp/jobs")
    assert listed.status_code == 200
    assert any(x["job_name"] == "nightly" for x in listed.json()["items"])

    detail = client.get("/api/workpieces/job-wp/jobs/nightly")
    assert detail.status_code == 200
    assert detail.json()["runbook_name"] == "job-rb"

    updated = client.put(
        "/api/workpieces/job-wp/jobs/nightly",
        json={"job_name": "nightly2", "cron": "*/10 * * * *", "variables": {"name": "b"}},
    )
    assert updated.status_code == 200
    assert updated.json()["job_name"] == "nightly2"

    deleted = client.delete("/api/workpieces/job-wp/jobs/nightly2")
    assert deleted.status_code == 204


def test_job_trigger_creates_job_task():
    create = client.post(
        "/api/workpieces/job-wp/jobs/quick",
        json={"cron": "* * * * *", "runbook_name": "job-rb", "variables": {"name": "from-job"}},
    )
    assert create.status_code == 201

    trigger = client.post("/api/workpieces/job-wp/jobs/quick/trigger")
    assert trigger.status_code == 201
    task = trigger.json()["task"]
    assert task["source"] == "job"
    assert task["runbook_name"] == "job-rb"


def test_job_trigger_with_unknown_variables_stays_pending():
    create = client.post(
        "/api/workpieces/job-wp/jobs/bad-vars",
        json={
            "cron": "* * * * *",
            "runbook_name": "job-rb",
            "variables": {"name": "from-job", "oops": "bad"},
        },
    )
    assert create.status_code == 201

    trigger = client.post("/api/workpieces/job-wp/jobs/bad-vars/trigger")

    assert trigger.status_code == 201
    body = trigger.json()
    assert body["unknown_variables"] == ["oops"]
    assert body["task"]["status"] == "pending"
    assert body["task"]["error_summary"] == "unknown variables: oops"
    assert body["task"]["variables"]["oops"] == "bad"
    assert "auto_strategy" not in body["task"]["schedule"]
