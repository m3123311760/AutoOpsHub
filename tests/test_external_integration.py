import os
import threading
import time
from pathlib import Path

import pytest

from autoopshub.auth_service import AuthService, pwd_context
from autoopshub.log_backend import LogBackendManager, LogRecordData
from autoopshub.settings import AppSettings


pytestmark = pytest.mark.integration


def _require_integration() -> None:
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("set RUN_INTEGRATION=1 to run Docker/Testcontainers integration tests")


def test_redis_stream_log_backend_with_testcontainers(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_integration()
    redis_mod = pytest.importorskip("testcontainers.redis")
    RedisContainer = redis_mod.RedisContainer

    with RedisContainer("redis:7-alpine") as redis:
        url = redis.get_connection_url()
        monkeypatch.setenv("AUTOOPSHUB_REDIS_URL", url)
        mgr = LogBackendManager(AppSettings())
        assert mgr.status.backend_type == "redis"

        seq1 = mgr.backend.append("wp", "task-1", LogRecordData("task-1", 0, "2026-01-01T00:00:00+00:00", "info", "one"))
        seq2 = mgr.backend.append("wp", "task-1", LogRecordData("task-1", 0, "2026-01-01T00:00:01+00:00", "error", "two"))

        assert (seq1, seq2) == (1, 2)
        assert [row["message"] for row in mgr.backend.read_after("wp", "task-1", 1, 10)] == ["two"]

        stop = threading.Event()
        seen: list[dict[str, object]] = []

        def consume() -> None:
            for row in mgr.backend.subscribe_existing_then_poll("wp", "task-2", 0.1, stop):
                seen.append(row)
                stop.set()
                break

        thread = threading.Thread(target=consume, daemon=True)
        thread.start()
        time.sleep(0.2)
        mgr.backend.append("wp", "task-2", LogRecordData("task-2", 0, "2026-01-01T00:00:02+00:00", "info", "live"))
        thread.join(timeout=5)

        assert seen and seen[0]["message"] == "live"


def test_mysql_local_auth_with_testcontainers(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_integration()
    mysql_mod = pytest.importorskip("testcontainers.mysql")
    MySqlContainer = mysql_mod.MySqlContainer

    root = Path(__file__).resolve().parents[1]
    sql = (root / "databases-init.sql").read_text(encoding="utf-8")

    with MySqlContainer("mysql:8.0") as mysql:
        import pymysql

        conn_url = mysql.get_connection_url()
        assert conn_url.startswith("mysql")
        host = mysql.get_container_host_ip()
        port = int(mysql.get_exposed_port(3306))
        user = mysql.username
        password = mysql.password
        database = mysql.dbname
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database, autocommit=True)
        try:
            with conn.cursor() as cur:
                for statement in [part.strip() for part in sql.split(";") if part.strip()]:
                    cur.execute(statement)
                cur.execute(
                    "UPDATE auth_users SET password_hash=%s WHERE username='admin'",
                    (pwd_context.hash("correct-password"),),
                )
        finally:
            conn.close()

        settings = AppSettings()
        settings.mysql.host = host
        settings.mysql.port = port
        settings.mysql.user = user
        settings.mysql.password = password
        settings.mysql.database = database
        settings.jwt.secret = "integration-secret"

        svc = AuthService(settings)
        assert svc.login("local", "admin", "correct-password")["access_token"]
        with pytest.raises(Exception):
            svc.login("local", "admin", "bad-password")
        with pytest.raises(Exception):
            svc.login("local", "missing", "correct-password")


def test_ldap_and_ad_with_testcontainers_connection_failure_paths() -> None:
    _require_integration()
    pytest.importorskip("testcontainers.core.container")

    settings = AppSettings()
    settings.ldap.uri = "ldap://127.0.0.1:1"
    settings.ad.uri = "ldap://127.0.0.1:1"
    settings.jwt.secret = "integration-secret"
    svc = AuthService(settings)

    with pytest.raises(Exception, match="LDAP 认证源不可用"):
        svc.login("ldap", "admin", "bad")
    with pytest.raises(Exception, match="AD 认证源不可用"):
        svc.login("ad", "admin", "bad")
