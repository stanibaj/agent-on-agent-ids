"""aoa-ids command line: install the judge into an observability stack or export it for import."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .adapters import exports, opik
from .config import Settings
from .spec import Spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aoa-ids", description="Agent-on-agent intrusion detection judge.")
    parser.add_argument("--env-file", default=".env", help="dotenv file to load (default: .env)")
    parser.add_argument("--version", action="version", version=f"aoa-ids {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("install", "create or update the judge (and alerts)"),
                            ("uninstall", "remove the judge and its alerts"),
                            ("status", "show rule, logs, alerts and recent scores")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("target", choices=["opik"])
        if name == "install":
            p.add_argument("--dry-run", action="store_true", help="print the payloads instead of calling the API")

    p = sub.add_parser("export", help="write import-ready files to dist/")
    p.add_argument("targets", nargs="*", choices=list(exports.TARGETS), help="default: all")

    p = sub.add_parser("render", help="print the rendered prompt")
    p.add_argument("--mode", choices=["agent", "mapped"], default="agent")
    p.add_argument("--output", choices=["scores", "json"], default="scores")

    args = parser.parse_args(argv)
    settings = Settings.load(args.env_file)
    spec = Spec()

    try:
        if args.command == "install":
            if args.dry_run:
                project_id = "<project-id>"
                print(json.dumps({"rule": opik.rule_payload(spec, settings, project_id),
                                  "alerts": opik.alert_payloads(spec, settings, project_id)}, indent=2))
            else:
                print("\n".join(opik.install(spec, settings)))
        elif args.command == "uninstall":
            print("\n".join(opik.uninstall(spec, settings)))
        elif args.command == "status":
            print(json.dumps(opik.status(spec, settings), indent=2, default=str))
        elif args.command == "export":
            for path in exports.export(spec, settings, args.targets or list(exports.TARGETS)):
                print(path)
        elif args.command == "render":
            for message in spec.messages(mode=args.mode, output=args.output, profile_file=settings.agent_profile_file):
                print(f"===== {message.role.upper()} =====\n{message.content}\n")
    except opik.OpikError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
