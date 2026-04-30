from __future__ import annotations

import json
import os
import posixpath
import shutil
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal
from uuid import uuid4

import yaml
from croniter import croniter
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from jinja2 import Environment, meta
from jinja2 import Template
from pydantic import BaseModel, Field, field_validator

from autoopshub.auth_service import AuthService
from autoopshub.db_schema import assert_auth_schema_present
from autoopshub.executors import dispatch_execution
from autoopshub.log_backend import LogBackendManager, LogRecordData
from autoopshub.manifest_resolve import (
    ManifestItem,
    detect_duplicate_names,
    extract_system_refs_from_template,
    extract_user_template_vars,
    resolve_nested_defaults,
    template_assigns_system_var,
)
from autoopshub.settings import load_settings


class RunbookType(str, Enum):
    TERRAFORM = "Terraform"
    ANSIBLE = "Ansible"
    SCRIPT = "Script"
    WORKFLOW = "Workflow"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskSource(str, Enum):
    MANUAL = "manual"
    JOB = "job"


class SettingAction(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    AUTO_CANCEL = "auto_cancel"
    SCHEDULE_EXECUTE = "schedule_execute"
    SCHEDULE_CANCEL = "schedule_cancel"


class ManifestVariableDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class LogLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class HandlingStrategy(BaseModel):
    action: SettingAction
    delay_seconds: int = Field(ge=0, default=0)


class WorkpieceSetting(BaseModel):
    no_variable_strategy: HandlingStrategy = Field(
        default_factory=lambda: HandlingStrategy(action=SettingAction.AUTO_EXECUTE, delay_seconds=0)
    )
    optional_only_strategy: HandlingStrategy = Field(
        default_factory=lambda: HandlingStrategy(action=SettingAction.AUTO_EXECUTE, delay_seconds=0)
    )
    ready_strategy: HandlingStrategy = Field(
        default_factory=lambda: HandlingStrategy(action=SettingAction.AUTO_EXECUTE, delay_seconds=0)
    )
    required_missing_retention_seconds: int = Field(default=86400, ge=60)


class WorkpieceCreateRequest(BaseModel):
    description: str = ""


class WorkpieceUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("name cannot be empty")
        return stripped


class WorkpieceMeta(BaseModel):
    name: str
    description: str = ""
    created_at: str
    updated_at: str


class WorkpieceDetail(WorkpieceMeta):
    directory: str
    stats: dict[str, int]


class ManifestVariable(BaseModel):
    name: str
    display_name: str = ""
    direction: ManifestVariableDirection = ManifestVariableDirection.INPUT
    required: bool = False
    default_value: str = ""

    @field_validator("display_name")
    @classmethod
    def default_display_name(cls, value: str) -> str:
        return value or ""


class RunbookRecord(BaseModel):
    name: str
    type: RunbookType
    description: str = ""
    content: str
    runtime: str | None = None
    content_mode: Literal["inline", "files"] = "inline"
    entry_file: str | None = None
    files_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class TaskRecord(BaseModel):
    task_id: str
    source: TaskSource
    runbook_name: str
    variables: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    error_summary: str = ""
    schedule: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    exit_code: int | None = None
    started_at: str | None = None
    ended_at: str | None = None


class JobRecord(BaseModel):
    job_name: str
    description: str = ""
    cron: str
    runbook_name: str
    variables: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    next_run_at: str | None = None
    created_at: str
    updated_at: str


class LogRecord(BaseModel):
    task_id: str
    log_seq: int
    ts: str
    level: LogLevel
    message: str


class RunbookUpsertRequest(BaseModel):
    type: RunbookType
    description: str = ""
    content: str
    runtime: str | None = None
    manifest: list[ManifestVariable] | None = None


class ManifestUpsertRequest(BaseModel):
    manifest: list[ManifestVariable]


class TriggerRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class TaskVariablesUpdateRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class TaskRerunRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class JobUpsertRequest(BaseModel):
    job_name: str | None = None
    description: str = ""
    cron: str
    runbook_name: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AuthLoginRequest(BaseModel):
    mode: Literal["local", "ldap", "ad"]
    username: str
    password: str


class ApiKeyCreateRequest(BaseModel):
    name: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# 系统保留变量名（与模板占位符一致）
SYSTEM_RESERVED_NAMES = {
    "system.set_runtime",
    "system.output",
    "system.runbook_file",
    "system.env_file",
    "system.inventory_file",
    "system.host",
    "system.runbook_path",
}
# 只读：禁止调用方在 task 变量中覆盖
SYSTEM_READONLY_NAMES = {"system.output", "system.runbook_file", "system.runbook_path"}


def _manifest_items_dict(manifest: list[ManifestVariable]) -> dict[str, ManifestItem]:
    return {m.name: ManifestItem(name=m.name, default_value=m.default_value) for m in manifest}


def _manifest_default(manifest: list[ManifestVariable], name: str) -> str:
    for item in manifest:
        if item.name == name:
            return item.default_value
    return ""


def _script_uses_system_set_runtime(content: str) -> bool:
    lines = content.splitlines()
    return bool(lines and lines[0].strip() == "{{ system.set_runtime }}")


def _drop_first_line(text: str) -> str:
    lines = text.splitlines(keepends=True)
    return "".join(lines[1:]) if lines else text


def _validate_runbook_manifest_on_create(content: str, manifest: list[ManifestVariable] | None) -> None:
    if template_assigns_system_var(content):
        raise HTTPException(status_code=422, detail="禁止在模板中使用 {% set system.* %} 为系统保留变量赋值")
    names = [m.name for m in (manifest or [])]
    dups = detect_duplicate_names(names)
    if dups:
        raise HTTPException(status_code=422, detail=f"manifest 变量重复声明: {', '.join(dups)}")
    for item in manifest or []:
        if item.name in SYSTEM_RESERVED_NAMES:
            raise HTTPException(status_code=422, detail="禁止在创建 runbook 的 manifest 中提前声明系统保留变量")


def _validate_task_variables_against_readonly(manifest: list[ManifestVariable], variables: dict[str, Any]) -> None:
    for key in variables:
        if key in SYSTEM_READONLY_NAMES:
            raise HTTPException(status_code=422, detail=f"禁止覆盖只读系统变量: {key}")


def _validate_workpiece_name_component(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise HTTPException(status_code=422, detail="workpiece name cannot be empty")
    if stripped in {".", ".."} or "/" in stripped or "\\" in stripped:
        raise HTTPException(status_code=422, detail="workpiece name must be a single path component")
    return stripped


def _jinja_render_context(variables: dict[str, Any]) -> dict[str, Any]:
    context = dict(variables)
    system_vars = {
        key.split(".", 1)[1]: value
        for key, value in variables.items()
        if key.startswith("system.") and "." in key
    }
    if system_vars:
        context["system"] = system_vars
        for key, value in system_vars.items():
            context.setdefault(key, value)
    return context


def _combined_template_var_names(content: str, *, include_all_system: bool = False) -> set[str]:
    names = extract_user_template_vars(content) | extract_system_refs_from_template(content)
    if include_all_system:
        names |= SYSTEM_RESERVED_NAMES
    return names


def _base_dir() -> Path:
    custom = os.getenv("AUTOOPSHUB_HOME")
    if custom:
        home = Path(custom)
    else:
        home = Path.home()
    root = home / ".autoopshub"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _workpiece_dir(workpiece_name: str) -> Path:
    return _base_dir() / "workpieces" / workpiece_name


def _meta_path(workpiece_name: str) -> Path:
    return _workpiece_dir(workpiece_name) / "meta.json"


def _setting_path(workpiece_name: str) -> Path:
    return _workpiece_dir(workpiece_name) / "setting" / "setting.json"


def _runbook_path(workpiece_name: str, runbook_name: str) -> Path:
    return _workpiece_dir(workpiece_name) / "runbooks" / f"{runbook_name}.json"


def _runbook_files_dir(workpiece_name: str, runbook_name: str) -> Path:
    return _workpiece_dir(workpiece_name) / "runbooks" / f"{runbook_name}.files"


def _manifest_path(workpiece_name: str, runbook_name: str) -> Path:
    return _workpiece_dir(workpiece_name) / "runbooks" / f"{runbook_name}.manifest.json"


def _task_path(workpiece_name: str, task_id: str) -> Path:
    return _workpiece_dir(workpiece_name) / "tasks" / f"{task_id}.json"


def _job_path(workpiece_name: str, job_name: str) -> Path:
    return _workpiece_dir(workpiece_name) / "jobs" / f"{job_name}.json"


def _task_log_path(workpiece_name: str, task_id: str) -> Path:
    return _workpiece_dir(workpiece_name) / "logs" / f"{task_id}.log.jsonl"


def _ensure_workpiece_structure(workpiece_name: str) -> Path:
    root = _workpiece_dir(workpiece_name)
    for relative in ["runbooks", "tasks", "jobs", "logs", "setting"]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_meta(workpiece_name: str) -> WorkpieceMeta:
    path = _meta_path(workpiece_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="workpiece not found")
    return WorkpieceMeta.model_validate(_read_json(path))


def _save_meta(meta: WorkpieceMeta) -> None:
    _write_json(_meta_path(meta.name), meta.model_dump())


def _load_setting(workpiece_name: str) -> WorkpieceSetting:
    path = _setting_path(workpiece_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="workpiece setting not found")
    return WorkpieceSetting.model_validate(_read_json(path))


def _save_setting(workpiece_name: str, setting: WorkpieceSetting) -> None:
    _write_json(_setting_path(workpiece_name), setting.model_dump())


def _save_runbook(workpiece_name: str, runbook: RunbookRecord) -> None:
    _write_json(_runbook_path(workpiece_name, runbook.name), runbook.model_dump())


def _load_runbook(workpiece_name: str, runbook_name: str) -> RunbookRecord:
    path = _runbook_path(workpiece_name, runbook_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="runbook not found")
    return RunbookRecord.model_validate(_read_json(path))


def _save_manifest(workpiece_name: str, runbook_name: str, manifest: list[ManifestVariable]) -> None:
    _write_json(_manifest_path(workpiece_name, runbook_name), {"items": [item.model_dump() for item in manifest]})


def _load_manifest(workpiece_name: str, runbook_name: str) -> list[ManifestVariable]:
    path = _manifest_path(workpiece_name, runbook_name)
    if not path.exists():
        items: list[ManifestVariable] = []
    else:
        payload = _read_json(path)
        items = [ManifestVariable.model_validate(item) for item in payload.get("items", [])]
    runbook_path = _runbook_path(workpiece_name, runbook_name)
    if runbook_path.exists():
        runbook_payload = _read_json(runbook_path)
        if runbook_payload.get("content_mode") == "files":
            template_vars = _file_package_template_vars(workpiece_name, runbook_name, include_all_system=True)
        else:
            template_vars = _combined_template_var_names(str(runbook_payload.get("content", "")), include_all_system=True)
        normalized = _normalize_manifest(template_vars, items, allow_extra_user_vars=True)
        if [item.model_dump() for item in normalized] != [item.model_dump() for item in items]:
            _save_manifest(workpiece_name, runbook_name, normalized)
        return normalized
    if not path.exists():
        return []
    payload = _read_json(path)
    return [ManifestVariable.model_validate(item) for item in payload.get("items", [])]


def _runbook_payload(workpiece_name: str, runbook: RunbookRecord) -> dict[str, Any]:
    payload = runbook.model_dump()
    payload["manifest_summary"] = {"variables": len(_load_manifest(workpiece_name, runbook.name))}
    return payload


TEXT_SCAN_EXTENSIONS = {
    ".tf",
    ".tfvars",
    ".yaml",
    ".yml",
    ".json",
    ".sh",
    ".tpl",
    ".txt",
    ".hcl",
}


def _safe_package_relative_path(raw_path: str | None) -> str:
    raw = (raw_path or "").strip()
    if not raw or raw.endswith("/") or raw.endswith("\\"):
        raise HTTPException(status_code=422, detail="上传文件路径不能为空或目录路径")
    if "\\" in raw:
        raise HTTPException(status_code=422, detail="上传文件路径必须使用安全相对路径")
    if PureWindowsPath(raw).drive or PureWindowsPath(raw).root:
        raise HTTPException(status_code=422, detail="禁止上传绝对路径或 Windows 盘符路径")
    normalized = posixpath.normpath(raw)
    path = PurePosixPath(normalized)
    if path.is_absolute() or normalized in {"", "."} or any(part in {"..", ""} for part in path.parts):
        raise HTTPException(status_code=422, detail="禁止上传绝对路径、空路径或路径穿越")
    return normalized


def _ensure_path_inside(root: Path, relative_path: str) -> Path:
    target = (root / Path(*PurePosixPath(relative_path).parts)).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise HTTPException(status_code=422, detail="上传文件路径逃逸文件包目录")
    return target


def _read_text_for_scan(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SCAN_EXTENSIONS:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _package_template_texts(workpiece_name: str, runbook_name: str) -> list[str]:
    root = _runbook_files_dir(workpiece_name, runbook_name)
    if not root.exists():
        return []
    texts: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        text = _read_text_for_scan(path)
        if text is not None:
            texts.append(text)
    return texts


def _file_package_template_vars(workpiece_name: str, runbook_name: str, *, include_all_system: bool = False) -> set[str]:
    names: set[str] = set()
    for text in _package_template_texts(workpiece_name, runbook_name):
        names |= _combined_template_var_names(text, include_all_system=include_all_system)
    if include_all_system:
        names |= SYSTEM_RESERVED_NAMES
    return names


def _files_summary(files: list[tuple[str, bytes]]) -> dict[str, Any]:
    paths = [path for path, _content in files]
    return {
        "count": len(files),
        "total_bytes": sum(len(content) for _path, content in files),
        "paths": paths[:100],
    }


def _select_entry_file(files: list[tuple[str, bytes]], requested: str | None) -> str:
    paths = [path for path, _content in files]
    if requested and requested.strip():
        entry = _safe_package_relative_path(requested)
        if entry not in paths:
            raise HTTPException(status_code=422, detail="entry_file 必须指向已上传文件")
        return entry
    if "main.tf" in paths:
        return "main.tf"
    for path in paths:
        if path.endswith(".tf"):
            return path
    return paths[0]


def _replace_runbook_file_package(workpiece_name: str, runbook_name: str, files: list[tuple[str, bytes]]) -> None:
    root = _runbook_files_dir(workpiece_name, runbook_name)
    tmp = root.with_name(f"{root.name}.tmp-{uuid4().hex[:8]}")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for relative_path, content in files:
            target = _ensure_path_inside(tmp, relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if root.exists():
            shutil.rmtree(root)
        shutil.move(str(tmp), str(root))
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _delete_runbook_file_package(workpiece_name: str, runbook_name: str) -> None:
    shutil.rmtree(_runbook_files_dir(workpiece_name, runbook_name), ignore_errors=True)


def _render_text_files_in_place(root: Path, variables: dict[str, Any]) -> None:
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        text = _read_text_for_scan(path)
        if text is None:
            continue
        path.write_text(Template(text).render(**_jinja_render_context(variables)), encoding="utf-8")


async def _uploaded_package_files(request: Request) -> tuple[dict[str, str], list[tuple[str, bytes]]]:
    try:
        form = await request.form()
    except AssertionError as exc:
        if "python-multipart" in str(exc):
            raise HTTPException(
                status_code=503,
                detail="服务器缺少 python-multipart 依赖，无法解析 multipart/form-data 上传；请执行 pip install -r requirements.txt 后重启后端服务",
            ) from exc
        raise
    fields = {key: str(value) for key, value in form.multi_items() if not hasattr(value, "filename")}
    upload_items = [value for key, value in form.multi_items() if key == "files" and hasattr(value, "filename")]
    if not upload_items:
        raise HTTPException(status_code=422, detail="multipart runbook 必须上传至少一个 files 文件")
    limits = settings.runbook_upload
    if len(upload_items) > limits.max_files:
        raise HTTPException(status_code=413, detail=f"上传文件数量超过限制: {limits.max_files}")
    files: list[tuple[str, bytes]] = []
    total = 0
    seen: set[str] = set()
    for upload in upload_items:
        relative_path = _safe_package_relative_path(getattr(upload, "filename", ""))
        if relative_path in seen:
            raise HTTPException(status_code=422, detail=f"重复上传文件路径: {relative_path}")
        seen.add(relative_path)
        content = await upload.read()
        if len(content) > limits.max_file_bytes:
            raise HTTPException(status_code=413, detail=f"单文件大小超过限制: {relative_path}")
        total += len(content)
        if total > limits.max_total_bytes:
            raise HTTPException(status_code=413, detail=f"上传文件总大小超过限制: {limits.max_total_bytes}")
        files.append((relative_path, content))
    return fields, files


def _save_task(workpiece_name: str, task: TaskRecord) -> None:
    _write_json(_task_path(workpiece_name, task.task_id), task.model_dump())


def _load_task(workpiece_name: str, task_id: str) -> TaskRecord:
    path = _task_path(workpiece_name, task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="task not found")
    return TaskRecord.model_validate(_read_json(path))


def _save_job(workpiece_name: str, job: JobRecord) -> None:
    _write_json(_job_path(workpiece_name, job.job_name), job.model_dump())


def _load_job(workpiece_name: str, job_name: str) -> JobRecord:
    path = _job_path(workpiece_name, job_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="job not found")
    return JobRecord.model_validate(_read_json(path))


def _save_log_record(workpiece_name: str, task_id: str, record: LogRecord) -> int:
    payload = LogRecordData(
        task_id=task_id,
        log_seq=0,
        ts=record.ts,
        level=record.level.value,
        message=record.message,
    )
    return log_mgr.backend.append(workpiece_name, task_id, payload)


def _extract_template_variables(content: str) -> set[str]:
    env = Environment()
    parsed = env.parse(content)
    return set(meta.find_undeclared_variables(parsed))


def _normalize_manifest(
    vars_from_template: set[str],
    manifest: list[ManifestVariable] | None,
    *,
    allow_extra_user_vars: bool = False,
) -> list[ManifestVariable]:
    provided = {item.name: item for item in (manifest or [])}
    unknown_set = set(provided.keys()) - vars_from_template
    if allow_extra_user_vars:
        unknown_set = {name for name in unknown_set if name in SYSTEM_RESERVED_NAMES}
        vars_from_template = vars_from_template | {item.name for item in (manifest or []) if item.name not in SYSTEM_RESERVED_NAMES}
    unknown = sorted(unknown_set)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown manifest variables: {', '.join(unknown)}")
    merged: list[ManifestVariable] = []
    for name in sorted(vars_from_template):
        direction = ManifestVariableDirection.INPUT
        if name in SYSTEM_READONLY_NAMES:
            direction = ManifestVariableDirection.OUTPUT
        base = ManifestVariable(
            name=name,
            display_name=name,
            direction=direction,
            required=False,
            default_value="",
        )
        item = base.model_copy(update=provided[name].model_dump(exclude_unset=True)) if name in provided else base
        if name in SYSTEM_READONLY_NAMES:
            item = item.model_copy(update={"direction": ManifestVariableDirection.OUTPUT, "required": False})
        merged.append(item)
    return merged


def _workflow_includes(content: str) -> list[str]:
    try:
        parsed = yaml.safe_load(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid workflow yaml: {exc}") from exc
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="workflow yaml must be a mapping")
    steps = parsed.get("steps", []) or []
    if not isinstance(steps, list):
        raise HTTPException(status_code=422, detail="workflow steps must be a list")
    includes: list[str] = []
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("include"), str):
            includes.append(step["include"])
    return includes


def _runbook_exists(workpiece_name: str, runbook_name: str) -> bool:
    return _runbook_path(workpiece_name, runbook_name).exists()


def _validate_workflow_references(workpiece_name: str, runbook_name: str, content: str) -> None:
    includes = _workflow_includes(content)
    for include in includes:
        if include == runbook_name:
            raise HTTPException(status_code=422, detail="workflow include self reference")
        if not _runbook_exists(workpiece_name, include):
            raise HTTPException(status_code=422, detail=f"workflow include target not found: {include}")
        try:
            ref = _load_runbook(workpiece_name, include)
        except HTTPException:
            continue
        if ref.type not in {RunbookType.TERRAFORM, RunbookType.ANSIBLE, RunbookType.SCRIPT, RunbookType.WORKFLOW}:
            raise HTTPException(status_code=422, detail=f"workflow include type is not allowed: {include}")
        if ref.type == RunbookType.WORKFLOW:
            nested = _workflow_includes(ref.content)
            if runbook_name in nested:
                raise HTTPException(status_code=422, detail=f"workflow include cycle detected: {runbook_name} <-> {include}")


def _workpiece_stats(workpiece_name: str) -> dict[str, int]:
    root = _workpiece_dir(workpiece_name)
    return {
        "runbooks": len(list((root / "runbooks").glob("*"))),
        "tasks": len(list((root / "tasks").glob("*.json"))),
        "jobs": len(list((root / "jobs").glob("*.json"))),
        "logs": len(list((root / "logs").glob("*.log"))),
    }


def _list_tasks(workpiece_name: str) -> list[TaskRecord]:
    tasks_dir = _workpiece_dir(workpiece_name) / "tasks"
    items: list[TaskRecord] = []
    for path in sorted(tasks_dir.glob("*.json")):
        items.append(TaskRecord.model_validate(_read_json(path)))
    return items


def _list_workpiece_names() -> list[str]:
    root = _base_dir() / "workpieces"
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and _meta_path(path.name).exists())


def _find_task_workpiece(task_id: str) -> tuple[str, TaskRecord]:
    for workpiece_name in _list_workpiece_names():
        path = _task_path(workpiece_name, task_id)
        if path.exists():
            return workpiece_name, TaskRecord.model_validate(_read_json(path))
    raise HTTPException(status_code=404, detail="task not found")


def _next_task_id() -> str:
    return f"task-{uuid4().hex[:12]}"


def _validate_variables(
    manifest: list[ManifestVariable], provided: dict[str, Any]
) -> tuple[list[str], list[str], list[str]]:
    known = {item.name for item in manifest}
    required_inputs = {item.name for item in manifest if item.direction == ManifestVariableDirection.INPUT and item.required}
    provided_keys = set(provided.keys())
    unknown = sorted(provided_keys - known)
    missing = sorted(required_inputs - provided_keys)
    valid_keys = sorted((provided_keys & known))
    return missing, unknown, valid_keys


def _task_runtime_dir(task_id: str) -> Path:
    return Path(tempfile.gettempdir()) / "autoopshub" / task_id


def _task_inherited_runtime_dir(task: TaskRecord) -> Path | None:
    raw = task.schedule.get("inherited_runtime_dir")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Path(raw)


def _append_task_log(workpiece_name: str, task: TaskRecord, level: LogLevel, message: str) -> int:
    return _save_log_record(
        workpiece_name,
        task.task_id,
        LogRecord(task_id=task.task_id, log_seq=0, ts=_utc_now(), level=level, message=message),
    )


def _execute_task(workpiece_name: str, task: TaskRecord) -> TaskRecord:
    task.status = TaskStatus.RUNNING
    now = _utc_now()
    task.started_at = now
    task.updated_at = now
    task.exit_code = None
    _save_task(workpiece_name, task)
    _append_task_log(workpiece_name, task, LogLevel.INFO, "task running")
    runbook = _load_runbook(workpiece_name, task.runbook_name)
    manifest = _load_manifest(workpiece_name, task.runbook_name)
    try:
        _validate_task_variables_against_readonly(manifest, task.variables)
        items = _manifest_items_dict(manifest)
        resolved_defaults = resolve_nested_defaults(items, task.variables)
        merged_vars: dict[str, Any] = {**resolved_defaults, **task.variables}
        runtime_dir = _task_runtime_dir(task.task_id)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        inherited_runtime_dir = _task_inherited_runtime_dir(task)
        if inherited_runtime_dir and inherited_runtime_dir.exists() and inherited_runtime_dir.resolve() != runtime_dir.resolve():
            shutil.copytree(inherited_runtime_dir, runtime_dir, dirs_exist_ok=True)
        if runbook.content_mode == "files":
            package_dir = _runbook_files_dir(workpiece_name, runbook.name)
            if not package_dir.exists():
                raise ValueError("runbook 文件包不存在")
            shutil.copytree(package_dir, runtime_dir, dirs_exist_ok=True)
            entry = runbook.entry_file or "main.tf"
            rendered_path = _ensure_path_inside(runtime_dir, entry)
        else:
            suffix = runbook.type.value.lower()
            rendered_path = runtime_dir / f"{runbook.name}.{suffix}.rendered"
        merged_vars["system.runbook_file"] = str(rendered_path)
        merged_vars["system.runbook_path"] = str(runtime_dir)
        merged_vars["system.output"] = str(runtime_dir / "system.output")
        merged_vars["system.env_file"] = str(runtime_dir / "autoopshub.env")
        Path(str(merged_vars["system.output"])).mkdir(parents=True, exist_ok=True)
        if not str(merged_vars.get("system.inventory_file", "")).strip():
            merged_vars["system.inventory_file"] = str(runtime_dir / "inventory.ini")
        set_runtime_template = str(task.variables.get("system.set_runtime") or _manifest_default(manifest, "system.set_runtime"))
        if set_runtime_template.strip():
            merged_vars["system.set_runtime"] = Template(set_runtime_template).render(**_jinja_render_context(merged_vars))
        effective_runtime = runbook.runtime
        if runbook.content_mode == "files":
            _render_text_files_in_place(runtime_dir, merged_vars)
            rendered = ""
        else:
            rendered = Template(runbook.content).render(**_jinja_render_context(merged_vars))
            if runbook.type == RunbookType.SCRIPT and _script_uses_system_set_runtime(runbook.content):
                effective_runtime = str(merged_vars.get("system.set_runtime", ""))
                rendered = _drop_first_line(rendered)
            rendered_path.write_text(rendered, encoding="utf-8")
        task.schedule["runtime_dir"] = str(runtime_dir)
        task.schedule["rendered_file"] = str(rendered_path)
        task.schedule["content_mode"] = runbook.content_mode
        if runbook.content_mode == "files":
            task.schedule["entry_file"] = runbook.entry_file
            task.schedule["files_summary"] = runbook.files_summary

        def _log_line(level: str, msg: str) -> None:
            lvl = LogLevel.INFO if level == "info" else LogLevel.ERROR
            _append_task_log(workpiece_name, task, lvl, msg)

        if runbook.type == RunbookType.WORKFLOW:
            task.status = TaskStatus.SUCCESS
            task.exit_code = 0
            task.error_summary = ""
            _append_task_log(workpiece_name, task, LogLevel.INFO, "workflow runbook 渲染完成，跳过外部 runtime")
        else:
            result = dispatch_execution(
                settings,
                runbook.type.value,
                runtime_dir,
                rendered_path,
                rendered,
                effective_runtime,
                merged_vars,
                settings.task_execution_timeout_seconds,
                _log_line,
            )
            if result.command:
                task.schedule["runtime_command"] = result.command
            task.exit_code = result.exit_code
            if result.exit_code == 0:
                task.status = TaskStatus.SUCCESS
                task.error_summary = ""
                _append_task_log(workpiece_name, task, LogLevel.INFO, "task success")
            else:
                task.status = TaskStatus.FAILED
                task.error_summary = result.error_summary or "runtime failed"
                _append_task_log(workpiece_name, task, LogLevel.ERROR, task.error_summary)
    except ValueError as exc:
        task.status = TaskStatus.FAILED
        task.error_summary = str(exc)
        task.exit_code = task.exit_code if task.exit_code is not None else 1
        _append_task_log(workpiece_name, task, LogLevel.ERROR, f"task failed: {exc}")
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.error_summary = str(exc)
        task.exit_code = task.exit_code if task.exit_code is not None else 1
        _append_task_log(workpiece_name, task, LogLevel.ERROR, f"task failed: {exc}")
    task.ended_at = _utc_now()
    task.updated_at = task.ended_at
    _save_task(workpiece_name, task)
    return task


def _apply_setting_on_task_creation(
    workpiece_name: str,
    task: TaskRecord,
    background_tasks: BackgroundTasks | None = None,
) -> TaskRecord:
    setting = _load_setting(workpiece_name)
    manifest = _load_manifest(workpiece_name, task.runbook_name)
    required_inputs = [m for m in manifest if m.direction == ManifestVariableDirection.INPUT and m.required]
    missing, unknown, _ = _validate_variables(manifest, task.variables)
    if unknown:
        task.error_summary = f"unknown variables: {', '.join(unknown)}"
        _save_task(workpiece_name, task)
        return task
    if missing:
        task.status = TaskStatus.PENDING
        task.schedule["retention_seconds"] = setting.required_missing_retention_seconds
        _save_task(workpiece_name, task)
        return task
    if not manifest or not required_inputs:
        strategy = setting.no_variable_strategy if not manifest else setting.optional_only_strategy
    else:
        strategy = setting.ready_strategy
    task.schedule["auto_strategy"] = strategy.model_dump()
    if strategy.action == SettingAction.AUTO_CANCEL:
        task.status = TaskStatus.CANCELED
        task.updated_at = _utc_now()
        _append_task_log(workpiece_name, task, LogLevel.WARN, "task auto canceled by setting")
        _save_task(workpiece_name, task)
        return task
    if strategy.action == SettingAction.AUTO_EXECUTE:
        if background_tasks is not None:
            _save_task(workpiece_name, task)
            background_tasks.add_task(_execute_task, workpiece_name, task)
            return task
        return _execute_task(workpiece_name, task)
    _save_task(workpiece_name, task)
    return task


def _validate_cron(expr: str) -> bool:
    try:
        croniter(expr, datetime.now(timezone.utc))
        return True
    except Exception:
        return False


def _next_run_at(expr: str) -> str:
    base = datetime.now(timezone.utc)
    nxt = croniter(expr, base).get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    return nxt.isoformat()


def _create_task_from_runbook(
    workpiece_name: str,
    runbook_name: str,
    variables: dict[str, Any],
    source: TaskSource,
    background_tasks: BackgroundTasks | None = None,
    inherited_runtime_dir: Path | None = None,
) -> tuple[TaskRecord, list[ManifestVariable], list[str], list[str]]:
    _load_runbook(workpiece_name, runbook_name)
    manifest = _load_manifest(workpiece_name, runbook_name)
    _validate_task_variables_against_readonly(manifest, variables)
    missing, unknown, valid_keys = _validate_variables(manifest, variables)
    task = TaskRecord(
        task_id=_next_task_id(),
        source=source,
        runbook_name=runbook_name,
        variables=dict(variables),
        status=TaskStatus.PENDING if (missing or unknown) else TaskStatus.READY,
        error_summary="",
        schedule={"inherited_runtime_dir": str(inherited_runtime_dir)} if inherited_runtime_dir is not None else {},
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    if unknown:
        task.error_summary = f"unknown variables: {', '.join(unknown)}"
    elif missing:
        task.error_summary = "missing required input variables"
    _save_task(workpiece_name, task)
    task = _apply_setting_on_task_creation(workpiece_name, task, background_tasks)
    return task, manifest, missing, unknown


app = FastAPI()

settings = load_settings()
log_mgr = LogBackendManager(settings)
auth_svc = AuthService(settings)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "AUTOOPSHUB_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

def _assert_auth_schema_ready() -> None:
    try:
        assert_auth_schema_present(settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"认证数据库不可用: {exc}") from exc


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path in {"/", "/docs", "/openapi.json", "/redoc"} or path.startswith("/hello/"):
        return await call_next(request)
    if path.startswith("/api/auth/login") or path.startswith("/api/health/"):
        return await call_next(request)
    if not settings.require_auth:
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)
    xkey = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    auth = request.headers.get("authorization")
    try:
        if xkey and xkey.strip():
            p = auth_svc.validate_api_key(xkey.strip())
            if p:
                request.state.principal = p
                return await call_next(request)
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            request.state.principal = auth_svc.decode_and_validate_jwt(token)
            return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=401, content={"detail": "未认证"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_check_auth_schema() -> None:
    if not settings.require_auth:
        return
    if not settings.jwt.secret.strip():
        raise RuntimeError("未配置 AUTOOPSHUB_JWT_SECRET，强制认证模式无法安全启动。")
    assert_auth_schema_present(settings)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str) -> dict[str, str]:
    return {"message": f"Hello {name}"}


@app.get("/api/health/logging")
async def logging_health() -> dict[str, Any]:
    st = log_mgr.status
    return {
        "backend_type": st.backend_type,
        "redis_configured": st.redis_configured,
        "redis_reachable": st.redis_reachable,
        "degrade_reason": st.degrade_reason,
        "non_persistent_note": "内存日志后端不保证跨进程或重启后保留",
    }


@app.get("/api/health/auth")
async def auth_health() -> dict[str, bool]:
    return {"require_auth": settings.require_auth}


@app.post("/api/auth/login")
async def auth_login(body: AuthLoginRequest) -> dict[str, Any]:
    _assert_auth_schema_ready()
    return auth_svc.login(body.mode, body.username, body.password)


@app.post("/api/auth/jwt/revoke", status_code=204)
async def auth_jwt_revoke(authorization: str | None = Header(None)) -> Response:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="需要 Bearer JWT")
    token = authorization.split(" ", 1)[1].strip()
    auth_svc.revoke_jwt_for_token(token)
    return Response(status_code=204)


@app.post("/api/auth/api-keys", status_code=201)
async def auth_create_api_key(body: ApiKeyCreateRequest) -> dict[str, Any]:
    _assert_auth_schema_ready()
    return auth_svc.create_api_key(body.name or "default")


@app.get("/api/auth/api-keys")
async def auth_list_api_keys() -> dict[str, list[dict[str, Any]]]:
    _assert_auth_schema_ready()
    rows = auth_svc.list_api_keys()
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "key_prefix": row["key_prefix"],
                "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                "revoked_at": row["revoked_at"].isoformat()
                if row.get("revoked_at") and hasattr(row["revoked_at"], "isoformat")
                else (str(row["revoked_at"]) if row.get("revoked_at") else None),
            }
        )
    return {"items": items}


@app.delete("/api/auth/api-keys/{key_id}", status_code=204)
async def auth_revoke_api_key(key_id: str) -> Response:
    _assert_auth_schema_ready()
    auth_svc.revoke_api_key(key_id)
    return Response(status_code=204)


@app.get("/api/workpieces")
async def list_workpieces() -> dict[str, list[dict[str, Any]]]:
    wp_root = _base_dir() / "workpieces"
    wp_root.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for child in wp_root.iterdir():
        if not child.is_dir():
            continue
        meta_file = child / "meta.json"
        if not meta_file.exists():
            continue
        meta = WorkpieceMeta.model_validate(_read_json(meta_file))
        items.append(
            {
                **meta.model_dump(),
                "stats": _workpiece_stats(meta.name),
            }
        )
    items.sort(key=lambda item: item["name"])
    return {"items": items}


@app.post("/api/workpieces/{workpiece_name}", status_code=201)
async def create_workpiece(workpiece_name: str, body: WorkpieceCreateRequest) -> dict[str, Any]:
    workpiece_name = _validate_workpiece_name_component(workpiece_name)
    root = _workpiece_dir(workpiece_name)
    if root.exists():
        raise HTTPException(status_code=409, detail="workpiece already exists")
    _ensure_workpiece_structure(workpiece_name)
    now = _utc_now()
    meta = WorkpieceMeta(name=workpiece_name, description=body.description, created_at=now, updated_at=now)
    _save_meta(meta)
    _save_setting(workpiece_name, WorkpieceSetting())
    return meta.model_dump()


@app.get("/api/workpieces/{workpiece_name}")
async def get_workpiece(workpiece_name: str) -> dict[str, Any]:
    meta = _load_meta(workpiece_name)
    detail = WorkpieceDetail(
        **meta.model_dump(),
        directory=str(_workpiece_dir(workpiece_name)),
        stats=_workpiece_stats(workpiece_name),
    )
    return detail.model_dump()


@app.put("/api/workpieces/{workpiece_name}")
async def update_workpiece(workpiece_name: str, body: WorkpieceUpdateRequest) -> dict[str, Any]:
    current = _load_meta(workpiece_name)
    new_name = _validate_workpiece_name_component(body.name) if body.name is not None else current.name
    new_desc = current.description if body.description is None else body.description
    if new_name != workpiece_name and _workpiece_dir(new_name).exists():
        raise HTTPException(status_code=409, detail="target workpiece name already exists")
    if new_name != workpiece_name:
        shutil.move(str(_workpiece_dir(workpiece_name)), str(_workpiece_dir(new_name)))
    updated = WorkpieceMeta(
        name=new_name,
        description=new_desc,
        created_at=current.created_at,
        updated_at=_utc_now(),
    )
    _save_meta(updated)
    return updated.model_dump()


@app.delete("/api/workpieces/{workpiece_name}", status_code=204)
async def delete_workpiece(workpiece_name: str) -> Response:
    workpiece_name = _validate_workpiece_name_component(workpiece_name)
    root = _workpiece_dir(workpiece_name)
    if not root.exists():
        raise HTTPException(status_code=404, detail="workpiece not found")
    shutil.rmtree(root)
    return Response(status_code=204)


@app.get("/api/workpieces/{workpiece_name}/setting")
async def get_setting(workpiece_name: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    return _load_setting(workpiece_name).model_dump()


@app.put("/api/workpieces/{workpiece_name}/setting")
async def update_setting(workpiece_name: str, body: WorkpieceSetting) -> dict[str, Any]:
    _load_meta(workpiece_name)
    _save_setting(workpiece_name, body)
    return body.model_dump()


@app.get("/api/workpieces/{workpiece_name}/runbooks")
async def list_runbooks(workpiece_name: str) -> dict[str, list[dict[str, Any]]]:
    _load_meta(workpiece_name)
    base = _workpiece_dir(workpiece_name) / "runbooks"
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        if path.name.endswith(".manifest.json"):
            continue
        rb = RunbookRecord.model_validate(_read_json(path))
        manifest = _load_manifest(workpiece_name, rb.name)
        items.append(
            {
                "name": rb.name,
                "type": rb.type.value,
                "description": rb.description,
                "content_mode": rb.content_mode,
                "entry_file": rb.entry_file,
                "files_summary": rb.files_summary,
                "created_at": rb.created_at,
                "updated_at": rb.updated_at,
                "manifest_summary": {"variables": len(manifest)},
            }
        )
    return {"items": items}


def _parse_manifest_field(raw: str | None) -> list[ManifestVariable] | None:
    if not raw or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"manifest must be valid JSON: {exc}") from exc
    if isinstance(payload, dict) and "items" in payload:
        payload = payload["items"]
    if not isinstance(payload, list):
        raise HTTPException(status_code=422, detail="manifest must be a JSON array")
    return [ManifestVariable.model_validate(item) for item in payload]


def _upsert_inline_runbook(workpiece_name: str, runbook_name: str, body: RunbookUpsertRequest) -> dict[str, Any]:
    _load_meta(workpiece_name)
    exists = _runbook_exists(workpiece_name, runbook_name)
    now = _utc_now()
    old_created_at = now
    if exists:
        old_created_at = _load_runbook(workpiece_name, runbook_name).created_at
    if body.type == RunbookType.SCRIPT and body.runtime and body.runtime.lower() == "powershell":
        raise HTTPException(status_code=422, detail="powershell runtime is not allowed")
    if body.type == RunbookType.WORKFLOW:
        _validate_workflow_references(workpiece_name, runbook_name, body.content)
    _validate_runbook_manifest_on_create(body.content, body.manifest)
    runbook = RunbookRecord(
        name=runbook_name,
        type=body.type,
        description=body.description,
        content=body.content,
        runtime=body.runtime,
        content_mode="inline",
        entry_file=None,
        files_summary={},
        created_at=old_created_at,
        updated_at=now,
    )
    _save_runbook(workpiece_name, runbook)
    _delete_runbook_file_package(workpiece_name, runbook_name)
    template_vars = _combined_template_var_names(body.content, include_all_system=True)
    merged_manifest = _normalize_manifest(template_vars, body.manifest)
    _save_manifest(workpiece_name, runbook_name, merged_manifest)
    return _runbook_payload(workpiece_name, runbook)


async def _upsert_file_package_runbook(workpiece_name: str, runbook_name: str, request: Request) -> dict[str, Any]:
    _load_meta(workpiece_name)
    fields, files = await _uploaded_package_files(request)
    runbook_type = RunbookType(fields.get("type", "Terraform"))
    if runbook_type != RunbookType.TERRAFORM:
        raise HTTPException(status_code=422, detail="文件包 runbook 初期仅支持 Terraform 类型")
    manifest = _parse_manifest_field(fields.get("manifest"))
    description = fields.get("description", "")
    runtime = fields.get("runtime") or None
    entry_file = _select_entry_file(files, fields.get("entry_file"))
    exists = _runbook_exists(workpiece_name, runbook_name)
    now = _utc_now()
    old_created_at = _load_runbook(workpiece_name, runbook_name).created_at if exists else now

    _replace_runbook_file_package(workpiece_name, runbook_name, files)
    runbook = RunbookRecord(
        name=runbook_name,
        type=runbook_type,
        description=description,
        content="",
        runtime=runtime,
        content_mode="files",
        entry_file=entry_file,
        files_summary=_files_summary(files),
        created_at=old_created_at,
        updated_at=now,
    )
    _save_runbook(workpiece_name, runbook)
    template_vars = _file_package_template_vars(workpiece_name, runbook_name, include_all_system=True)
    merged_manifest = _normalize_manifest(template_vars, manifest)
    _save_manifest(workpiece_name, runbook_name, merged_manifest)
    return _runbook_payload(workpiece_name, runbook)


@app.post("/api/workpieces/{workpiece_name}/runbooks/{runbook_name}", status_code=201)
async def upsert_runbook(workpiece_name: str, runbook_name: str, request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
        return await _upsert_file_package_runbook(workpiece_name, runbook_name, request)
    body = RunbookUpsertRequest.model_validate(await request.json())
    return _upsert_inline_runbook(workpiece_name, runbook_name, body)


@app.get("/api/workpieces/{workpiece_name}/runbooks/{runbook_name}")
async def get_runbook(workpiece_name: str, runbook_name: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    runbook = _load_runbook(workpiece_name, runbook_name)
    return _runbook_payload(workpiece_name, runbook)


@app.delete("/api/workpieces/{workpiece_name}/runbooks/{runbook_name}", status_code=204)
async def delete_runbook(workpiece_name: str, runbook_name: str) -> Response:
    _load_meta(workpiece_name)
    runbook = _runbook_path(workpiece_name, runbook_name)
    if not runbook.exists():
        raise HTTPException(status_code=404, detail="runbook not found")
    manifest = _manifest_path(workpiece_name, runbook_name)
    runbook.unlink(missing_ok=True)
    manifest.unlink(missing_ok=True)
    _delete_runbook_file_package(workpiece_name, runbook_name)
    return Response(status_code=204)


@app.get("/api/workpieces/{workpiece_name}/runbooks/{runbook_name}/manifest")
async def get_runbook_manifest(workpiece_name: str, runbook_name: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    _load_runbook(workpiece_name, runbook_name)
    manifest = _load_manifest(workpiece_name, runbook_name)
    return {"items": [m.model_dump() for m in manifest]}


@app.post("/api/workpieces/{workpiece_name}/runbooks/{runbook_name}/manifest")
async def upsert_runbook_manifest(workpiece_name: str, runbook_name: str, body: ManifestUpsertRequest) -> dict[str, Any]:
    _load_meta(workpiece_name)
    runbook = _load_runbook(workpiece_name, runbook_name)
    names = [m.name for m in body.manifest]
    dups = detect_duplicate_names(names)
    if dups:
        raise HTTPException(status_code=422, detail=f"manifest 变量重复声明: {', '.join(dups)}")
    if runbook.content_mode == "files":
        vars_from_template = _file_package_template_vars(workpiece_name, runbook_name, include_all_system=True)
    else:
        vars_from_template = _combined_template_var_names(runbook.content, include_all_system=True)
    current = {item.name: item for item in _load_manifest(workpiece_name, runbook_name)}
    for incoming in body.manifest:
        if incoming.name in SYSTEM_RESERVED_NAMES and incoming.name not in vars_from_template:
            raise HTTPException(status_code=422, detail="禁止在 manifest 中声明未知系统保留变量")
        current[incoming.name] = incoming
    merged = _normalize_manifest(vars_from_template, list(current.values()), allow_extra_user_vars=True)
    _save_manifest(workpiece_name, runbook_name, merged)
    return {"items": [m.model_dump() for m in merged]}


@app.post("/api/workpieces/{workpiece_name}/runbooks/{runbook_name}/trigger")
async def trigger_runbook(
    workpiece_name: str,
    runbook_name: str,
    body: TriggerRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    _load_meta(workpiece_name)
    _load_runbook(workpiece_name, runbook_name)
    manifest = _load_manifest(workpiece_name, runbook_name)
    missing_pre, unknown_pre, _ = _validate_variables(manifest, body.variables)

    if not manifest and body.variables:
        raise HTTPException(status_code=422, detail="runbook has no variables but request provided variables")
    if unknown_pre:
        raise HTTPException(
            status_code=422,
            detail={"message": "unknown variables in request", "unknown_variables": unknown_pre, "manifest": [m.model_dump() for m in manifest]},
        )

    task, manifest, missing, unknown = _create_task_from_runbook(
        workpiece_name, runbook_name, body.variables, TaskSource.MANUAL, background_tasks
    )

    payload = {"task": task.model_dump(), "manifest": [m.model_dump() for m in manifest], "missing_required": missing}
    if missing:
        return JSONResponse(content=payload, status_code=202)
    return JSONResponse(content=payload, status_code=201)


@app.get("/api/workpieces/{workpiece_name}/tasks")
async def list_tasks(workpiece_name: str) -> dict[str, list[dict[str, Any]]]:
    _load_meta(workpiece_name)
    items = []
    for task in _list_tasks(workpiece_name):
        items.append(
            {
                "task_id": task.task_id,
                "runbook_name": task.runbook_name,
                "source": task.source.value,
                "status": task.status.value,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "variables_summary": {"count": len(task.variables)},
            }
        )
    return {"items": items}


@app.get("/api/workpieces/{workpiece_name}/tasks/{task_id}")
async def get_task(workpiece_name: str, task_id: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    return _load_task(workpiece_name, task_id).model_dump()


@app.put("/api/workpieces/{workpiece_name}/tasks/{task_id}/variables")
async def update_task_variables(workpiece_name: str, task_id: str, body: TaskVariablesUpdateRequest) -> dict[str, Any]:
    _load_meta(workpiece_name)
    task = _load_task(workpiece_name, task_id)
    if task.status in {TaskStatus.RUNNING, TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELED}:
        raise HTTPException(status_code=409, detail="cannot update variables for executed task")
    manifest = _load_manifest(workpiece_name, task.runbook_name)
    _validate_task_variables_against_readonly(manifest, body.variables)
    _, unknown, _ = _validate_variables(manifest, body.variables)
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown_variables": unknown, "manifest": [m.model_dump() for m in manifest]})
    task.variables = body.variables
    task.updated_at = _utc_now()
    _save_task(workpiece_name, task)
    return task.model_dump()


@app.post("/api/workpieces/{workpiece_name}/tasks/{task_id}/confirm")
async def confirm_task(workpiece_name: str, task_id: str, background_tasks: BackgroundTasks) -> Response:
    _load_meta(workpiece_name)
    task = _load_task(workpiece_name, task_id)
    if task.status == TaskStatus.CANCELED:
        raise HTTPException(status_code=409, detail="task already canceled")
    manifest = _load_manifest(workpiece_name, task.runbook_name)
    missing, unknown, _ = _validate_variables(manifest, task.variables)
    if missing or unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "missing_required": missing,
                "unknown_variables": unknown,
                "manifest": [m.model_dump() for m in manifest],
            },
        )
    task.error_summary = ""
    _save_task(workpiece_name, task)
    background_tasks.add_task(_execute_task, workpiece_name, task)
    return Response(content=json.dumps({"task": task.model_dump()}, ensure_ascii=False), status_code=202, media_type="application/json")


@app.post("/api/tasks/{task_id}/rerun", status_code=201)
async def rerun_task(task_id: str, background_tasks: BackgroundTasks, body: TaskRerunRequest | None = None) -> dict[str, Any]:
    workpiece_name, original = _find_task_workpiece(task_id)
    variables = {**original.variables, **((body.variables if body is not None else {}) or {})}
    runbook = _load_runbook(workpiece_name, original.runbook_name)
    inherited_runtime_dir = None
    if runbook.type == RunbookType.TERRAFORM:
        inherited_runtime_dir = Path(str(original.schedule.get("runtime_dir") or _task_runtime_dir(original.task_id)))
    try:
        manifest = _load_manifest(workpiece_name, original.runbook_name)
        _validate_task_variables_against_readonly(manifest, variables)
        missing, unknown, _ = _validate_variables(manifest, variables)
        if missing or unknown:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "rerun variables failed validation",
                    "missing_required": missing,
                    "unknown_variables": unknown,
                    "manifest": [m.model_dump() for m in manifest],
                },
            )
        task, manifest, missing, unknown = _create_task_from_runbook(
            workpiece_name,
            original.runbook_name,
            variables,
            original.source,
            background_tasks,
            inherited_runtime_dir,
        )
    except HTTPException as exc:
        if exc.status_code == 422:
            raise HTTPException(status_code=400, detail=exc.detail) from exc
        raise
    return {"task": task.model_dump(), "manifest": [m.model_dump() for m in manifest], "missing_required": missing}


@app.post("/api/workpieces/{workpiece_name}/tasks/{task_id}/cancel")
async def cancel_task(workpiece_name: str, task_id: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    task = _load_task(workpiece_name, task_id)
    if task.status in {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELED}:
        raise HTTPException(status_code=409, detail="task already finished")
    task.status = TaskStatus.CANCELED
    task.updated_at = _utc_now()
    _save_task(workpiece_name, task)
    return task.model_dump()


def _read_task_logs(workpiece_name: str, task_id: str, after: int, limit: int) -> list[dict[str, Any]]:
    return log_mgr.backend.read_after(workpiece_name, task_id, after, limit)


@app.get("/api/workpieces/{workpiece_name}/tasks/{task_id}/logs")
async def get_task_logs(workpiece_name: str, task_id: str, after: int = 0, limit: int = 200) -> dict[str, Any]:
    _load_meta(workpiece_name)
    _load_task(workpiece_name, task_id)
    capped = min(max(limit, 1), 500)
    rows = _read_task_logs(workpiece_name, task_id, after, capped)
    return {"items": rows}


@app.get("/api/workpieces/{workpiece_name}/tasks/{task_id}/logs/stream")
async def stream_task_logs(
    workpiece_name: str,
    task_id: str,
    follow: int = 0,
) -> StreamingResponse:
    _load_meta(workpiece_name)
    _load_task(workpiece_name, task_id)

    def event_iter():
        rows = log_mgr.backend.read_after(workpiece_name, task_id, 0, 10000)
        for row in rows:
            yield f"data: {json.dumps(row, ensure_ascii=False)}\n\n"
        if follow:
            import time

            last = max((int(r.get("log_seq", 0)) for r in rows), default=0)
            while True:
                batch = log_mgr.backend.read_after(workpiece_name, task_id, last, 200)
                if not batch:
                    time.sleep(0.4)
                    continue
                for row in batch:
                    last = max(last, int(row.get("log_seq", 0)))
                    yield f"data: {json.dumps(row, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_iter(), media_type="text/event-stream")


@app.get("/api/workpieces/{workpiece_name}/jobs")
async def list_jobs(workpiece_name: str) -> dict[str, list[dict[str, Any]]]:
    _load_meta(workpiece_name)
    jobs_dir = _workpiece_dir(workpiece_name) / "jobs"
    items: list[dict[str, Any]] = []
    for path in sorted(jobs_dir.glob("*.json")):
        job = JobRecord.model_validate(_read_json(path))
        items.append(
            {
                "job_name": job.job_name,
                "description": job.description,
                "cron": job.cron,
                "runbook_name": job.runbook_name,
                "enabled": job.enabled,
                "next_run_at": job.next_run_at,
            }
        )
    return {"items": items}


@app.get("/api/workpieces/{workpiece_name}/jobs/{job_name}")
async def get_job(workpiece_name: str, job_name: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    return _load_job(workpiece_name, job_name).model_dump()


@app.post("/api/workpieces/{workpiece_name}/jobs/{job_name}", status_code=201)
async def create_job(workpiece_name: str, job_name: str, body: JobUpsertRequest) -> dict[str, Any]:
    _load_meta(workpiece_name)
    if _job_path(workpiece_name, job_name).exists():
        raise HTTPException(status_code=409, detail="job already exists")
    if not _validate_cron(body.cron):
        raise HTTPException(status_code=422, detail="invalid cron expression")
    if not body.runbook_name:
        raise HTTPException(status_code=422, detail="runbook_name is required")
    if not _runbook_exists(workpiece_name, body.runbook_name):
        raise HTTPException(status_code=422, detail="target runbook not found")
    now = _utc_now()
    job = JobRecord(
        job_name=job_name,
        description=body.description,
        cron=body.cron,
        runbook_name=body.runbook_name,
        variables=body.variables,
        enabled=body.enabled,
        next_run_at=_next_run_at(body.cron) if body.enabled else None,
        created_at=now,
        updated_at=now,
    )
    _save_job(workpiece_name, job)
    return job.model_dump()


@app.put("/api/workpieces/{workpiece_name}/jobs/{job_name}")
async def update_job(workpiece_name: str, job_name: str, body: JobUpsertRequest) -> dict[str, Any]:
    _load_meta(workpiece_name)
    current = _load_job(workpiece_name, job_name)
    runbook_name = body.runbook_name or current.runbook_name
    target_name = body.job_name or job_name
    if target_name != job_name and _job_path(workpiece_name, target_name).exists():
        raise HTTPException(status_code=409, detail="target job name already exists")
    if not _validate_cron(body.cron):
        raise HTTPException(status_code=422, detail="invalid cron expression")
    if not _runbook_exists(workpiece_name, runbook_name):
        raise HTTPException(status_code=422, detail="target runbook not found")
    updated = JobRecord(
        job_name=target_name,
        description=body.description,
        cron=body.cron,
        runbook_name=runbook_name,
        variables=body.variables if "variables" in body.model_fields_set else current.variables,
        enabled=body.enabled,
        next_run_at=_next_run_at(body.cron) if body.enabled else None,
        created_at=current.created_at,
        updated_at=_utc_now(),
    )
    if target_name != job_name:
        _job_path(workpiece_name, job_name).unlink(missing_ok=True)
    _save_job(workpiece_name, updated)
    return updated.model_dump()


@app.delete("/api/workpieces/{workpiece_name}/jobs/{job_name}", status_code=204)
async def delete_job(workpiece_name: str, job_name: str) -> Response:
    _load_meta(workpiece_name)
    path = _job_path(workpiece_name, job_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="job not found")
    path.unlink(missing_ok=True)
    return Response(status_code=204)


@app.post("/api/workpieces/{workpiece_name}/jobs/{job_name}/trigger", status_code=201)
async def trigger_job(workpiece_name: str, job_name: str) -> dict[str, Any]:
    _load_meta(workpiece_name)
    job = _load_job(workpiece_name, job_name)
    task, manifest, missing, unknown = _create_task_from_runbook(
        workpiece_name, job.runbook_name, job.variables, TaskSource.JOB
    )
    job.next_run_at = _next_run_at(job.cron) if job.enabled else None
    job.updated_at = _utc_now()
    _save_job(workpiece_name, job)
    return {"task": task.model_dump(), "manifest": [m.model_dump() for m in manifest], "missing_required": missing, "unknown_variables": unknown}
