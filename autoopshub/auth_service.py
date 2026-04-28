"""认证、JWT 与 API Key。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt
from fastapi import HTTPException, status

from autoopshub.db_schema import mysql_connect
from autoopshub.settings import AppSettings

class BcryptPasswordContext:
    def hash(self, value: str) -> str:
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    def verify(self, value: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(value.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False


pwd_context = BcryptPasswordContext()

AuthMode = Literal["local", "ldap", "ad"]


@dataclass
class AuthPrincipal:
    subject: str
    auth_mode: str


class AuthService:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def _api_key_prefix_len(self) -> int:
        return max(4, int(self._settings.api_key.prefix_length))

    def _require_jwt_secret(self) -> str:
        secret = self._settings.jwt.secret.strip()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="未配置 AUTOOPSHUB_JWT_SECRET，无法签发 JWT",
            )
        return secret

    def login(self, mode: AuthMode, username: str, password: str) -> dict[str, Any]:
        if mode == "local":
            self._verify_local(username, password)
        elif mode == "ldap":
            self._verify_ldap(username, password)
        elif mode == "ad":
            self._verify_ad(username, password)
        else:
            raise HTTPException(status_code=422, detail="不支持的认证方式")

        jti = str(uuid.uuid4())
        exp = datetime.now(timezone.utc) + timedelta(minutes=self._settings.jwt.expire_minutes)
        secret = self._require_jwt_secret()
        token = jwt.encode(
            {"sub": username, "jti": jti, "amr": mode, "exp": exp},
            secret,
            algorithm=self._settings.jwt.algorithm,
        )
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO auth_jwt_sessions (jti, subject_username, expires_at) VALUES (%s,%s,%s)",
                    (jti, username, exp.replace(tzinfo=None)),
                )
        finally:
            conn.close()

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": exp.isoformat(),
            "principal": {"username": username, "auth_mode": mode},
        }

    def _verify_local(self, username: str, password: str) -> None:
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT password_hash FROM auth_users WHERE username=%s LIMIT 1",
                    (username,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row or not pwd_context.verify(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="认证失败")

    def _verify_ldap(self, username: str, password: str) -> None:
        try:
            from ldap3 import Connection, Server  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="LDAP 客户端不可用") from exc

        uri = self._settings.ldap.uri
        timeout = float(self._settings.ldap.connect_timeout_seconds)
        try:
            server = Server(uri, connect_timeout=timeout)
            bind_dn = (
                self._settings.ldap.bind_dn_template.format(username=username)
                if self._settings.ldap.bind_dn_template
                else username
            )
            conn = Connection(server, user=bind_dn, password=password, auto_bind=True)
            conn.unbind()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"LDAP 认证源不可用: {exc}") from exc

    def _verify_ad(self, username: str, password: str) -> None:
        try:
            from ldap3 import Connection, Server  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="AD 客户端不可用") from exc

        uri = self._settings.ad.uri
        timeout = float(self._settings.ad.connect_timeout_seconds)
        try:
            server = Server(uri, connect_timeout=timeout)
            bind_dn = (
                self._settings.ad.bind_dn_template.format(username=username)
                if self._settings.ad.bind_dn_template
                else username
            )
            conn = Connection(server, user=bind_dn, password=password, auto_bind=True)
            conn.unbind()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"AD 认证源不可用: {exc}") from exc

    def decode_and_validate_jwt(self, token: str) -> AuthPrincipal:
        secret = self._require_jwt_secret()
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self._settings.jwt.algorithm],
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="JWT 已过期") from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail="JWT 无效") from exc

        jti = str(payload.get("jti", ""))
        sub = str(payload.get("sub", ""))
        mode = str(payload.get("amr", "local"))
        if not jti or not sub:
            raise HTTPException(status_code=401, detail="JWT 无效")
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT revoked_at FROM auth_jwt_sessions WHERE jti=%s LIMIT 1",
                    (jti,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row or row.get("revoked_at"):
            raise HTTPException(status_code=401, detail="JWT 已撤销或无效")
        return AuthPrincipal(subject=sub, auth_mode=mode)  # type: ignore[arg-type]

    def revoke_jwt(self, jti: str) -> None:
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_jwt_sessions SET revoked_at=%s WHERE jti=%s AND revoked_at IS NULL",
                    (datetime.now(timezone.utc).replace(tzinfo=None), jti),
                )
        finally:
            conn.close()

    def revoke_jwt_for_token(self, token: str) -> None:
        secret = self._require_jwt_secret()
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self._settings.jwt.algorithm],
                options={"verify_exp": False},
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail="JWT 无效") from exc
        jti = str(payload.get("jti", ""))
        if not jti:
            raise HTTPException(status_code=401, detail="JWT 无效")
        self.revoke_jwt(jti)

    def create_api_key(self, name: str) -> dict[str, Any]:
        raw = f"aoh_{secrets.token_urlsafe(32)}"
        prefix_len = self._api_key_prefix_len()
        prefix = raw[:prefix_len]
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key_hash = pwd_context.hash(digest)
        kid = str(uuid.uuid4())
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO auth_api_keys (id, name, key_prefix, key_hash) VALUES (%s,%s,%s,%s)",
                    (kid, name, prefix, key_hash),
                )
        finally:
            conn.close()
        return {"id": kid, "name": name, "api_key": raw, "prefix": prefix}

    def revoke_api_key(self, key_id: str) -> None:
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_api_keys SET revoked_at=%s WHERE id=%s AND revoked_at IS NULL",
                    (datetime.now(timezone.utc).replace(tzinfo=None), key_id),
                )
        finally:
            conn.close()

    def list_api_keys(self) -> list[dict[str, Any]]:
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, key_prefix, created_at, revoked_at FROM auth_api_keys ORDER BY created_at DESC"
                )
                return list(cur.fetchall() or [])
        finally:
            conn.close()

    def validate_api_key(self, raw_key: str) -> AuthPrincipal | None:
        if not raw_key:
            return None
        conn = mysql_connect(self._settings)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, key_hash, revoked_at FROM auth_api_keys WHERE key_prefix=%s LIMIT 5",
                    (raw_key[: self._api_key_prefix_len()],),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        for row in rows or []:
            if row.get("revoked_at"):
                continue
            if pwd_context.verify(digest, row["key_hash"]):
                return AuthPrincipal(subject=f"apikey:{row['id']}", auth_mode="local")
        return None
