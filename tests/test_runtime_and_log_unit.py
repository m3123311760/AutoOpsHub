"""轻量单元测试：日志后端选择、manifest 循环引用、DDL 脚本静态检查。"""

import re
import sys
from pathlib import Path

import bcrypt
import pytest

from autoopshub import auth_service
from autoopshub import executors
from autoopshub.auth_service import AuthService
from autoopshub.executors import build_runtime_override_argv, build_script_argv, dispatch_execution
from autoopshub.log_backend import LogBackendManager, LogRecordData, MemoryLogBackend
from autoopshub.manifest_resolve import ManifestItem, resolve_nested_defaults
from autoopshub.settings import APIKeySettings, AppSettings, RuntimeCommands, load_settings


def test_log_backend_falls_back_when_redis_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOOPSHUB_REDIS_URL", "redis://127.0.0.1:59999")
    mgr = LogBackendManager(load_settings())
    assert mgr.status.backend_type == "memory"
    assert mgr.status.redis_configured is True
    assert mgr.status.degrade_reason


def test_log_backend_defaults_to_memory_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOOPSHUB_REDIS_URL", raising=False)
    mgr = LogBackendManager(load_settings())
    assert mgr.status.backend_type == "memory"
    seq = mgr.backend.append(
        "wp",
        "t1",
        LogRecordData(task_id="t1", log_seq=0, ts="2026-01-01T00:00:00+00:00", level="info", message="hi"),
    )
    assert seq == 1
    rows = mgr.backend.read_after("wp", "t1", 0, 10)
    assert len(rows) == 1


def test_memory_log_backend_is_process_local_and_non_persistent() -> None:
    first = MemoryLogBackend()
    first.append(
        "wp",
        "t1",
        LogRecordData(task_id="t1", log_seq=0, ts="2026-01-01T00:00:00+00:00", level="info", message="kept"),
    )

    second = MemoryLogBackend()

    assert first.read_after("wp", "t1", 0, 10)
    assert second.read_after("wp", "t1", 0, 10) == []


def test_manifest_nested_default_cycle_raises() -> None:
    items = {
        "a": ManifestItem(name="a", default_value="{{ b }}"),
        "b": ManifestItem(name="b", default_value="{{ a }}"),
    }
    with pytest.raises(ValueError, match="循环引用|收敛"):
        resolve_nested_defaults(items, {})


def test_databases_init_sql_contains_required_tables() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = (root / "databases-init.sql").read_text(encoding="utf-8")
    for name in ("auth_users", "auth_jwt_sessions", "auth_api_keys"):
        assert f"CREATE TABLE IF NOT EXISTS {name}" in sql


def test_databases_init_sql_seeds_default_local_admin_without_plaintext_password() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = (root / "databases-init.sql").read_text(encoding="utf-8")

    assert "INSERT INTO auth_users (username, password_hash)" in sql
    match = re.search(r"VALUES \('admin', '([^']+)'\)", sql)
    assert match is not None
    assert match.group(1).startswith("$2")
    assert bcrypt.checkpw(b"ChangeMe123!", match.group(1).encode("utf-8"))
    assert "ON DUPLICATE KEY UPDATE id = id" in sql
    assert "ChangeMe123!" not in sql


def test_auth_password_context_verifies_seeded_admin_password() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = (root / "databases-init.sql").read_text(encoding="utf-8")
    match = re.search(r"VALUES \('admin', '([^']+)'\)", sql)
    assert match is not None

    assert auth_service.pwd_context.verify("ChangeMe123!", match.group(1))


def test_requirements_use_direct_bcrypt_without_passlib_adapter() -> None:
    root = Path(__file__).resolve().parents[1]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    assert "bcrypt>=4.0,<6" in requirements
    assert "passlib" not in requirements


def test_default_auth_settings_match_local_compose_without_predictable_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOOPSHUB_MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("AUTOOPSHUB_JWT_SECRET", raising=False)

    settings = load_settings()

    assert settings.mysql.password == "autoopshub"
    assert settings.jwt.secret == ""


def test_auth_service_requires_explicit_jwt_secret() -> None:
    settings = AppSettings()
    settings.jwt.secret = ""

    svc = AuthService(settings)

    with pytest.raises(Exception, match="AUTOOPSHUB_JWT_SECRET"):
        svc._require_jwt_secret()


def test_script_runtime_takes_precedence_over_shebang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executors.os, "name", "posix")
    settings = AppSettings(runtime_commands=RuntimeCommands(default_script_shell="/bin/sh"))
    rendered_path = Path("script.rendered")

    argv = build_script_argv(settings, rendered_path, "#!/usr/bin/env python3\nprint('ok')\n", "python3 -I")

    assert argv == ["python3", "-I", str(rendered_path)]


def test_unix_shebang_script_launches_rendered_file_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(executors.os, "name", "posix")
    settings = AppSettings(runtime_commands=RuntimeCommands(default_script_shell="/bin/sh"))
    rendered_path = Path("script.rendered")

    argv = build_script_argv(settings, rendered_path, "#!/usr/bin/env python3\nprint('ok')\n", None)

    assert argv == [str(rendered_path)]


def test_runtime_override_command_renders_system_and_short_aliases() -> None:
    argv = build_runtime_override_argv(
        "ansible-playbook -i {{ system.inventory_file }} {{ runbook_file }} --limit {{ host }}",
        {
            "system.inventory_file": "/tmp/inventory.ini",
            "system.runbook_file": "/tmp/playbook.yml",
            "host": "localhost",
        },
    )

    assert argv == [
        "ansible-playbook",
        "-i",
        "/tmp/inventory.ini",
        "/tmp/playbook.yml",
        "--limit",
        "localhost",
    ]


def test_ansible_dispatch_uses_system_set_runtime_override(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, cwd, env, timeout_sec, log):
        calls.append(argv)
        return executors.ExecResult(exit_code=0, error_summary="", command=argv)

    monkeypatch.setattr(executors, "run_subprocess_with_logging", fake_run)
    monkeypatch.setattr(executors, "check_tokens_available", lambda argv: type("Check", (), {"ok": True, "message": ""})())
    settings = AppSettings()
    runtime_dir = Path(".codex-tmp") / "test-runtime-command"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    result = dispatch_execution(
        settings,
        "Ansible",
        runtime_dir,
        runtime_dir / "playbook.yml",
        "---\n",
        None,
        {
            "system.set_runtime": "ansible-playbook -i {{ inventory_file }} {{ runbook_file }}",
            "system.inventory_file": str(runtime_dir / "inventory.ini"),
            "system.runbook_file": str(runtime_dir / "playbook.yml"),
        },
        30,
        lambda level, message: None,
    )

    assert result.exit_code == 0
    assert calls == [["ansible-playbook", "-i", str(runtime_dir / "inventory.ini"), str(runtime_dir / "playbook.yml")]]
    assert result.command == calls[0]


def test_empty_system_set_runtime_uses_default_terraform_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, cwd, env, timeout_sec, log):
        calls.append(argv)
        return executors.ExecResult(exit_code=0, error_summary="", command=argv)

    monkeypatch.setattr(executors, "run_subprocess_with_logging", fake_run)
    monkeypatch.setattr(executors, "check_command_available", lambda command: type("Check", (), {"ok": True, "message": ""})())
    settings = AppSettings(runtime_commands=RuntimeCommands(terraform_bin="terraform"))
    runtime_dir = Path(".codex-tmp") / "test-empty-runtime-command"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    rendered_path = runtime_dir / "main.tf"
    rendered_path.write_text("resource \"null_resource\" \"x\" {}\n", encoding="utf-8")

    result = dispatch_execution(
        settings,
        "Terraform",
        runtime_dir,
        rendered_path,
        "",
        None,
        {"system.set_runtime": ""},
        30,
        lambda level, message: None,
    )

    assert result.exit_code == 0
    assert calls == [
        ["terraform", "init", "-input=false"],
        ["terraform", "apply", "-input=false", "-auto-approve"],
    ]


def test_terraform_override_runs_init_and_moves_chdir_before_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, cwd, env, timeout_sec, log):
        calls.append(argv)
        return executors.ExecResult(exit_code=0, error_summary="", command=argv)

    monkeypatch.setattr(executors, "run_subprocess_with_logging", fake_run)
    monkeypatch.setattr(executors, "check_tokens_available", lambda argv: type("Check", (), {"ok": True, "message": ""})())
    settings = AppSettings(runtime_commands=RuntimeCommands(terraform_bin="terraform"))
    runtime_dir = Path(".codex-tmp") / "test-terraform-chdir"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    rendered_path = runtime_dir / "main.tf"
    rendered_path.write_text("resource \"null_resource\" \"x\" {}\n", encoding="utf-8")

    result = dispatch_execution(
        settings,
        "Terraform",
        runtime_dir,
        rendered_path,
        "",
        None,
        {
            "system.set_runtime": "terraform destroy -chdir={{ runbook_path }} -auto-approve",
            "system.runbook_path": str(runtime_dir),
        },
        30,
        lambda level, message: None,
    )

    assert result.exit_code == 0
    assert calls == [
        ["terraform", f"-chdir={runtime_dir}", "init", "-input=false"],
        ["terraform", f"-chdir={runtime_dir}", "destroy", "-auto-approve"],
    ]
    assert result.command == calls[1]


@pytest.mark.parametrize(
    ("runbook_type", "runtime_commands", "runbook_runtime", "expected_command"),
    [
        ("Terraform", RuntimeCommands(terraform_bin="autoopshub-missing-terraform"), None, "autoopshub-missing-terraform"),
        ("Ansible", RuntimeCommands(ansible_playbook_bin="autoopshub-missing-ansible"), None, "autoopshub-missing-ansible"),
        ("Script", RuntimeCommands(), "autoopshub-missing-shell", "autoopshub-missing-shell"),
    ],
)
def test_dispatch_marks_missing_runtime_command_unavailable(
    runbook_type: str,
    runtime_commands: RuntimeCommands,
    runbook_runtime: str | None,
    expected_command: str,
) -> None:
    runtime_dir = Path(".codex-tmp") / f"missing-{runbook_type.lower()}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    rendered_path = runtime_dir / "runbook.rendered"
    rendered_text = "" if runbook_type == "Script" else "echo ok\n"
    rendered_path.write_text(rendered_text, encoding="utf-8")
    logs: list[tuple[str, str]] = []

    result = dispatch_execution(
        AppSettings(runtime_commands=runtime_commands),
        runbook_type,
        runtime_dir,
        rendered_path,
        rendered_text,
        runbook_runtime,
        {},
        30,
        lambda level, message: logs.append((level, message)),
    )

    assert result.exit_code == 127
    assert result.command and result.command[0] == expected_command
    assert logs and logs[-1][0] == "error"


def test_subprocess_logging_captures_stdout_stderr_and_nonzero_exit() -> None:
    runtime_dir = Path(".codex-tmp") / "subprocess-nonzero"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    logs: list[tuple[str, str]] = []

    result = executors.run_subprocess_with_logging(
        [
            sys.executable,
            "-c",
            "import sys; print('hello-out'); print('hello-err', file=sys.stderr); sys.exit(3)",
        ],
        runtime_dir,
        None,
        30,
        lambda level, message: logs.append((level, message)),
    )

    assert result.exit_code == 3
    assert ("info", "hello-out") in logs
    assert ("error", "hello-err") in logs
    assert "命令退出码 3" in result.error_summary


def test_subprocess_timeout_kills_process_and_reports_124() -> None:
    runtime_dir = Path(".codex-tmp") / "subprocess-timeout"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    logs: list[tuple[str, str]] = []

    result = executors.run_subprocess_with_logging(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        runtime_dir,
        None,
        1,
        lambda level, message: logs.append((level, message)),
    )

    assert result.exit_code == 124
    assert result.error_summary == "runtime execution timeout"
    assert any("超时" in message for _level, message in logs)


def test_api_key_validation_uses_effective_minimum_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, str] = {}
    selected_prefixes: list[str] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            if sql.startswith("INSERT INTO auth_api_keys"):
                stored["id"] = str(params[0])
                stored["prefix"] = str(params[2])
                stored["hash"] = str(params[3])
                return
            if sql.startswith("SELECT id, key_hash"):
                selected_prefixes.append(str(params[0]))

        def fetchall(self) -> list[dict[str, object]]:
            if selected_prefixes and selected_prefixes[-1] == stored["prefix"]:
                return [{"id": stored["id"], "key_hash": stored["hash"], "revoked_at": None}]
            return []

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            return None

    class FakePasswordContext:
        def hash(self, value: str) -> str:
            return f"hashed:{value}"

        def verify(self, value: str, hashed: str) -> bool:
            return hashed == f"hashed:{value}"

    monkeypatch.setattr(auth_service.secrets, "token_urlsafe", lambda _: "abcdef")
    monkeypatch.setattr(auth_service, "mysql_connect", lambda settings: FakeConnection())
    monkeypatch.setattr(auth_service, "pwd_context", FakePasswordContext())
    svc = AuthService(AppSettings(api_key=APIKeySettings(prefix_length=1)))

    created = svc.create_api_key("short-prefix")
    principal = svc.validate_api_key(created["api_key"])

    assert created["prefix"] == "aoh_"
    assert selected_prefixes == ["aoh_"]
    assert principal is not None
