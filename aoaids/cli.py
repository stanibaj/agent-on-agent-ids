"""aoa-ids command line: install the judge into an observability stack or export it for import."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from . import __version__, notify
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
            p.add_argument("--smoke-test", action="store_true",
                           help="after installing, log 5 test traces (3 attacks, 2 benign) and verify the verdicts")
            p.add_argument("--keep-smoke-traces", action="store_true", help="do not delete the smoke-test traces")

    p = sub.add_parser("smoke-test", help="run only the 5-trace smoke test against an installed judge")
    p.add_argument("target", choices=["opik"])
    p.add_argument("--keep-smoke-traces", action="store_true")

    p = sub.add_parser("coverage", help="share of recent traces the judge scored; exits 2 when below the minimum")
    p.add_argument("target", choices=["opik"])
    p.add_argument("--hours", type=float, help="look-back window (default AOA_COVERAGE_HOURS, 24)")
    p.add_argument("--min", type=float, dest="minimum", help="minimum coverage, 0-1 (default AOA_COVERAGE_MIN, 0.95)")
    p.add_argument("--notify", action="store_true",
                   help="send a notice to the alert destination when coverage is low (PagerDuty also gets resolves)")
    p.add_argument("--json", action="store_true", help="print the full report as JSON")

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
            elif not opik.install(spec, settings, smoke=args.smoke_test, keep_smoke=args.keep_smoke_traces):
                return 1
        elif args.command == "smoke-test":
            client = opik.OpikClient(settings)
            project_id = client.project_id(settings.opik_project)
            if not client.find_rule(project_id, settings.rule_name):
                print(f"error: rule {settings.rule_name} not found; run `aoa-ids install opik` first", file=sys.stderr)
                return 1
            if not opik.smoke_test(client, spec, settings, project_id, print, keep=args.keep_smoke_traces):
                return 1
        elif args.command == "coverage":
            return coverage(spec, settings, args)
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
    except (opik.OpikError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def coverage(spec: Spec, settings: Settings, args: argparse.Namespace) -> int:
    if args.minimum is not None:
        settings = replace(settings, coverage_min=args.minimum)
    client = opik.OpikClient(settings)
    project_id = client.project_id(settings.opik_project)
    report = opik.coverage(client, spec, settings, project_id, hours=args.hours)
    summary = opik.coverage_summary(report, settings)
    print(json.dumps(report, indent=2, default=str) if args.json else summary)
    if args.notify and report["healthy"] is not None:
        kind = opik.destination(settings)
        if kind is None:
            print("error: --notify needs an alert destination in .env", file=sys.stderr)
            return 1
        title = f"AOA-IDS coverage {'OK' if report['healthy'] else 'LOW'} on Opik project {settings.opik_project}"
        if notify.send(settings, kind, title=title, text=summary, link=opik.traces_url(settings, project_id),
                       dedup_key=f"aoa-ids-coverage-{project_id}", resolved=report["healthy"]):
            print(f"notice sent to {kind}")
    return 0 if report["healthy"] is not False else 2


if __name__ == "__main__":
    sys.exit(main())
