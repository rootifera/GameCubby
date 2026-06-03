#!/usr/bin/env python3
"""Compare the current FastAPI OpenAPI schema against a local snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "openapi.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Baseline not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from None

    if not isinstance(data, dict):
        raise SystemExit(f"Expected top-level JSON object in {path}")
    return data


def current_openapi() -> dict[str, Any]:
    try:
        from gamecubby_api.main import app
    except Exception as exc:
        raise SystemExit(
            "Could not import gamecubby_api.main to generate OpenAPI.\n"
            "If your local app import needs Postgres, set DB_HOST/DB_PORT/"
            f"DB_NAME/DB_USER/DB_PASSWORD first.\nOriginal error: {exc}"
        ) from exc

    schema = app.openapi()
    if not isinstance(schema, dict):
        raise SystemExit("app.openapi() did not return a JSON object")
    return schema


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def summarize_dict_diff(name: str, baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    old_keys = set(baseline)
    new_keys = set(current)

    for key in sorted(new_keys - old_keys):
        lines.append(f"+ {name}: {key}")
    for key in sorted(old_keys - new_keys):
        lines.append(f"- {name}: {key}")
    for key in sorted(old_keys & new_keys):
        if canonical(baseline[key]) != canonical(current[key]):
            lines.append(f"~ {name}: {key}")
    return lines


def compare(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    lines.extend(summarize_dict_diff("path", baseline.get("paths", {}), current.get("paths", {})))

    old_components = baseline.get("components", {})
    new_components = current.get("components", {})
    if isinstance(old_components, dict) and isinstance(new_components, dict):
        for section in sorted(set(old_components) | set(new_components)):
            old_section = old_components.get(section, {})
            new_section = new_components.get(section, {})
            if isinstance(old_section, dict) and isinstance(new_section, dict):
                lines.extend(summarize_dict_diff(f"component.{section}", old_section, new_section))
            elif canonical(old_section) != canonical(new_section):
                lines.append(f"~ component.{section}")
    elif canonical(old_components) != canonical(new_components):
        lines.append("~ components")

    for key in ("openapi", "info", "servers", "security", "tags"):
        if canonical(baseline.get(key)) != canonical(current.get(key)):
            lines.append(f"~ top-level: {key}")

    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="OpenAPI snapshot to compare against. Defaults to ./openapi.json.",
    )
    parser.add_argument(
        "--write-current",
        type=Path,
        help="Write the generated current OpenAPI schema to this path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_path = args.baseline.resolve()
    baseline = load_json(baseline_path)
    current = current_openapi()

    if args.write_current:
        write_json(args.write_current.resolve(), current)

    differences = compare(baseline, current)
    if not differences:
        print(f"OpenAPI contract matches {baseline_path}")
        return 0

    print(f"OpenAPI contract changed compared with {baseline_path}:")
    for line in differences:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
