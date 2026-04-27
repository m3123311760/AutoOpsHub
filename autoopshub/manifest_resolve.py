"""Manifest 默认值嵌套解析与循环引用检测。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, meta
from jinja2 import Template


@dataclass
class ManifestItem:
    name: str
    default_value: str = ""


def extract_system_refs_from_template(content: str) -> set[str]:
    """从模板中提取 `{{ system.xxx }}` 形式的占位符名称。"""

    return set(re.findall(r"\{\{\s*(system\.\w+)\s*\}\}", content))


def extract_user_template_vars(content: str) -> set[str]:
    """Jinja2 未声明变量，并剔除裸 `system`（由 system.xxx 单独处理）。"""

    env = Environment()
    parsed = env.parse(content)
    names = set(meta.find_undeclared_variables(parsed))
    names.discard("system")
    return names


def template_assigns_system_var(content: str) -> bool:
    """检测 `{% set system.xxx ... %}` 等非法赋值。"""

    return bool(re.search(r"\{%\s*set\s+system\.\w+", content, flags=re.IGNORECASE))


def detect_duplicate_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    dups: set[str] = set()
    for n in names:
        if n in seen:
            dups.add(n)
        seen.add(n)
    return sorted(dups)


def resolve_nested_defaults(items: dict[str, ManifestItem], task_vars: dict[str, Any]) -> dict[str, str]:
    """
    根据 manifest 默认值与 task 变量迭代渲染嵌套默认值；不收敛则视为循环引用。
    """

    env = Environment(variable_start_string="{{", variable_end_string="}}")
    resolved: dict[str, str] = {k: v.default_value for k, v in items.items()}
    for k, v in task_vars.items():
        if k in resolved:
            resolved[k] = str(v)

    explicit_keys = set(task_vars.keys())
    names = list(items.keys())
    max_rounds = max(3, len(names) * 5 + 3)

    for _ in range(max_rounds):
        changed = False
        ctx: dict[str, Any] = {**resolved, **task_vars}
        for name in names:
            if name in explicit_keys:
                continue
            raw = items[name].default_value
            before = resolved.get(name, "")
            tmpl = env.from_string(raw)
            new_val = tmpl.render(**ctx)
            if new_val != before:
                resolved[name] = new_val
                changed = True
        if not changed:
            return resolved

    raise ValueError("manifest 默认值存在循环引用或未能在限定轮次内收敛")


def merge_task_variables(resolved_defaults: dict[str, str], task_vars: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(resolved_defaults)
    for k, v in task_vars.items():
        out[k] = v
    return out


def render_runbook_content(content: str, variables: dict[str, Any]) -> str:
    return Template(content).render(**variables)
