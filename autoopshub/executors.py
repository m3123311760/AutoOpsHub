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

from autoopshub.runtime_commands import check_command_available, check_tokens_available
from autoopshub.settings import AppSettings


LogFn = Callable[[str, str], None]  # level, message


@dataclass
class ExecResult:
    exit_code: int
    error_summary: str


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
        return ExecResult(124, "runtime execution timeout")
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    summary = "" if exit_code == 0 else f"命令退出码 {exit_code}: {' '.join(argv)}"
    return ExecResult(int(exit_code), summary)


def _parse_script_command_from_first_line(rendered_text: str) -> str | None:
    lines = rendered_text.splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    return first if first else None


def build_script_argv(
    settings: AppSettings,
    rendered_path: Path,
    rendered_text: str,
    runbook_runtime: str | None,
) -> list[str]:
    """Script：优先 runbook.runtime；否则 shebang；否则首行命令；否则默认 shell。"""

    stripped = rendered_text.lstrip()
    if stripped.startswith("#!"):
        if os.name == "nt":
            return ["cmd", "/c", str(rendered_path)]
        shell = settings.runtime_commands.default_script_shell
        return [shell, str(rendered_path)]

    if runbook_runtime and runbook_runtime.strip():
        parts = shlex.split(runbook_runtime, posix=os.name != "nt")
        if parts:
            return parts + [str(rendered_path)]
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
) -> ExecResult:
    tf = settings.runtime_commands.terraform_bin
    chk = check_command_available(tf)
    if not chk.ok:
        log("error", chk.message)
        return ExecResult(127, chk.message)
    target = cwd / "main.tf"
    target.write_bytes(rendered_path.read_bytes())
    r1 = run_subprocess_with_logging([tf, "init", "-input=false"], cwd, None, timeout_sec // 2 or 30, log)
    if r1.exit_code != 0:
        return r1
    return run_subprocess_with_logging([tf, "apply", "-input=false", "-auto-approve"], cwd, None, timeout_sec, log)


def run_ansible(
    settings: AppSettings,
    cwd: Path,
    playbook: Path,
    inventory_path: str | None,
    timeout_sec: int,
    log: LogFn,
) -> ExecResult:
    ap = settings.runtime_commands.ansible_playbook_bin
    chk = check_command_available(ap)
    if not chk.ok:
        log("error", chk.message)
        return ExecResult(127, chk.message)
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
    chk = check_tokens_available(argv)
    if not chk.ok:
        log("error", chk.message)
        return ExecResult(127, chk.message)
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
    if rt == "Terraform":
        return run_terraform(settings, cwd, rendered_path, timeout_sec, log)
    if rt == "Ansible":
        inv = variables.get("system.inventory_file")
        inv_s = str(inv) if inv is not None else None
        return run_ansible(settings, cwd, rendered_path, inv_s, timeout_sec, log)
    if rt == "Script":
        return run_script(settings, cwd, rendered_path, rendered_text, runbook_runtime, timeout_sec, log)
    # Workflow 等：不执行外部命令
    log("info", f"runbook 类型 {rt} 跳过外部 runtime 执行")
    return ExecResult(0, "")
