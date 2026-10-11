"""End-to-end check of an Opik install: log fixture runs as real traces and wait for the judge's scores.

    python scripts/e2e_opik.py --project aoa-ids-e2e --cases benign-service-restart,atk-log-injection-authorized-keys

Run `aoa-ids install opik` against the same project first (the rule only scores traces logged after it
exists). Use a scratch project so test attacks don't land in your production data. Needs `pip install opik`.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import opik
import yaml

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sysadmin_traces.yaml"
DEFAULT_CASES = "benign-service-restart,benign-log-audit-mentions-attacks,atk-log-injection-authorized-keys,atk-pr-comment-ci-curl-pipe"


def log_case(client: opik.Opik, project: str, case: dict) -> str:
    # Pass end times up front: ending a trace right after creating it can race the SDK's batching.
    start = datetime.now(timezone.utc)
    trace = client.trace(name=case["id"], project_name=project, input={"role": "user", "content": case["input"]},
                         output={"content": case["output"]}, tags=["aoa-ids-e2e"], metadata={"label": case["label"]},
                         start_time=start, end_time=start + timedelta(seconds=len(case["trajectory"]) + 1))
    for i, step in enumerate(case["trajectory"]):
        trace.span(name=f"Tool: {step['tool']}", type="tool", input=step["input"], output=step["output"],
                   start_time=start + timedelta(seconds=i), end_time=start + timedelta(seconds=i + 1))
    return trace.id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="aoa-ids-e2e")
    parser.add_argument("--cases", default=DEFAULT_CASES)
    parser.add_argument("--bootstrap", action="store_true", help="only log one trace so the project exists")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    client = opik.Opik(project_name=args.project)
    if args.bootstrap:
        now = datetime.now(timezone.utc)
        client.trace(name="aoa-ids-bootstrap", project_name=args.project, input={"content": "bootstrap"}, output={},
                     start_time=now, end_time=now)
        client.flush()
        print(f"project {args.project} ready; now run: OPIK_PROJECT_NAME={args.project} aoa-ids install opik")
        return 0

    cases = {c["id"]: c for c in yaml.safe_load(FIXTURES.read_text())}
    logged = {log_case(client, args.project, cases[cid]): cases[cid] for cid in args.cases.split(",")}
    client.flush()
    print(f"logged {len(logged)} traces to {args.project}; waiting for aoa_ids_* scores...")

    deadline, results = time.time() + args.timeout, {}
    while time.time() < deadline and len(results) < len(logged):
        time.sleep(15)
        for trace_id in set(logged) - set(results):
            scores = {s.name: s for s in (client.get_trace_content(trace_id).feedback_scores or [])
                      if s.name.startswith("aoa_ids_")}
            if "aoa_ids_incident" in scores:
                results[trace_id] = scores

    ok = True
    for trace_id, case in logged.items():
        scores = results.get(trace_id)
        if not scores:
            print(f"  {case['id']:40} NOT SCORED (check `aoa-ids status opik` for rule logs)")
            ok = False
            continue
        got = scores["aoa_ids_incident"].value >= 0.5
        match = got == (case["label"] == "incident")
        ok &= match
        sev, alert = scores.get("aoa_ids_severity"), scores.get("aoa_ids_alert")
        print(f"  {case['id']:40} expected={case['label']:8} incident={got!s:5} severity={sev.value if sev else '?'} "
              f"alert={alert.value if alert else '?'} "
              f"{'✓' if match else '✗'}\n      {scores['aoa_ids_incident'].reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
