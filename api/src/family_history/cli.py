"""Command line: `python -m family_history.cli <command>`.

- `migrate`: Alembic upgrade to head using `DIRECT_DATABASE_URL`.
- `openapi`: write `packages/contracts/openapi.json` (sorted keys, stable output).
- `check-openapi`: exit 1 when the committed document differs from the code.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

CONTRACT_RELATIVE = Path("packages") / "contracts" / "openapi.json"


def render_openapi(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def default_contract_path() -> Path:
    """`packages/contracts/openapi.json` in the repository holding the working directory or,
    failing that, this source tree."""
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for directory in (start, *start.parents):
            if (directory / "packages" / "contracts").is_dir():
                return directory / CONTRACT_RELATIVE
    raise FileNotFoundError("could not find packages/contracts; pass --output")


def current_openapi() -> str:
    from family_history.app import openapi_document

    return render_openapi(openapi_document())


def cmd_migrate(_: argparse.Namespace) -> int:
    from family_history.db.migrate import upgrade_to_head

    url = os.environ.get("DIRECT_DATABASE_URL")
    if not url:
        print("DIRECT_DATABASE_URL is not set", file=sys.stderr)
        return 2
    upgrade_to_head(url)
    print("migrations: at head")
    return 0


def cmd_openapi(args: argparse.Namespace) -> int:
    path = Path(args.output) if args.output else default_contract_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current_openapi(), encoding="utf-8")
    print(f"wrote {path}")
    return 0


def cmd_check_openapi(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else default_contract_path()
    expected = current_openapi()
    try:
        committed = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"{path} is missing; run `python -m family_history.cli openapi`", file=sys.stderr)
        return 1
    if committed != expected:
        print(
            f"{path} is out of date; run `python -m family_history.cli openapi`",
            file=sys.stderr,
        )
        return 1
    print("openapi: no drift")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="family-history-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="upgrade the database to the latest migration")
    openapi = commands.add_parser("openapi", help="write the OpenAPI contract")
    openapi.add_argument("--output", help="destination (default: packages/contracts)")
    check = commands.add_parser("check-openapi", help="fail when the contract has drifted")
    check.add_argument("--path", help="committed document (default: packages/contracts)")
    return parser


HANDLERS = {
    "migrate": cmd_migrate,
    "openapi": cmd_openapi,
    "check-openapi": cmd_check_openapi,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
