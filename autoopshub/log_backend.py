"""Task 日志后端：内存与 Redis Stream，带降级与状态。"""

from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from autoopshub.settings import AppSettings


@dataclass
class LogRecordData:
    task_id: str
    log_seq: int
    ts: str
    level: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "log_seq": self.log_seq,
            "ts": self.ts,
            "level": self.level,
            "message": self.message,
        }


class LogBackend(ABC):
    """统一追加、历史读取与实时订阅。"""

    @abstractmethod
    def append(self, workpiece_name: str, task_id: str, record: LogRecordData) -> int:
        """写入一条日志，返回分配的 log_seq。"""

    @abstractmethod
    def read_after(self, workpiece_name: str, task_id: str, after: int, limit: int) -> list[dict[str, Any]]:
        """读取 log_seq > after 的最多 limit 条。"""

    @abstractmethod
    def subscribe_existing_then_poll(
        self,
        workpiece_name: str,
        task_id: str,
        poll_interval_seconds: float,
        stop_event: threading.Event,
    ) -> Iterator[dict[str, Any]]:
        """先产出已有增量，再在 stop_event 清除前轮询新日志。"""


@dataclass
class LogBackendStatus:
    backend_type: str
    redis_configured: bool
    redis_reachable: bool | None
    degrade_reason: str | None = None


class MemoryLogBackend(LogBackend):
    """进程内内存后端，非持久化。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self._seq: dict[tuple[str, str], int] = defaultdict(int)
        self._listeners: dict[tuple[str, str], list[threading.Condition]] = defaultdict(list)

    def append(self, workpiece_name: str, task_id: str, record: LogRecordData) -> int:
        key = (workpiece_name, task_id)
        with self._lock:
            self._seq[key] += 1
            seq = self._seq[key]
            row = record.to_dict()
            row["log_seq"] = seq
            self._items[key].append(row)
            conds = list(self._listeners[key])
        for c in conds:
            with c:
                c.notify_all()
        return seq

    def read_after(self, workpiece_name: str, task_id: str, after: int, limit: int) -> list[dict[str, Any]]:
        key = (workpiece_name, task_id)
        with self._lock:
            rows = [x for x in self._items[key] if int(x.get("log_seq", 0)) > after]
        return rows[:limit]

    def subscribe_existing_then_poll(
        self,
        workpiece_name: str,
        task_id: str,
        poll_interval_seconds: float,
        stop_event: threading.Event,
    ) -> Iterator[dict[str, Any]]:
        key = (workpiece_name, task_id)
        last = 0
        cond = threading.Condition(self._lock)
        with self._lock:
            self._listeners[key].append(cond)
        try:
            while not stop_event.is_set():
                batch = self.read_after(workpiece_name, task_id, last, 500)
                if batch:
                    for row in batch:
                        last = int(row["log_seq"])
                        yield row
                    continue
                with cond:
                    cond.wait(timeout=poll_interval_seconds)
        finally:
            with self._lock:
                if cond in self._listeners[key]:
                    self._listeners[key].remove(cond)


class RedisStreamLogBackend(LogBackend):
    """Redis Stream：stream key = prefix + workpiece + ':' + task_id。"""

    def __init__(self, client: Any, stream_prefix: str) -> None:
        self._r = client
        self._prefix = stream_prefix.rstrip(":") + ":"

    def _key(self, workpiece_name: str, task_id: str) -> str:
        return f"{self._prefix}{workpiece_name}:{task_id}"

    def _seq_key(self, workpiece_name: str, task_id: str) -> str:
        return f"{self._prefix}seq:{workpiece_name}:{task_id}"

    def append(self, workpiece_name: str, task_id: str, record: LogRecordData) -> int:
        key = self._key(workpiece_name, task_id)
        seq = int(self._r.incr(self._seq_key(workpiece_name, task_id)))
        payload = {
            b"task_id": record.task_id.encode(),
            b"log_seq": str(seq).encode(),
            b"ts": record.ts.encode(),
            b"level": record.level.encode(),
            b"message": record.message.encode(),
        }
        self._r.xadd(key, payload)
        return seq

    def read_after(self, workpiece_name: str, task_id: str, after: int, limit: int) -> list[dict[str, Any]]:
        key = self._key(workpiece_name, task_id)
        rows: list[dict[str, Any]] = []
        result = self._r.xrange(key, "-", "+")
        for _entry_id, data in result or []:
            seq = int(_decode_field(data, b"log_seq") or "0")
            if seq <= after:
                continue
            row = {
                "task_id": _decode_field(data, b"task_id"),
                "log_seq": seq,
                "ts": _decode_field(data, b"ts"),
                "level": _decode_field(data, b"level"),
                "message": _decode_field(data, b"message"),
            }
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def subscribe_existing_then_poll(
        self,
        workpiece_name: str,
        task_id: str,
        poll_interval_seconds: float,
        stop_event: threading.Event,
    ) -> Iterator[dict[str, Any]]:
        key = self._key(workpiece_name, task_id)
        last_id = "0-0"
        while not stop_event.is_set():
            result = self._r.xread({key: last_id}, count=100, block=int(poll_interval_seconds * 1000))
            if not result:
                continue
            for _sname, messages in result:
                for entry_id, data in messages:
                    last_id = entry_id
                    seq = int(_decode_field(data, b"log_seq") or "0")
                    yield {
                        "task_id": _decode_field(data, b"task_id"),
                        "log_seq": seq,
                        "ts": _decode_field(data, b"ts"),
                        "level": _decode_field(data, b"level"),
                        "message": _decode_field(data, b"message"),
                    }


def _decode_field(data: dict, k: bytes) -> str:
    v = data.get(k) or data.get(k.decode())
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)


class LogBackendManager:
    """选择 Redis 或内存，并维护降级状态。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._memory = MemoryLogBackend()
        self._redis_backend: RedisStreamLogBackend | None = None
        self._active: LogBackend = self._memory
        self._status = LogBackendStatus(
            backend_type="memory",
            redis_configured=bool(settings.redis.url),
            redis_reachable=False,
            degrade_reason=None if not settings.redis.url else "尚未连接 Redis",
        )
        self._connect_redis_if_configured()

    def _connect_redis_if_configured(self) -> None:
        url = self._settings.redis.url
        if not url:
            self._status = LogBackendStatus(
                backend_type="memory",
                redis_configured=False,
                redis_reachable=None,
                degrade_reason="未配置 AUTOOPSHUB_REDIS_URL，使用内存日志后端（非持久化）",
            )
            self._active = self._memory
            return
        try:
            import redis as redis_lib  # type: ignore

            client = redis_lib.from_url(url, decode_responses=False)
            client.ping()
            self._redis_backend = RedisStreamLogBackend(client, self._settings.redis.stream_prefix)
            self._active = self._redis_backend
            self._status = LogBackendStatus(
                backend_type="redis",
                redis_configured=True,
                redis_reachable=True,
                degrade_reason=None,
            )
        except Exception as exc:  # noqa: BLE001
            self._redis_backend = None
            self._active = self._memory
            self._status = LogBackendStatus(
                backend_type="memory",
                redis_configured=True,
                redis_reachable=False,
                degrade_reason=f"Redis 不可用，已降级内存日志: {exc}",
            )

    @property
    def backend(self) -> LogBackend:
        return self._active

    @property
    def status(self) -> LogBackendStatus:
        return self._status

    def reload(self) -> None:
        """用于测试或配置变更后重连。"""

        self._connect_redis_if_configured()
