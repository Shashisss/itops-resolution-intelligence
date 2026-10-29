#!/usr/bin/env python3
"""One clock per render.

Every relative time on the incident screen — the waiting clock, the SLA left, the freshness lag, the
handoff hops — is "now minus a stored timestamp". Computed independently, two of those calls can
straddle a minute boundary inside one render and print 60m beside 61m for the same fact. That is a
contradiction a client can see.

So the app fixes one `now` at the top of each script run. Everything that needs the current time for
display asks here. Outside a run (tests, scripts) it falls back to the real clock, so a pure function
still behaves like one.
"""
import datetime as dt

_now = None


def begin():
    """Fix the clock for this script run. Called once at the top of app.py."""
    global _now
    _now = dt.datetime.now().replace(microsecond=0)


def now():
    """The current time for this render — identical in every call within one run."""
    return _now or dt.datetime.now()


def reset():
    global _now
    _now = None
