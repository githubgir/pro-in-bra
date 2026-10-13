import pandas as pd
import pytest

from gdp_icb import config as C
from gdp_icb.mapping import build_buckets, bucket_table
from gdp_icb.weights import build_weights, review_calendar, third_friday


def test_every_icb_subsector_maps_to_one_bucket():
    _, icb_b = build_buckets()
    assert len(icb_b) == 173
    assert icb_b["sub_code"].is_unique
    assert icb_b["bucket_id"].notna().all()


def test_no_icio_industry_is_split():
    icio_b, icb_b = build_buckets()
    assert icio_b["icio_code"].is_unique and len(icio_b) == 50
    # every ICIO code an ICB subsector spans sits in that subsector's bucket
    owner = icio_b.set_index("icio_code")["bucket_id"]
    for r in icb_b.itertuples():
        assert {owner[c] for c in r.icio_codes.split(";")} == {r.bucket_id}


def test_bucket_scope_is_homogeneous():
    b = bucket_table()
    assert b.loc[b["in_scope"] == 0, "bucket_id"].str.startswith("X_").all()


def test_calendar_third_fridays():
    assert third_friday(2024, 9).isoformat() == "2024-09-20"
    assert third_friday(2026, 3).isoformat() == "2026-03-20"
    cal = review_calendar()
    assert (pd.to_datetime(cal["effective_date"]).dt.weekday == 0).all()


@pytest.fixture(scope="module")
def res():
    if not (C.PROCESSED / "icio_va.csv").exists():
        pytest.skip("run python -m gdp_icb.download first")
    return build_weights()


def test_weights_sum_to_one(res):
    s = res["weights"].groupby("effective_date")["weight"].sum()
    assert ((s - 1).abs() < 1e-9).all()
    assert (res["weights"]["weight"] >= 0).all()


def test_country_weight_consistency(res):
    w = res["weights"][res["weights"]["event"] == "review"]
    a = w.groupby(["review", "country"])["weight"].sum()
    b = res["country_weights"].set_index(["review", "country"])["country_weight"]
    assert ((a - b.loc[a.index]).abs() < 1e-12).all()


def test_no_lookahead_in_data_years(res):
    cal = res["calendar"]
    assert (cal["imf_year"] < cal["review_year"]).all()
    assert (cal["icio_year"] <= cal["review_year"] - 3).all()


def test_universe_events(res):
    cw = res["country_weights"]
    has = lambda c, r: ((cw["country"] == c) & (cw["review"] == r)).any()
    assert has("Russia", "2021-09") and not has("Russia", "2022-03")
    assert not has("Saudi Arabia", "2019-09") and has("Saudi Arabia", "2020-03")
    assert has("Pakistan", "2024-03") and not has("Pakistan", "2024-09")
    w = res["weights"]
    ev = w[w["event"].str.startswith("intra_review")]
    assert set(ev["event"]) == {"intra_review_deletion:Morocco", "intra_review_deletion:Russia"}
    for r in ev.itertuples():
        assert not r.event.endswith(r.country)
