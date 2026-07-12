#!/usr/bin/env python3
"""Cross-platform CLI for deterministic analysis-result bundle handoff."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis_exchange.python.bridge import (  # noqa: E402
    BridgeError,
    OBJECT_DESTINATIONS,
    create_draft_bundle,
    publish_bundle,
    validate_bundle,
    verify_bundle,
)
from analysis_exchange.python.reader import iter_published_bundles  # noqa: E402


def _default_exchange_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_report(report) -> None:
    for line in report.format_lines():
        print(line)
    print(f"SUMMARY errors={len(report.errors)} warnings={len(report.warnings)}")


def _cmd_new(args: argparse.Namespace) -> int:
    path = create_draft_bundle(
        args.exchange_root,
        analysis_id=args.analysis_id,
        analysis_version=args.analysis_version,
        object_type=args.object_type,
        title=args.title,
        bundle_id=args.bundle_id,
        run_id=args.run_id,
    )
    print(path)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    report = validate_bundle(args.bundle)
    _print_report(report)
    return 0 if report.valid else 1


def _cmd_publish(args: argparse.Namespace) -> int:
    path = publish_bundle(args.bundle, args.exchange_root)
    print(path)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    manifest = verify_bundle(args.bundle)
    print(f"VERIFIED {manifest['bundle_id']}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    count = 0
    for bundle in iter_published_bundles(args.exchange_root, verify=True):
        result = bundle.manifest["result"]
        handoff = bundle.manifest["handoff"]
        print(
            f"{bundle.bundle_id}\t{result['object_type']}\t"
            f"{handoff['recommended_destination']}\t{result['title']}"
        )
        count += 1
    if count == 0:
        print("No complete published bundles")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchange-root",
        type=Path,
        default=_default_exchange_root(),
        help="analysis_exchange directory (default: repository-local directory)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    new = subparsers.add_parser("new", help="create a conservative draft bundle")
    new.add_argument("--analysis-id", required=True)
    new.add_argument("--analysis-version", required=True)
    new.add_argument("--object-type", choices=sorted(OBJECT_DESTINATIONS), required=True)
    new.add_argument("--title", required=True)
    new.add_argument("--bundle-id")
    new.add_argument("--run-id")
    new.set_defaults(handler=_cmd_new)

    validate = subparsers.add_parser("validate", help="validate a draft or published bundle")
    validate.add_argument("bundle", type=Path)
    validate.set_defaults(handler=_cmd_validate)

    publish = subparsers.add_parser("publish", help="validate, hash, seal, and publish a staging bundle")
    publish.add_argument("bundle", type=Path)
    publish.set_defaults(handler=_cmd_publish)

    verify = subparsers.add_parser("verify", help="verify a sealed published bundle")
    verify.add_argument("bundle", type=Path)
    verify.set_defaults(handler=_cmd_verify)

    listing = subparsers.add_parser("list", help="list complete verified published bundles")
    listing.set_defaults(handler=_cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

