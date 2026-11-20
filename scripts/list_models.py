"""List the models this project's gateway key can call.

Usage:
    python scripts/list_models.py                 # grouped by capability
    python scripts/list_models.py --roles         # project role table
    python scripts/list_models.py --check         # verify configured role ids
    python scripts/list_models.py --capability image
    python scripts/list_models.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.core.config.model_catalog import (  # noqa: E402
    MODEL_ROLES,
    available_models,
    gateway,
    missing_role_models,
    models_by_capability,
    resolve_model,
)


def _print_roles() -> None:
    base_url, _ = gateway()
    print(f"gateway: {base_url or '(missing OPENAI_BASE_URL)'}")
    print("\nproject roles:")
    print(f"{'role':<12}{'capability':<12}{'model':<32}{'env':<30}{'verified'}")
    for role, spec in MODEL_ROLES.items():
        print(f"{role:<12}{spec.capability:<12}{resolve_model(role):<32}{spec.env:<30}{spec.verified}")


def _print_grouped(groups: dict[str, list[str]]) -> None:
    for capability, items in groups.items():
        print(f"\n[{capability}] {len(items)}")
        for model_id in items:
            print(f"  {model_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="List gateway models by capability")
    parser.add_argument("--roles", action="store_true", help="print the project role table")
    parser.add_argument("--check", action="store_true", help="verify configured role ids exist")
    parser.add_argument("--capability", help="only show one capability, e.g. embedding")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        model_ids = available_models()
    except Exception as error:  # noqa: BLE001
        print(f"cannot read model list: {type(error).__name__}: {error}", file=sys.stderr)
        return 2

    if args.check:
        missing = missing_role_models(model_ids)
        if missing:
            print(f"missing configured models ({len(missing)}):")
            for role, model in missing:
                print(f"  {role}: {model}")
            return 1
        print(f"all {len(MODEL_ROLES)} roles resolve to models on the gateway")
        return 0

    if args.roles:
        _print_roles()
        return 0

    groups = models_by_capability(model_ids)
    if args.capability:
        groups = {name: items for name, items in groups.items() if name == args.capability}
        if not groups:
            print(f"no models classified as {args.capability}", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(groups, ensure_ascii=False, indent=2))
    else:
        print(f"gateway models: {len(model_ids)}")
        _print_grouped(groups)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
