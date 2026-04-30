"""Runbook 运行时执行：Terraform、Ansible、Script。"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jinja2 import Template

from autoopshub.runtime_commands import check_command_available, check_tokens_available
from autoopshub.settings import AppSettings


LogFn = Callable[[str, str], None]  # level, message


@dataclass
class ExecResult:
    exit_code: int
    error_summary: str
    command: list[str] | None = None


def _runtime_template_context(variables: dict[str, Any]) -> dict[str, Any]:
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


def build_runtime_override_argv(command_template: str | None, variables: dict[str, Any]) -> list[str] | None:
    if not command_template or not command_template.strip():
        return None
    rendered = Template(command_template).render(**_runtime_template_context(variables)).strip()
    if not rendered:
        return None
    return shlex.split(rendered, posix=os.name != "nt")


def _is_terraform_cli(argv: list[str], terraform_bin: str) -> bool:
    if not argv:
        return False
    command = Path(argv[0]).name.lower()
    configured = Path(terraform_bin).name.lower()
    return command == configured or command == "terraform"


def _split_terraform_chdir(argv: list[str]) -> tuple[list[str], list[str]]:
    chdir_flags = [token for token in argv[1:] if token.startswith("-chdir=")]
    rest = [argv[0], *[token for token in argv[1:] if not token.startswith("-chdir=")]]
    return chdir_flags, rest


def normalize_terraform_override_argv(argv: list[str], terraform_bin: str) -> tuple[list[str], list[str] | None]:
    if not _is_terraform_cli(argv, terraform_bin):
        return argv, None
    chdir_flags, rest = _split_terraform_chdir(argv)
    normalized = [rest[0], *chdir_flags, *rest[1:]]
    subcommand = next((token for token in rest[1:] if not token.startswith("-")), "")
    init_argv = None if subcommand == "init" else [rest[0], *chdir_flags, "init", "-input=false"]
    return normalized, init_argv


def _stream_reader(stream: Any, level: str, log: LogFn) -> None:
    try:
        for line in iter(stream.readline, b""):
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                log(level, text)
    finally:
        stream.close()


def run_subprocess_with_logging(
    argv: list[str],
    cwd: Path,
    env: dict[str, str] | None,
    timeout_sec: int,
    log: LogFn,
) -> ExecResult:
    """启动子进程并采集 stdout/stderr；超时则终止。"""

    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=False,
    )
    assert proc.stdout and proc.stderr
    t_out = threading.Thread(target=_stream_reader, args=(proc.stdout, "info", log), daemon=True)
    t_err = threading.Thread(target=_stream_reader, args=(proc.stderr, "error", log), daemon=True)
    t_out.start()
    t_err.start()
    try:
        exit_code = proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        log("error", f"runtime 执行超时（{timeout_sec}s），进程已终止")
        return ExecResult(124, "runtime execution timeout", argv)
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    summary = "" if exit_code == 0 else f"命令退出码 {exit_code}: {' '.join(argv)}"
    return ExecResult(int(exit_code), summary, argv)


def _parse_script_command_from_first_line(rendered_text: str) -> str | None:
    lines = rendered_text.splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    return first if first else None


def _has_shebang(rendered_text: str) -> bool:
    return rendered_text.lstrip().startswith("#!")


def build_script_argv(
    settings: AppSettings,
    rendered_path: Path,
    rendered_text: str,
    runbook_runtime: str | None,
) -> list[str]:
    """Script：优先 runbook.runtime；否则 shebang；否则首行命令；否则默认 shell。"""

    if runbook_runtime and runbook_runtime.strip():
        parts = shlex.split(runbook_runtime, posix=os.name != "nt")
        if parts:
            return parts + [str(rendered_path)]
    if _has_shebang(rendered_text):
        if os.name == "nt":
            return ["cmd", "/c", str(rendered_path)]
        return [str(rendered_path)]
    cmd_line = _parse_script_command_from_first_line(rendered_text)
    if cmd_line:
        try:
            parts = shlex.split(cmd_line, posix=os.name != "nt")
        except ValueError:
            parts = [cmd_line]
        if parts:
            return parts + [str(rendered_path)]
    if os.name == "nt":
        return ["cmd", "/c", str(rendered_path)]
    shell = settings.runtime_commands.default_script_shell
    return [shell, str(rendered_path)]


def run_terraform(
    settings: AppSettings,
    cwd: Path,
    rendered_path: Path,
    timeout_sec: int,
    log: LogFn,
    override_argv: list[str] | None = None,
) -> ExecResult:
    terraform_cwd = rendered_path.parent if rendered_path.suffix == ".tf" else cwd
    if rendered_path.suffix != ".tf":
        target = cwd / "main.tf"
        try:
            same_target = target.resolve() == rendered_path.resolve()
        except FileNotFoundError:
            same_target = False
        if not same_target:
            target.write_bytes(rendered_path.read_bytes())
    if override_argv:
        chk = check_tokens_available(override_argv)
        if not chk.ok:
            log("error", chk.message)
            return ExecResult(127, chk.message, override_argv)
        normalized_argv, init_argv = normalize_terraform_override_argv(override_argv, settings.runtime_commands.terraform_bin)
        if init_argv:
            r1 = run_subprocess_with_logging(init_argv, terraform_cwd, None, timeout_sec // 2 or 30, log)
            if r1.exit_code != 0:
                return r1
        return run_subprocess_with_logging(normalized_argv, terraform_cwd, None, timeout_sec, log)
    tf = settings.runtime_commands.terraform_bin
    chk = check_command_available(tf)
    if not chk.ok:
        log("error", chk.message)
        return ExecResult(127, chk.message, [tf])
    r1 = run_subprocess_with_logging([tf, "init", "-input=false"], terraform_cwd, None, timeout_sec // 2 or 30, log)
    if r1.exit_code != 0:
        return r1
    return run_subprocess_with_logging([tf, "apply", "-input=false", "-auto-approve"], terraform_cwd, None, timeout_sec, log)


def run_ansible(
    settings: AppSettings,
    cwd: Path,
    playbook: Path,
    inventory_path: str | None,
    timeout_sec: int,
    log: LogFn,
    override_argv: list[str] | None = None,
) -> ExecResult:
    if override_argv:
        chk = check_tokens_available(override_argv)
        if not chk.ok:
            log("error", chk.message)
            return ExecResult(127, chk.message, override_argv)
        return run_subprocess_with_logging(override_argv, cwd, None, timeout_sec, log)
    ap = settings.runtime_commands.ansible_playbook_bin
    chk = check_command_available(ap)
    if not chk.ok:
        log("error", chk.message)
        return ExecResult(127, chk.message, [ap])
    inv = inventory_path or str(cwd / "inventory.ini")
    Path(inv).parent.mkdir(parents=True, exist_ok=True)
    if not Path(inv).exists():
        Path(inv).write_text("localhost ansible_connection=local\n", encoding="utf-8")
    argv = [ap, "-i", inv, str(playbook)]
    return run_subprocess_with_logging(argv, cwd, None, timeout_sec, log)


def run_script(
    settings: AppSettings,
    cwd: Path,
    rendered_path: Path,
    rendered_text: str,
    runbook_runtime: str | None,
    timeout_sec: int,
    log: LogFn,
) -> ExecResult:
    argv = build_script_argv(settings, rendered_path, rendered_text, runbook_runtime)
    if os.name != "nt" and _has_shebang(rendered_text) and not (runbook_runtime and runbook_runtime.strip()):
        rendered_path.chmod(rendered_path.stat().st_mode | 0o700)
    chk = check_tokens_available(argv)
    if not chk.ok:
        log("error", chk.message)
        return ExecResult(127, chk.message, argv)
    return run_subprocess_with_logging(argv, cwd, None, timeout_sec, log)


def dispatch_execution(
    settings: AppSettings,
    runbook_type: str,
    cwd: Path,
    rendered_path: Path,
    rendered_text: str,
    runbook_runtime: str | None,
    variables: dict[str, Any],
    timeout_sec: int,
    log: LogFn,
) -> ExecResult:
    rt = runbook_type
    override_argv = build_runtime_override_argv(str(variables.get("system.set_runtime", "")), variables)
    if rt == "Terraform":
        return run_terraform(settings, cwd, rendered_path, timeout_sec, log, override_argv)
    if rt == "Ansible":
        inv = variables.get("system.inventory_file")
        inv_s = str(inv) if inv is not None else None
        return run_ansible(settings, cwd, rendered_path, inv_s, timeout_sec, log, override_argv)
    if rt == "Script":
        return run_script(settings, cwd, rendered_path, rendered_text, runbook_runtime, timeout_sec, log)
    # Workflow 等：不执行外部命令
    log("info", f"runbook 类型 {rt} 跳过外部 runtime 执行")
    return ExecResult(0, "")
