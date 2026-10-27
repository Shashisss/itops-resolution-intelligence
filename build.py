#!/usr/bin/env python3
"""Build identity — so "is the deployed build the commit I pushed?" is answerable from the UI.

The footer shows build number, commit and commit time. On a host without a .git directory (some
deployments strip it) the values fall back to the RI_COMMIT / RI_BUILD_TIME environment variables,
then to "unknown" — never to a hardcoded string that can silently lie.
"""
import datetime as dt
import functools
import os
import subprocess


def _git(*args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=2,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def info():
    sha = os.environ.get("RI_COMMIT") or _git("rev-parse", "--short", "HEAD") or "unknown"
    commit_time = os.environ.get("RI_BUILD_TIME") or _git("show", "-s", "--format=%cI", "HEAD") or ""
    count = _git("rev-list", "--count", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    build = f'v{count}' if count else "dev"
    try:
        when = dt.datetime.fromisoformat(commit_time).astimezone().strftime("%d %b %H:%M") if commit_time else ""
    except Exception:
        when = commit_time
    return {"sha": sha, "build": build, "time": when, "dirty": dirty}


def label(short=False):
    i = info()
    bits = [f'build {i["build"]}', i["sha"] + ("-dirty" if i["dirty"] else "")]
    if i["time"] and not short:
        bits.append(i["time"])
    return " · ".join(bits)


def matches(deployed_label, expected_sha):
    """True when a deployed build label contains the expected commit (smoke-test helper)."""
    return str(expected_sha)[:7] in str(deployed_label)
