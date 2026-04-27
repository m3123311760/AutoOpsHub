"""轻量单元测试：日志后端选择、manifest 循环引用、DDL 脚本静态检查。"""

from pathlib import Path

import pytest

from autoopshub.log_backend import LogBackendManager, LogRecordData
from autoopshub.manifest_resolve import ManifestItem, resolve_nested_defaults
from autoopshub.settings import load_settings


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
