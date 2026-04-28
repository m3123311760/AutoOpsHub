"""轻量单元测试：日志后端选择、manifest 循环引用、DDL 脚本静态检查。"""

import re
from pathlib import Path

import bcrypt
import pytest

from autoopshub import auth_service
from autoopshub import executors
from autoopshub.auth_service import AuthService
from autoopshub.executors import build_script_argv
from autoopshub.log_backend import LogBackendManager, LogRecordData
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


def test_requirements_pin_bcrypt_below_passlib_incompatible_major() -> None:
    root = Path(__file__).resolve().parents[1]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    assert "bcrypt>=4.0,<5" in requirements


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
