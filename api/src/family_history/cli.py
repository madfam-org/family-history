"""Command line: `python -m family_history.cli <command>`.

- `migrate`: Alembic upgrade to head using `DIRECT_DATABASE_URL`.
- `openapi`: write the generated contracts, `packages/contracts/openapi.json` and
  `packages/contracts/family-history-tree.v1.schema.json` (sorted keys, stable output).
- `check-openapi`: exit 1 when either committed contract differs from the code.
- `validate-export <file>`: check a native `family-history-tree/v1` export.
- `seed-synth --space <uuid> --seed <n> --generations <n>`: persist a synthetic family
  (`domain.synth.generate_family`) into a space, as its first steward. Refused in production.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

CONTRACT_RELATIVE = Path("packages") / "contracts" / "openapi.json"
TREE_SCHEMA_NAME = "family-history-tree.v1.schema.json"


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


def current_tree_schema() -> str:
    from family_history.interchange.native import render_schema

    return render_schema()


def _contracts(openapi_path: Path) -> list[tuple[Path, str]]:
    return [
        (openapi_path, current_openapi()),
        (openapi_path.parent / TREE_SCHEMA_NAME, current_tree_schema()),
    ]


def cmd_openapi(args: argparse.Namespace) -> int:
    path = Path(args.output) if args.output else default_contract_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    for target, content in _contracts(path):
        target.write_text(content, encoding="utf-8")
        print(f"wrote {target}")
    return 0


def cmd_check_openapi(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else default_contract_path()
    drifted = False
    for target, expected in _contracts(path):
        try:
            committed = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            committed = None
        if committed != expected:
            state = "missing" if committed is None else "out of date"
            print(
                f"{target} is {state}; run `python -m family_history.cli openapi`",
                file=sys.stderr,
            )
            drifted = True
    if drifted:
        return 1
    print("openapi: no drift (openapi.json, family-history-tree.v1.schema.json)")
    return 0


def cmd_validate_export(args: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from family_history.interchange.native import parse

    try:
        document = parse(Path(args.file).read_bytes())
    except OSError as exc:
        print(f"cannot read {args.file}: {exc.strerror}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        print(f"{args.file} is not a valid family-history-tree/v1 export:", file=sys.stderr)
        for error in exc.errors()[:20]:
            where = ".".join(str(part) for part in error["loc"]) or "(document)"
            print(f"  {where}: {error['msg']}", file=sys.stderr)
        return 1
    print(
        f"valid family-history-tree/v1: {len(document.people)} people, "
        f"{len(document.events)} events, {len(document.sources)} sources"
    )
    return 0


def cmd_seed_synth(args: argparse.Namespace) -> int:
    from family_history.seed import SeedError, seed_space

    try:
        counts = seed_space(args.space, seed=args.seed, generations=args.generations)
    except SeedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("seeded: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="family-history-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="upgrade the database to the latest migration")
    openapi = commands.add_parser("openapi", help="write the OpenAPI contract")
    openapi.add_argument("--output", help="destination (default: packages/contracts)")
    check = commands.add_parser("check-openapi", help="fail when the contract has drifted")
    check.add_argument("--path", help="committed document (default: packages/contracts)")
    validate = commands.add_parser("validate-export", help="check a native JSON export")
    validate.add_argument("file")
    seed = commands.add_parser("seed-synth", help="persist a synthetic family (not production)")
    seed.add_argument("--space", required=True, type=uuid.UUID, help="family space id")
    seed.add_argument("--seed", required=True, type=int)
    seed.add_argument("--generations", type=int, default=4, choices=range(3, 7), metavar="3-6")
    return parser


HANDLERS = {
    "migrate": cmd_migrate,
    "openapi": cmd_openapi,
    "check-openapi": cmd_check_openapi,
    "validate-export": cmd_validate_export,
    "seed-synth": cmd_seed_synth,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
