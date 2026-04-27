"""运行时命令可用性检查。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Sequence


@dataclass
class RuntimeCheckResult:
    ok: bool
    command: str
    message: str


def check_command_available(argv0: str) -> RuntimeCheckResult:
    """检查可执行文件是否在 PATH 中或路径存在。"""

    if not argv0.strip():
        return RuntimeCheckResult(False, argv0, "runtime 命令为空")
    path = shutil.which(argv0)
    if path:
        return RuntimeCheckResult(True, argv0, path)
    p = argv0
    if "/" in p or "\\" in p:
        from pathlib import Path

        if Path(p).is_file():
            return RuntimeCheckResult(True, argv0, str(Path(p).resolve()))
    return RuntimeCheckResult(False, argv0, f"未找到可执行文件: {argv0}")


def check_tokens_available(tokens: Sequence[str]) -> RuntimeCheckResult:
    """将命令行拆分为首个 token 做 PATH 检查。"""

    if not tokens:
        return RuntimeCheckResult(False, "", "命令为空")
    head = tokens[0]
    return check_command_available(head)
