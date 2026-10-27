#!/usr/bin/env python3
"""Deployment smoke test — the check to run before saying "it's deployed".

    python3 scripts/smoke.py            # local checkout
    python3 scripts/smoke.py --expect <sha>   # also assert the build label carries that commit

It does four things a demo cannot survive without:
  1. every module imports cleanly (catches stale signatures and missing helpers);
  2. the app boots headless through Streamlit's own test harness (no exception, list rendered);
  3. navigation works end to end (open an incident, go back, URL cleared);
  4. the build label shown to the user matches the checked-out commit.
"""
import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# `seed` is deliberately excluded: importing it reseeds the demo database (it is a script).
MODULES = ["build", "clock", "collab", "command_center", "dataops_engine", "dataops_views", "engine",
           "journey", "personas", "realtime", "shell", "viz", "workspace"]


def fail(msg):
    print(f"FAIL  {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", help="commit sha the deployed build must contain")
    args = ap.parse_args()

    for m in MODULES:
        try:
            __import__(m)
        except Exception as exc:  # noqa: BLE001
            fail(f"import {m}: {exc}")
    print(f"ok    {len(MODULES)} modules import")

    import build
    label = build.label()
    print(f"ok    build label: {label}")
    if args.expect:
        if not build.matches(label, args.expect):
            fail(f"build label {label!r} does not contain expected commit {args.expect[:7]}")
        print("ok    build matches expected commit")

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    if at.exception:
        fail(f"app raised: {at.exception}")
    print("ok    app boots headless")

    rows = [b for b in at.button if "INC-8841" in (b.label or "")]
    if not rows:
        fail("incident list did not render (no INC-8841 row)")
    rows[0].click().run()
    if at.exception:
        fail(f"workspace raised: {at.exception}")
    if at.session_state.get("open_incident", {}).get("ref") != "INC-8841":
        fail("clicking a row did not open INC-8841")
    if at.query_params.get("inc") != "INC-8841":
        fail("workspace did not put the incident in the URL")
    print("ok    incident opens with a shareable URL")

    back = next((b for b in at.button if "All incidents" in (b.label or "")), None)
    if back is None:
        fail("no back-to-list control on the workspace")
    back.click().run()
    if at.session_state.get("open_incident"):
        fail("back-to-list left the workspace open")
    if at.query_params.get("inc") not in (None, [], ""):
        fail("back-to-list left a stale ?inc= parameter")
    print("ok    back to list clears state and URL")

    print("\nSMOKE PASSED")


if __name__ == "__main__":
    main()
