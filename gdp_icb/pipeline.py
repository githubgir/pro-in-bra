"""End-to-end build: weights, diagnostics and output files.

Run: python -m gdp_icb.pipeline        (after python -m gdp_icb.download)
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from .mapping import bucket_table, build_buckets
from .weights import build_weights, global_bucket_weights, imputed_rent_shares, turnover


def _round(df: pd.DataFrame, cols: list[str], nd: int = 10) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = df[c].round(nd)
    return df


def ppp_vs_usd(cw: pd.DataFrame) -> pd.DataFrame:
    x = cw.copy()
    x["usd_weight"] = x["usd_gdp_bn"] / x.groupby("review")["usd_gdp_bn"].transform("sum")
    return x[["review", "country", "country_weight", "usd_weight"]].rename(columns={"country_weight": "ppp_weight"})


def run() -> dict[str, pd.DataFrame]:
    C.OUTPUT.mkdir(exist_ok=True)
    res = build_weights(adjust_rent=True)
    res_raw = build_weights(adjust_rent=False)
    w, cw, cal = res["weights"], res["country_weights"], res["calendar"]

    buckets = bucket_table()
    _, icb_b = build_buckets()
    gb = global_bucket_weights(w).merge(buckets[["bucket_id", "bucket_name", "reporting_icb_industry"]], on="bucket_id")
    gb_raw = global_bucket_weights(res_raw["weights"])
    to = turnover(w)
    p, med = imputed_rent_shares(range(1995, 2023))
    rent = p.stack().rename("imputed_rent_share").reset_index().rename(columns={"level_1": "iso3"})

    w = w.merge(buckets[["bucket_id", "bucket_name", "reporting_icb_industry"]], on="bucket_id")
    w = w.sort_values(["effective_date", "country", "bucket_id"])
    _round(w, ["within_country_share", "country_weight", "weight"]).to_csv(
        C.OUTPUT / "weights_country_bucket_long.csv", index=False)

    latest = cal.loc[~cal["provisional"], "review"].max()
    mat = w[(w["review"] == latest) & (w["event"] == "review")].pivot_table(
        index="country", columns="bucket_id", values="weight", aggfunc="sum").fillna(0)
    mat = mat.loc[mat.sum(axis=1).sort_values(ascending=False).index]
    mat.round(10).to_csv(C.OUTPUT / f"weights_matrix_{latest}.csv")

    _round(cw, ["country_weight"]).to_csv(C.OUTPUT / "country_weights.csv", index=False)
    _round(gb, ["weight"]).to_csv(C.OUTPUT / "global_bucket_weights.csv", index=False)
    cal.to_csv(C.OUTPUT / "review_calendar.csv", index=False)
    buckets.to_csv(C.OUTPUT / "bucket_definitions.csv", index=False)
    icb_b[["sub_code", "subsector", "sector", "supersector", "industry", "icio_codes", "bucket_id",
           "bucket_name", "in_scope", "rationale"]].to_csv(C.OUTPUT / "icb_subsector_to_bucket.csv", index=False)
    _round(to, ["total_turnover", "country_level_turnover", "global_bucket_turnover"]).to_csv(
        C.OUTPUT / "turnover.csv", index=False)
    return {
        "weights": w, "country_weights": cw, "calendar": cal, "buckets": buckets, "icb": icb_b,
        "global_buckets": gb, "global_buckets_no_rent_adj": gb_raw, "turnover": to,
        "rent_shares": rent, "rent_median": med, "ppp_usd": ppp_vs_usd(cw), "latest": latest,
    }


if __name__ == "__main__":
    out = run()
    print("latest review:", out["latest"], "| weight sets:", out["weights"]["effective_date"].nunique())
