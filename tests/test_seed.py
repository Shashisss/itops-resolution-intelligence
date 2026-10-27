"""Baseline: the seeded database certifies the release it was built from.

A hardcoded seed version let a schema change ship while an old database kept serving. The seed now
writes VERSION, and app._needs_seed() compares against it so a bump forces a reseed."""
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402  (module import does not run the page)


def test_seed_version_is_the_current_version():
    con = sqlite3.connect(ROOT / "data" / "ops.db")
    value = con.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
    con.close()
    assert value is not None
    assert value[0] == (ROOT / "VERSION").read_text().strip()


def test_needs_seed_compares_against_version():
    assert app_module._needs_seed() is False, "the current database matches this release"
