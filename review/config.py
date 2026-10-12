"""Load config.yaml, layer the profile underneath it, validate the result."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles"


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_profile(name: str) -> dict:
    path = PROFILES / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No profile named '{name}' in {PROFILES}")
    prof = yaml.safe_load(path.read_text()) or {}
    parent = prof.pop("extends", None)
    if parent:
        prof = _deep_merge(load_profile(parent), prof)
    return prof


def load_config(path: str | Path) -> dict:
    path = Path(path)
    cfg = yaml.safe_load(path.read_text()) or {}
    profile_name = cfg.get("profile", "generic")
    profile = load_profile(profile_name)

    # Profile supplies defaults; config wins.
    merged = {
        "business": cfg.get("business", {}),
        "profile": profile_name,
        "vocabulary": _deep_merge(profile.get("vocabulary", {}), cfg.get("vocabulary", {})),
        "rules": _deep_merge(profile.get("rules", {}), cfg.get("rules", {})),
        "playbooks": _deep_merge(profile.get("playbooks", {}), cfg.get("playbooks", {})),
        "decomposition": profile.get("decomposition", {}),
        "measure_spec": profile.get("measures", {}),
        "extra_dimensions": profile.get("extra_dimensions", {}),
        "segments": profile.get("segments", {}),
        "warehouse": cfg.get("warehouse", {}),
        "source": cfg.get("source"),
        "columns": cfg.get("columns", {}),
        "measures": cfg.get("measures", {}),
        "filters": cfg.get("filters", {}),
        "output": cfg.get("output", {"dir": "out"}),
        "holiday_calendar": cfg.get("holiday_calendar"),
        "holidays": cfg.get("holidays", []),
        "_config_path": str(path),
    }
    validate(merged)
    return merged


def validate(cfg: dict) -> None:
    problems = []
    if not cfg.get("source"):
        problems.append("config.source is required (a table, view, or subquery)")
    for col in ("date", "unit"):
        if not cfg["columns"].get(col):
            problems.append(f"config.columns.{col} is required")
    for m in cfg["measure_spec"].get("required", ["revenue", "orders"]):
        if not cfg["measures"].get(m):
            problems.append(f"config.measures.{m} is required by the '{cfg['profile']}' profile")
    for dim, spec in cfg.get("extra_dimensions", {}).items():
        if spec.get("required") and not (cfg["columns"].get(dim) or spec.get("default_expr")):
            problems.append(f"config.columns.{dim} is required by the profile")
    if problems:
        raise ValueError("Config problems:\n  - " + "\n  - ".join(problems))
