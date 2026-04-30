import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import starlette.requests

from autoopshub.executors import ExecResult

TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)
os.environ["AUTOOPSHUB_REQUIRE_AUTH"] = "false"

from main import app
import main

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
    assert create.json()["manifest_summary"] == {"variables": 9}

    list_resp = client.get("/api/workpieces/demo/runbooks")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "deploy"
    assert items[0]["type"] == "Script"

    detail_resp = client.get("/api/workpieces/demo/runbooks/deploy")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["content"] == "echo {{env}} {{region}}"
    assert detail_resp.json()["manifest_summary"] == {"variables": 9}

    manifest_get = client.get("/api/workpieces/demo/runbooks/deploy/manifest")
    assert manifest_get.status_code == 200
    names = [x["name"] for x in manifest_get.json()["items"]]
    assert {"env", "region"}.issubset(set(names))

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


def test_runbook_manifest_auto_declares_all_system_reserved_variables():
    create = client.post(
        "/api/workpieces/demo/runbooks/system-vars",
        json={
            "type": "Ansible",
            "description": "system vars",
            "content": "dest: {{ system.output }}/result.txt\nhost: {{ system.host }}\n",
        },
    )
    assert create.status_code == 201

    manifest_get = client.get("/api/workpieces/demo/runbooks/system-vars/manifest")
    assert manifest_get.status_code == 200
    items = {item["name"]: item for item in manifest_get.json()["items"]}

    assert {
        "system.set_runtime",
        "system.output",
        "system.runbook_file",
        "system.env_file",
        "system.inventory_file",
        "system.host",
        "system.runbook_path",
    }.issubset(items)
    assert items["system.output"]["direction"] == "output"
    assert items["system.runbook_file"]["direction"] == "output"
    assert items["system.runbook_path"]["direction"] == "output"
    assert items["system.host"]["direction"] == "input"

    update = client.post(
        "/api/workpieces/demo/runbooks/system-vars/manifest",
        json={
            "manifest": [
                {
                    "name": "system.host",
                    "display_name": "Target Host",
                    "direction": "input",
                    "required": False,
                    "default_value": "localhost",
                }
            ]
        },
    )
    assert update.status_code == 200
    updated = {item["name"]: item for item in update.json()["items"]}
    assert updated["system.host"]["display_name"] == "Target Host"
    assert updated["system.host"]["default_value"] == "localhost"


def test_existing_manifest_is_backfilled_with_system_reserved_variables():
    create = client.post(
        "/api/workpieces/demo/runbooks/legacy-system-vars",
        json={
            "type": "Script",
            "content": "echo {{ custom }}",
            "runtime": "python",
        },
    )
    assert create.status_code == 201
    main._save_manifest(
        "demo",
        "legacy-system-vars",
        [
            main.ManifestVariable(
                name="custom",
                display_name="custom",
                direction=main.ManifestVariableDirection.INPUT,
                required=False,
                default_value="",
            )
        ],
    )

    manifest_get = client.get("/api/workpieces/demo/runbooks/legacy-system-vars/manifest")

    assert manifest_get.status_code == 200
    names = {item["name"] for item in manifest_get.json()["items"]}
    assert "custom" in names
    assert "system.inventory_file" in names
    assert "system.runbook_path" in names


def test_system_output_directory_exists_before_runtime_dispatch(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/output-dir")
    create_wp = client.post("/api/workpieces/output-dir", json={"description": "output"})
    assert create_wp.status_code in (201, 409)

    create = client.post(
        "/api/workpieces/output-dir/runbooks/write-output",
        json={
            "type": "Script",
            "content": "echo {{ system.output }}",
            "runtime": "python",
        },
    )
    assert create.status_code == 201

    seen_output_dirs: list[Path] = []

    def fake_dispatch_execution(*args, **kwargs):
        variables = args[6]
        output_dir = Path(variables["system.output"])
        seen_output_dirs.append(output_dir)
        assert output_dir.is_dir()
        return ExecResult(exit_code=0, error_summary="")

    monkeypatch.setattr(main, "dispatch_execution", fake_dispatch_execution)

    trigger = client.post("/api/workpieces/output-dir/runbooks/write-output/trigger", json={"variables": {}})
    assert trigger.status_code == 201
    confirm = client.post(f"/api/workpieces/output-dir/tasks/{trigger.json()['task']['task_id']}/confirm")

    assert confirm.status_code == 202
    assert seen_output_dirs


def test_auto_execute_can_be_scheduled_after_trigger_response(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/auto-bg")
    create_wp = client.post("/api/workpieces/auto-bg", json={"description": "auto"})
    assert create_wp.status_code in (201, 409)
    create = client.post(
        "/api/workpieces/auto-bg/runbooks/run-script",
        json={"type": "Script", "content": "echo hello", "runtime": "bash"},
    )
    assert create.status_code == 201

    scheduled: list[tuple[object, tuple[object, ...]]] = []

    class FakeBackgroundTasks:
        def add_task(self, func, *args):
            scheduled.append((func, args))

    def fail_if_sync_execute(*args, **kwargs):
        raise AssertionError("auto_execute should be scheduled, not run synchronously")

    monkeypatch.setattr(main, "_execute_task", fail_if_sync_execute)
    task, _manifest, _missing, _unknown = main._create_task_from_runbook(
        "auto-bg",
        "run-script",
        {},
        main.TaskSource.MANUAL,
        background_tasks=FakeBackgroundTasks(),
    )

    assert task.status == main.TaskStatus.READY
    assert scheduled
    assert scheduled[0][1][0] == "auto-bg"
    assert scheduled[0][1][1].task_id == task.task_id


def test_rerun_task_with_overrides_creates_new_task_and_preserves_original(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/rerun-demo")
    create_wp = client.post("/api/workpieces/rerun-demo", json={"description": "rerun"})
    assert create_wp.status_code in (201, 409)
    create = client.post(
        "/api/workpieces/rerun-demo/runbooks/run-script",
        json={"type": "Script", "content": "echo {{ name }} {{ region }}", "runtime": "bash"},
    )
    assert create.status_code == 201

    monkeypatch.setattr(main, "dispatch_execution", lambda *args, **kwargs: ExecResult(exit_code=0, error_summary=""))
    original = client.post(
        "/api/workpieces/rerun-demo/runbooks/run-script/trigger",
        json={"variables": {"name": "old", "region": "east"}},
    )
    assert original.status_code == 201
    original_task = original.json()["task"]

    rerun = client.post(f"/api/tasks/{original_task['task_id']}/rerun", json={"variables": {"region": "west"}})

    assert rerun.status_code == 201
    new_task = rerun.json()["task"]
    assert new_task["task_id"] != original_task["task_id"]
    assert new_task["runbook_name"] == "run-script"
    assert new_task["variables"] == {"name": "old", "region": "west"}
    assert client.get(f"/api/workpieces/rerun-demo/tasks/{original_task['task_id']}").json()["variables"] == {
        "name": "old",
        "region": "east",
    }


def test_rerun_task_not_found_returns_404():
    rerun = client.post("/api/tasks/not-exists/rerun", json={"variables": {}})

    assert rerun.status_code == 404


def test_rerun_task_without_body_uses_original_variables(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/rerun-empty")
    create_wp = client.post("/api/workpieces/rerun-empty", json={"description": "rerun"})
    assert create_wp.status_code in (201, 409)
    create = client.post(
        "/api/workpieces/rerun-empty/runbooks/run-script",
        json={"type": "Script", "content": "echo {{ name }}", "runtime": "bash"},
    )
    assert create.status_code == 201
    monkeypatch.setattr(main, "dispatch_execution", lambda *args, **kwargs: ExecResult(exit_code=0, error_summary=""))
    original = client.post(
        "/api/workpieces/rerun-empty/runbooks/run-script/trigger",
        json={"variables": {"name": "same"}},
    )
    assert original.status_code == 201

    rerun = client.post(f"/api/tasks/{original.json()['task']['task_id']}/rerun")

    assert rerun.status_code == 201
    assert rerun.json()["task"]["variables"] == {"name": "same"}


def test_rerun_terraform_file_package_can_override_runtime_command(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/rerun-terraform")
    create_wp = client.post("/api/workpieces/rerun-terraform", json={"description": "tf rerun"})
    assert create_wp.status_code in (201, 409)
    create = client.post(
        "/api/workpieces/rerun-terraform/runbooks/tf",
        data={"type": "Terraform", "entry_file": "main.tf"},
        files=[("files", ("main.tf", b"resource \"null_resource\" \"{{ name }}\" {}\n", "text/plain"))],
    )
    assert create.status_code == 201

    seen_commands: list[str] = []

    def fake_dispatch_execution(*args, **kwargs):
        variables = args[6]
        seen_commands.append(str(variables.get("system.set_runtime", "")))
        return ExecResult(exit_code=0, error_summary="", command=str(variables.get("system.set_runtime", "")).split())

    monkeypatch.setattr(main, "dispatch_execution", fake_dispatch_execution)
    original = client.post(
        "/api/workpieces/rerun-terraform/runbooks/tf/trigger",
        json={"variables": {"name": "demo", "system.set_runtime": "terraform apply -auto-approve"}},
    )
    assert original.status_code == 201

    rerun = client.post(
        f"/api/tasks/{original.json()['task']['task_id']}/rerun",
        json={"variables": {"system.set_runtime": "terraform destroy -auto-approve"}},
    )

    assert rerun.status_code == 201
    assert rerun.json()["task"]["variables"] == {
        "name": "demo",
        "system.set_runtime": "terraform destroy -auto-approve",
    }
    assert seen_commands[-2:] == ["terraform apply -auto-approve", "terraform destroy -auto-approve"]


def test_rerun_terraform_file_package_inherits_previous_runtime_state(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/rerun-terraform-state")
    create_wp = client.post("/api/workpieces/rerun-terraform-state", json={"description": "tf rerun state"})
    assert create_wp.status_code in (201, 409)
    create = client.post(
        "/api/workpieces/rerun-terraform-state/runbooks/tf",
        data={"type": "Terraform", "entry_file": "main.tf"},
        files=[("files", ("main.tf", b"resource \"null_resource\" \"{{ name }}\" {}\n", "text/plain"))],
    )
    assert create.status_code == 201

    runtime_dirs: list[Path] = []

    def fake_dispatch_execution(*args, **kwargs):
        runtime_dir = args[2]
        variables = args[6]
        runtime_dirs.append(runtime_dir)
        if "apply" in str(variables.get("system.set_runtime", "")):
            (runtime_dir / "terraform.tfstate").write_text('{"resources":[]}', encoding="utf-8")
            (runtime_dir / ".terraform").mkdir()
            (runtime_dir / ".terraform" / "providers.lock").write_text("provider cache", encoding="utf-8")
        else:
            assert (runtime_dir / "terraform.tfstate").read_text(encoding="utf-8") == '{"resources":[]}'
            assert (runtime_dir / ".terraform" / "providers.lock").read_text(encoding="utf-8") == "provider cache"
        return ExecResult(exit_code=0, error_summary="", command=str(variables.get("system.set_runtime", "")).split())

    monkeypatch.setattr(main, "dispatch_execution", fake_dispatch_execution)
    original = client.post(
        "/api/workpieces/rerun-terraform-state/runbooks/tf/trigger",
        json={"variables": {"name": "demo", "system.set_runtime": "terraform apply -auto-approve"}},
    )
    assert original.status_code == 201

    rerun = client.post(
        f"/api/tasks/{original.json()['task']['task_id']}/rerun",
        json={"variables": {"system.set_runtime": "terraform destroy -auto-approve"}},
    )

    assert rerun.status_code == 201
    assert len(runtime_dirs) == 2
    assert runtime_dirs[1] != runtime_dirs[0]
    assert client.get(f"/api/workpieces/rerun-terraform-state/tasks/{rerun.json()['task']['task_id']}").json()["status"] == "success"
    assert (runtime_dirs[1] / "terraform.tfstate").read_text(encoding="utf-8") == '{"resources":[]}'
    assert (runtime_dirs[1] / ".terraform" / "providers.lock").read_text(encoding="utf-8") == "provider cache"


def test_system_set_runtime_default_renders_runtime_paths_into_schedule(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/runtime-command")
    create_wp = client.post("/api/workpieces/runtime-command", json={"description": "runtime"})
    assert create_wp.status_code in (201, 409)

    create = client.post(
        "/api/workpieces/runtime-command/runbooks/custom-ansible",
        json={
            "type": "Ansible",
            "content": "---\n- hosts: localhost\n  tasks: []\n",
        },
    )
    assert create.status_code == 201
    manifest = client.get("/api/workpieces/runtime-command/runbooks/custom-ansible/manifest")
    items = manifest.json()["items"]
    for item in items:
        if item["name"] == "system.set_runtime":
            item["default_value"] = "ansible-playbook -i {{ inventory_file }} {{ runbook_file }} --limit {{ host }}"
        if item["name"] == "system.host":
            item["default_value"] = "localhost"
    update = client.post("/api/workpieces/runtime-command/runbooks/custom-ansible/manifest", json={"manifest": items})
    assert update.status_code == 200

    def fake_dispatch_execution(*args, **kwargs):
        variables = args[6]
        command = variables["system.set_runtime"].split()
        return ExecResult(exit_code=0, error_summary="", command=command)

    monkeypatch.setattr(main, "dispatch_execution", fake_dispatch_execution)

    trigger = client.post("/api/workpieces/runtime-command/runbooks/custom-ansible/trigger", json={"variables": {}})
    assert trigger.status_code == 201
    confirm = client.post(f"/api/workpieces/runtime-command/tasks/{trigger.json()['task']['task_id']}/confirm")
    body = confirm.json()["task"]

    assert confirm.status_code == 202
    assert body["schedule"]["runtime_command"][0] == "ansible-playbook"
    assert "--limit" in body["schedule"]["runtime_command"]
    assert "localhost" in body["schedule"]["runtime_command"]
    assert body["schedule"]["rendered_file"] in body["schedule"]["runtime_command"]


def test_script_system_set_runtime_first_line_is_runtime_not_script_content(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/script-runtime-line")
    create_wp = client.post("/api/workpieces/script-runtime-line", json={"description": "script runtime"})
    assert create_wp.status_code in (201, 409)

    create = client.post(
        "/api/workpieces/script-runtime-line/runbooks/run-script",
        json={
            "type": "Script",
            "content": "{{ system.set_runtime }}\necho hello\n",
        },
    )
    assert create.status_code == 201
    manifest = client.get("/api/workpieces/script-runtime-line/runbooks/run-script/manifest")
    items = manifest.json()["items"]
    for item in items:
        if item["name"] == "system.set_runtime":
            item["default_value"] = "custom-shell"
    update = client.post("/api/workpieces/script-runtime-line/runbooks/run-script/manifest", json={"manifest": items})
    assert update.status_code == 200

    seen: dict[str, object] = {}

    def fake_dispatch_execution(*args, **kwargs):
        seen["rendered_text"] = args[4]
        seen["runbook_runtime"] = args[5]
        return ExecResult(exit_code=0, error_summary="", command=["custom-shell", str(args[3])])

    monkeypatch.setattr(main, "dispatch_execution", fake_dispatch_execution)

    trigger = client.post("/api/workpieces/script-runtime-line/runbooks/run-script/trigger", json={"variables": {}})
    assert trigger.status_code == 201
    confirm = client.post(f"/api/workpieces/script-runtime-line/tasks/{trigger.json()['task']['task_id']}/confirm")

    assert confirm.status_code == 202
    assert seen["runbook_runtime"] == "custom-shell"
    assert seen["rendered_text"] == "echo hello"


def test_multipart_runbook_create_missing_files_and_path_validation():
    client.delete("/api/workpieces/file-packages")
    create_wp = client.post("/api/workpieces/file-packages", json={"description": "files"})
    assert create_wp.status_code in (201, 409)

    missing_files = client.post(
        "/api/workpieces/file-packages/runbooks/tf-empty",
        data={"type": "Terraform", "description": "empty"},
    )
    assert missing_files.status_code == 422

    unsafe_path = client.post(
        "/api/workpieces/file-packages/runbooks/tf-unsafe",
        data={"type": "Terraform"},
        files=[("files", ("../main.tf", b"resource \"null_resource\" \"x\" {}", "text/plain"))],
    )
    assert unsafe_path.status_code == 422

    create = client.post(
        "/api/workpieces/file-packages/runbooks/tf-package",
        data={
            "type": "Terraform",
            "description": "multi file",
            "entry_file": "main.tf",
        },
        files=[
            ("files", ("main.tf", b"resource \"null_resource\" \"{{ name }}\" {}\n", "text/plain")),
            ("files", ("modules/network/main.tf", b"output \"host\" { value = \"{{ system.host }}\" }\n", "text/plain")),
        ],
    )

    assert create.status_code == 201
    body = create.json()
    assert body["content_mode"] == "files"
    assert body["entry_file"] == "main.tf"
    assert body["files_summary"]["count"] == 2
    assert body["files_summary"]["paths"] == ["main.tf", "modules/network/main.tf"]

    detail = client.get("/api/workpieces/file-packages/runbooks/tf-package")
    assert detail.status_code == 200
    assert detail.json()["content_mode"] == "files"

    listed = client.get("/api/workpieces/file-packages/runbooks")
    assert listed.status_code == 200
    item = next(item for item in listed.json()["items"] if item["name"] == "tf-package")
    assert item["content_mode"] == "files"
    assert item["files_summary"]["count"] == 2


def test_multipart_runbook_returns_clear_error_when_parser_dependency_is_missing(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/file-parser-missing")
    create_wp = client.post("/api/workpieces/file-parser-missing", json={"description": "files"})
    assert create_wp.status_code in (201, 409)

    monkeypatch.setattr(starlette.requests, "parse_options_header", None)

    create = client.post(
        "/api/workpieces/file-parser-missing/runbooks/tf-package",
        data={"type": "Terraform"},
        files=[("files", ("main.tf", b"resource \"null_resource\" \"x\" {}\n", "text/plain"))],
    )

    assert create.status_code == 503
    assert "python-multipart" in create.json()["detail"]


def test_file_package_manifest_scans_multiple_text_files_and_skips_binary():
    client.delete("/api/workpieces/file-manifest")
    create_wp = client.post("/api/workpieces/file-manifest", json={"description": "manifest"})
    assert create_wp.status_code in (201, 409)

    create = client.post(
        "/api/workpieces/file-manifest/runbooks/tf-vars",
        data={"type": "Terraform", "entry_file": "main.tf"},
        files=[
            ("files", ("main.tf", b"resource \"null_resource\" \"{{ app }}\" {}\n", "text/plain")),
            ("files", ("vars.tfvars", b"region = \"{{ region }}\"\nhost = \"{{ system.host }}\"\n", "text/plain")),
            ("files", ("asset.bin", b"\xff\x00\xfe", "application/octet-stream")),
        ],
    )

    assert create.status_code == 201
    manifest = client.get("/api/workpieces/file-manifest/runbooks/tf-vars/manifest")
    assert manifest.status_code == 200
    names = {item["name"] for item in manifest.json()["items"]}
    assert {"app", "region", "system.host", "system.set_runtime", "system.runbook_path"}.issubset(names)

    items = manifest.json()["items"]
    for item in items:
        if item["name"] == "system.host":
            item["default_value"] = "localhost"
    update = client.post("/api/workpieces/file-manifest/runbooks/tf-vars/manifest", json={"manifest": items})
    assert update.status_code == 200
    updated = {item["name"]: item for item in update.json()["items"]}
    assert updated["system.host"]["default_value"] == "localhost"


def test_terraform_file_package_execution_copies_and_renders_without_writing_back(monkeypatch: pytest.MonkeyPatch):
    client.delete("/api/workpieces/file-exec")
    create_wp = client.post("/api/workpieces/file-exec", json={"description": "exec"})
    assert create_wp.status_code in (201, 409)

    create = client.post(
        "/api/workpieces/file-exec/runbooks/tf-exec",
        data={"type": "Terraform", "entry_file": "main.tf"},
        files=[
            ("files", ("main.tf", b"resource \"null_resource\" \"{{ name }}\" {}\n", "text/plain")),
            ("files", ("modules/network/main.tf", b"output \"x\" { value = \"{{ system.host }}\" }\n", "text/plain")),
        ],
    )
    assert create.status_code == 201

    manifest = client.get("/api/workpieces/file-exec/runbooks/tf-exec/manifest")
    items = manifest.json()["items"]
    for item in items:
        if item["name"] == "system.set_runtime":
            item["default_value"] = "terraform-custom {{ runbook_path }}"
        if item["name"] == "system.host":
            item["default_value"] = "localhost"
    assert client.post("/api/workpieces/file-exec/runbooks/tf-exec/manifest", json={"manifest": items}).status_code == 200

    seen: dict[str, object] = {}

    def fake_dispatch_execution(*args, **kwargs):
        runtime_dir = Path(args[2])
        seen["runtime_dir"] = runtime_dir
        seen["rendered_text"] = args[4]
        seen["variables"] = args[6]
        assert (runtime_dir / "main.tf").read_text(encoding="utf-8") == 'resource "null_resource" "demo" {}'
        assert (runtime_dir / "modules" / "network" / "main.tf").read_text(encoding="utf-8") == 'output "x" { value = "localhost" }'
        (runtime_dir / ".terraform").mkdir()
        return ExecResult(exit_code=0, error_summary="", command=["terraform-custom", str(runtime_dir)])

    monkeypatch.setattr(main, "dispatch_execution", fake_dispatch_execution)

    trigger = client.post("/api/workpieces/file-exec/runbooks/tf-exec/trigger", json={"variables": {"name": "demo"}})
    assert trigger.status_code == 201
    confirm = client.post(f"/api/workpieces/file-exec/tasks/{trigger.json()['task']['task_id']}/confirm")
    assert confirm.status_code == 202
    task = confirm.json()["task"]

    assert task["schedule"]["content_mode"] == "files"
    assert task["schedule"]["entry_file"] == "main.tf"
    assert task["schedule"]["runtime_command"][0] == "terraform-custom"
    assert seen["rendered_text"] == ""

    package_dir = main._runbook_files_dir("file-exec", "tf-exec")
    assert not (package_dir / ".terraform").exists()
    assert "{{ name }}" in (package_dir / "main.tf").read_text(encoding="utf-8")
