"""检查认证相关 MySQL 表是否存在（不执行 DDL）。"""

from __future__ import annotations

from typing import Any

REQUIRED_TABLES = ("auth_users", "auth_jwt_sessions", "auth_api_keys")


def mysql_connect(settings: Any) -> Any:
    import pymysql

    return pymysql.connect(
        host=settings.mysql.host,
        port=int(settings.mysql.port),
        user=settings.mysql.user,
        password=settings.mysql.password,
        database=settings.mysql.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def assert_auth_schema_present(settings: Any) -> None:
    """缺失表时抛出带明确信息的 RuntimeError。"""

    conn = mysql_connect(settings)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT TABLE_NAME FROM information_schema.tables
                WHERE table_schema=%s AND table_name IN (%s,%s,%s)
                """,
                (settings.mysql.database,) + REQUIRED_TABLES,
            )
            rows = cur.fetchall()
            names = {r["TABLE_NAME"] for r in rows}
    finally:
        conn.close()
    missing = [t for t in REQUIRED_TABLES if t not in names]
    if missing:
        raise RuntimeError(
            "认证数据库 schema 不完整，请先执行项目根目录 databases-init.sql 初始化。"
            f" 缺失表: {', '.join(missing)}"
        )
