"""从环境变量加载应用配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class RuntimeCommands:
    """Terraform / Ansible / 默认 Script 包装命令。"""

    terraform_bin: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_TERRAFORM_BIN", "terraform"))
    ansible_playbook_bin: str = field(
        default_factory=lambda: os.getenv("AUTOOPSHUB_ANSIBLE_PLAYBOOK_BIN", "ansible-playbook")
    )
    default_script_shell: str = field(
        default_factory=lambda: os.getenv("AUTOOPSHUB_DEFAULT_SCRIPT_SHELL", "/bin/sh")
    )


@dataclass
class RedisSettings:
    url: str | None = field(default_factory=lambda: os.getenv("AUTOOPSHUB_REDIS_URL") or None)
    stream_prefix: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_REDIS_LOG_PREFIX", "autoopshub:logs:"))


@dataclass
class MySQLSettings:
    host: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_MYSQL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("AUTOOPSHUB_MYSQL_PORT", 3306))
    user: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_MYSQL_USER", "autoopshub"))
    password: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_MYSQL_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_MYSQL_DATABASE", "autoopshub"))


@dataclass
class LDAPSettings:
    uri: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_LDAP_URI", "ldap://127.0.0.1:389"))
    bind_dn_template: str | None = field(
        default_factory=lambda: os.getenv("AUTOOPSHUB_LDAP_BIND_DN_TEMPLATE") or None
    )
    base_dn: str | None = field(default_factory=lambda: os.getenv("AUTOOPSHUB_LDAP_BASE_DN") or None)
    connect_timeout_seconds: float = field(default_factory=lambda: _env_float("AUTOOPSHUB_LDAP_CONNECT_TIMEOUT", 5.0))


@dataclass
class ADSettings:
    """与 LDAP 类似的 AD 连接参数（ldap3 统一协议）。"""

    uri: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_AD_URI", "ldap://127.0.0.1:389"))
    bind_dn_template: str | None = field(
        default_factory=lambda: os.getenv("AUTOOPSHUB_AD_BIND_DN_TEMPLATE") or None
    )
    base_dn: str | None = field(default_factory=lambda: os.getenv("AUTOOPSHUB_AD_BASE_DN") or None)
    connect_timeout_seconds: float = field(default_factory=lambda: _env_float("AUTOOPSHUB_AD_CONNECT_TIMEOUT", 5.0))


@dataclass
class JWTSettings:
    secret: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_JWT_SECRET", ""))
    algorithm: str = field(default_factory=lambda: os.getenv("AUTOOPSHUB_JWT_ALGORITHM", "HS256"))
    expire_minutes: int = field(default_factory=lambda: _env_int("AUTOOPSHUB_JWT_EXPIRE_MINUTES", 60))


@dataclass
class APIKeySettings:
    """API Key 前缀长度等策略。"""

    prefix_length: int = field(default_factory=lambda: _env_int("AUTOOPSHUB_API_KEY_PREFIX_LEN", 8))


@dataclass
class AppSettings:
    """聚合配置。"""

    runtime_commands: RuntimeCommands = field(default_factory=RuntimeCommands)
    task_execution_timeout_seconds: int = field(
        default_factory=lambda: _env_int("AUTOOPSHUB_TASK_EXEC_TIMEOUT_SECONDS", 3600)
    )
    redis: RedisSettings = field(default_factory=RedisSettings)
    mysql: MySQLSettings = field(default_factory=MySQLSettings)
    ldap: LDAPSettings = field(default_factory=LDAPSettings)
    ad: ADSettings = field(default_factory=ADSettings)
    jwt: JWTSettings = field(default_factory=JWTSettings)
    api_key: APIKeySettings = field(default_factory=APIKeySettings)
    require_auth: bool = field(default_factory=lambda: _env_bool("AUTOOPSHUB_REQUIRE_AUTH", False))

    def public_dict(self) -> dict[str, Any]:
        """用于调试端点，避免泄露密钥。"""

        return {
            "task_execution_timeout_seconds": self.task_execution_timeout_seconds,
            "redis_configured": bool(self.redis.url),
            "mysql_configured": bool(self.mysql.password or self.mysql.user),
            "require_auth": self.require_auth,
        }


def load_settings() -> AppSettings:
    return AppSettings()
