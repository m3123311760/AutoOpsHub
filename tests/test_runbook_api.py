import os
from pathlib import Path

from fastapi.testclient import TestClient

TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)
os.environ["AUTOOPSHUB_REQUIRE_AUTH"] = "false"

from main import app

client = TestClient(app)


def setup_module() -> None:
    client.delete("/api/workpieces/demo")
    create = client.post("/api/workpieces/demo", json={"description": "demo"})
    assert create.status_code in (201, 409)


def test_runbook_create_list_manifest_and_delete():
    create = client.post(
        "/api/workpieces/demo/runbooks/deploy",
        json={
            "type": "Script",
            "description": "deploy",
            "content": "echo {{env}} {{region}}",
            "runtime": "python",
            "manifest": [{"name": "env", "direction": "input", "required": True}],
        },
    )
    assert create.status_code == 201
    assert create.json()["content"] == "echo {{env}} {{region}}"
    assert create.json()["runtime"] == "python"
    assert create.json()["manifest_summary"] == {"variables": 2}

    list_resp = client.get("/api/workpieces/demo/runbooks")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "deploy"
    assert items[0]["type"] == "Script"

    detail_resp = client.get("/api/workpieces/demo/runbooks/deploy")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["content"] == "echo {{env}} {{region}}"
    assert detail_resp.json()["manifest_summary"] == {"variables": 2}

    manifest_get = client.get("/api/workpieces/demo/runbooks/deploy/manifest")
    assert manifest_get.status_code == 200
    names = [x["name"] for x in manifest_get.json()["items"]]
    assert set(names) == {"env", "region"}

    manifest_update = client.post(
        "/api/workpieces/demo/runbooks/deploy/manifest",
        json={"manifest": [{"name": "region", "direction": "output"}]},
    )
    assert manifest_update.status_code == 200
    updated_names = [x["name"] for x in manifest_update.json()["items"]]
    assert "region" in updated_names

    delete_resp = client.delete("/api/workpieces/demo/runbooks/deploy")
    assert delete_resp.status_code == 204


def test_script_runtime_and_workflow_validations():
    missing_runtime = client.post(
        "/api/workpieces/demo/runbooks/r1",
        json={"type": "Script", "content": "echo 1"},
    )
    # Script 可不强制创建时指定 runtime（由默认策略或 system.set_runtime 解析）
    assert missing_runtime.status_code == 201

    powershell_runtime = client.post(
        "/api/workpieces/demo/runbooks/r2",
        json={"type": "Script", "content": "echo 1", "runtime": "powershell"},
    )
    assert powershell_runtime.status_code == 422

    workflow_missing_ref = client.post(
        "/api/workpieces/demo/runbooks/wf1",
        json={
            "type": "Workflow",
            "content": "steps:\n  - include: missing_rb\n",
        },
    )
    assert workflow_missing_ref.status_code == 422

    workflow_list_document = client.post(
        "/api/workpieces/demo/runbooks/wf-list",
        json={"type": "Workflow", "content": "[]\n"},
    )
    assert workflow_list_document.status_code == 422

    workflow_scalar_document = client.post(
        "/api/workpieces/demo/runbooks/wf-scalar",
        json={"type": "Workflow", "content": "hello\n"},
    )
    assert workflow_scalar_document.status_code == 422

    client.post(
        "/api/workpieces/demo/runbooks/s1",
        json={"type": "Script", "content": "echo {{a}}", "runtime": "python"},
    )
    ok_workflow = client.post(
        "/api/workpieces/demo/runbooks/wf2",
        json={
            "type": "Workflow",
            "content": "steps:\n  - include: s1\n",
        },
    )
    assert ok_workflow.status_code == 201

    client.post(
        "/api/workpieces/demo/runbooks/wa",
        json={"type": "Workflow", "content": "steps:\n  - include: wb\n"},
    )
    cycle = client.post(
        "/api/workpieces/demo/runbooks/wb",
        json={"type": "Workflow", "content": "steps:\n  - include: wa\n"},
    )
    assert cycle.status_code == 422

    unknown_manifest = client.post(
        "/api/workpieces/demo/runbooks/r3",
        json={
            "type": "Script",
            "content": "echo {{ok}}",
            "runtime": "python",
            "manifest": [{"name": "not_exists", "direction": "input"}],
        },
    )
    assert unknown_manifest.status_code == 422
