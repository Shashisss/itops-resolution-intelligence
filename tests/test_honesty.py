"""The two honesty bugs from the deck audit, pinned in the product.

1. The competing DB signal is a low-confidence, last-ranked signal. The display must say so
   (ranked 4th of 4 · low · 30%), not "ranked 2nd".
2. Staleness has ONE definition — now − dop_freshness.last_updated — computed once and rendered in
   the thread, the hypotheses, the metric card and the verification row.
"""
import os
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import engine as E  # noqa: E402
import journey  # noqa: E402
import viz  # noqa: E402


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (E, journey):
        monkeypatch.setattr(mod, "DB", str(dst))
    services, edges, incidents, changes, metrics, G = E.load()
    inc = next(i for i in incidents if i["id"] == "INC-8841")
    return inc, E.causes(inc, G, changes, metrics, services), metrics


def test_db_signal_is_ranked_last_with_low_confidence(ctx):
    inc, causes, _ = ctx
    hyps = journey.rank(causes)
    db = next(h for h in hyps if h["label"] == "DB connection saturation")
    assert len(hyps) == 4
    assert hyps.index(db) == 3, "the DB signal is 4th of 4, not 2nd"
    assert db["confidence"] == "low"
    assert viz.CONF_PCT[db["confidence"]] == 30
    assert hyps[0]["type"] == "upstream data", "the true cause stays above the symptoms"
    assert all(h["confidence"] in viz.CONF_PCT for h in hyps)


def test_rank_label_is_printed_from_the_same_order():
    # The ordinal helper the card uses must render "4th of 4" for the last of four.
    assert viz._ordinal(1) == "1st" and viz._ordinal(2) == "2nd"
    assert viz._ordinal(4) == "4th" and viz._ordinal(11) == "11th"


def test_staleness_is_one_computed_number(ctx):
    inc, causes, metrics = ctx
    f = journey.freshness("ds_pay_gd")
    assert f is not None and f["lag_min"] >= 45

    upstream = next(h for h in causes if h["type"] == "upstream data")
    assert f'{f["lag_min"]} min ago' in upstream["evidence"]
    assert f'{f["lag_min"]} min' in upstream["text"]

    metric = next(m for m in metrics if m["metric"] == "data_age_min")
    assert metric["value"] == float(f["lag_min"]), "the metric card must show the computed age"

    edge = next(e for e in journey.thread_edges_for(inc["id"]) if "freshness" in e["source"])
    assert f'freshness {f["lag_min"]}m' in edge["source"]
    data_edge = next(e for e in journey.thread_edges_for(inc["id"]) if "data_age" in e["source"])
    assert f'data_age {f["lag_min"]}>' in data_edge["source"]
