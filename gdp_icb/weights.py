"""Country x ICB-bucket weight histories.

Weight of bucket b in country c at review r:

    w[c,b,r] = GDP%[c,r] * VA%[b | c, r]

    GDP%[c,r]    IMF WEO PPP GDP of the latest reported year at review r, as a share of the
                 universe total (FTSE All-World membership at r).
    VA%[b|c,r]   ICIO market-sector value added of bucket b in country c, as a share of the
                 country's in-scope total, for the latest ICIO year available at review r.

Because VA% is a within-country share, the ICIO data is effectively rescaled to the IMF
country total: the (more timely) IMF figure sets the level, ICIO only sets the mix.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import config as C
from .mapping import build_buckets


# ---------------------------------------------------------------- calendar
def third_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    first_fri = d + dt.timedelta(days=(4 - d.weekday()) % 7)
    return first_fri + dt.timedelta(days=14)


def data_cutoff(year: int, month: int) -> dt.date:
    """Wednesday before the first Friday of the review month (FTSE review data date)."""
    first_fri = third_friday(year, month) - dt.timedelta(days=14)
    return first_fri - dt.timedelta(days=2)


def review_calendar() -> pd.DataFrame:
    rows = []
    y, m = C.FIRST_REVIEW
    while (y, m) <= C.LAST_REVIEW:
        tf = third_friday(y, m)
        rows.append({
            "review": f"{y}-{m:02d}",
            "review_year": y,
            "review_month": m,
            "data_cutoff": data_cutoff(y, m),
            "effective_date": tf + dt.timedelta(days=3),
        })
        y, m = (y, 9) if m == 3 else (y + 1, 3)
    cal = pd.DataFrame(rows)
    cal["provisional"] = cal["data_cutoff"].astype(str) > C.AS_OF
    return cal


def imf_rule(cal: pd.DataFrame, weo_vintages: dict[str, str]) -> pd.DataFrame:
    """March review uses the prior October WEO (latest reported year = Y-2);
    September review uses the April WEO of the same year (latest reported year = Y-1).
    The frozen vintage is used where it exists, otherwise the latest (revised) WEO."""
    pub_to_flow = {pub: flow for flow, pub in weo_vintages.items()}
    out = cal.copy()
    out["imf_year"] = np.where(out["review_month"] == 3, out["review_year"] - 2, out["review_year"] - 1)
    out["imf_weo_release"] = np.where(
        out["review_month"] == 3,
        (out["review_year"] - 1).astype(str) + "-10",
        out["review_year"].astype(str) + "-04",
    )
    out["imf_vintage"] = out["imf_weo_release"].map(pub_to_flow).fillna("WEO")
    out["imf_point_in_time"] = out["imf_weo_release"].isin(pub_to_flow)
    # every review whose own WEO release is not archived falls back to the latest WEO (revised history)
    out["imf_vintage_used"] = np.where(out["imf_point_in_time"], "WEO " + out["imf_weo_release"],
                                       "WEO " + weo_vintages["WEO"] + " (latest, revised)")
    return out


def icio_rule(cal: pd.DataFrame) -> pd.DataFrame:
    ed = pd.read_csv(C.REFERENCE / "icio_editions.csv", parse_dates=["assumed_available_from"])
    out = cal.copy()
    years, eds = [], []
    for cut in pd.to_datetime(out["data_cutoff"]):
        avail = ed[ed["assumed_available_from"] < cut]
        if len(avail):
            years.append(int(avail["last_data_year"].max()))
            eds.append(avail.sort_values("assumed_available_from")["edition"].iloc[-1])
        else:
            years.append(cut.year - C.PRE_ICIO_LAG_YEARS)
            eds.append("simulated (pre-2013, 4-year lag)")
    out["icio_year"] = np.maximum(years, 1995)
    out["icio_edition_available"] = eds
    out["icio_lag_years"] = out["review_year"] - out["icio_year"]
    out["imf_lag_years"] = out["review_year"] - out["imf_year"]
    return out


# ---------------------------------------------------------------- universe
def load_universe() -> pd.DataFrame:
    u = pd.read_csv(C.REFERENCE / "ftse_allworld_universe.csv", dtype=str).fillna("")
    u["members"] = u["iso3_members"].str.split(";")
    return u


def universe_at(u: pd.DataFrame, review: str) -> pd.DataFrame:
    keep = (u["first_review"] <= review) & ((u["last_review"] == "") | (u["last_review"] >= review))
    return u[keep]


# ---------------------------------------------------------------- inputs
def imputed_rent_shares(years: range) -> pd.DataFrame:
    """L68A/L share per iso3 x year: interpolated within country, flat-extended,
    cross-country median (by year) where a country has no valid national-accounts split."""
    d = pd.read_csv(C.PROCESSED / "oecd_imputed_rent.csv")
    lo, hi = C.IMPUTED_RENT_VALID
    d = d[(d["imputed_rent_share_of_L"] >= lo) & (d["imputed_rent_share_of_L"] <= hi)]
    d = d[d["iso3"].str.len() == 3]
    p = d.pivot_table(index="year", columns="iso3", values="imputed_rent_share_of_L").reindex(list(years))
    p = p.interpolate(limit_area="inside").ffill().bfill()
    med = d.groupby("year")["imputed_rent_share_of_L"].median().reindex(list(years)).interpolate().ffill().bfill()
    return p, med


def load_icio_buckets() -> pd.DataFrame:
    va = pd.read_csv(C.PROCESSED / "icio_va.csv")
    icio_b, _ = build_buckets()
    va = va.merge(icio_b[["icio_code", "bucket_id", "in_scope"]], on="icio_code")
    return va


def load_imf() -> pd.DataFrame:
    imf = pd.read_csv(C.PROCESSED / "imf_weo_gdp.csv")
    # 'latest actual year' metadata is carried on the nominal-GDP series only; PPP GDP is derived from it
    la = imf[imf["indicator"] == "NGDPD"].groupby(["vintage", "iso3"])["latest_actual"].max()
    imf["latest_actual"] = pd.MultiIndex.from_frame(imf[["vintage", "iso3"]]).map(la)
    return imf


# ---------------------------------------------------------------- core
def within_country_shares(va: pd.DataFrame, rent: tuple, members: list[str], year: int,
                          adjust_rent: bool = True) -> pd.DataFrame:
    """In-scope VA by bucket for a (possibly multi-iso) FTSE country in a given ICIO year."""
    p, med = rent
    x = va[(va["iso3"].isin(members)) & (va["year"] == year) & (va["in_scope"] == 1)].copy()
    if adjust_rent:
        is_l = x["icio_code"] == "L"
        share = x.loc[is_l, "iso3"].map(lambda c: p.at[year, c] if c in p.columns else med[year])
        x.loc[is_l, "va_usd_mn"] = x.loc[is_l, "va_usd_mn"] * (1 - share.values)
    g = x.groupby("bucket_id")["va_usd_mn"].sum().clip(lower=0)
    return g


def build_weights(adjust_rent: bool = True) -> dict[str, pd.DataFrame]:
    cal = icio_rule(imf_rule(review_calendar(), {f: pub for f, (_, pub) in C.IMF_VINTAGES.items()}))
    u = load_universe()
    va = load_icio_buckets()
    imf = load_imf()
    rent = imputed_rent_shares(range(1995, 2031))
    ppp = imf[imf["indicator"] == "PPPGDP"]
    usd = imf[imf["indicator"] == "NGDPD"]

    long_rows, country_rows = [], []
    for r in cal.itertuples():
        uni = universe_at(u, r.review)
        vin = ppp[(ppp["vintage"] == r.imf_vintage) & (ppp["year"] == r.imf_year)].set_index("iso3")
        vin_usd = usd[(usd["vintage"] == r.imf_vintage) & (usd["year"] == r.imf_year)].set_index("iso3")["value"]
        gdp = {}
        for c in uni.itertuples():
            vals = [vin["value"].get(m, np.nan) for m in c.members]
            if any(pd.isna(vals)):
                raise ValueError(f"missing IMF PPP GDP for {c.country} {r.imf_year} in {r.imf_vintage}")
            la = min(vin["latest_actual"].get(m, np.nan) for m in c.members)
            gdp[c.country] = (sum(vals), sum(vin_usd.get(m, np.nan) for m in c.members), la)
        tot = sum(v[0] for v in gdp.values())
        for c in uni.itertuples():
            src = [c.icio_proxy] if c.icio_proxy else c.members
            sh = within_country_shares(va, rent, src, r.icio_year, adjust_rent)
            sh = sh / sh.sum()
            cw = gdp[c.country][0] / tot
            la = gdp[c.country][2]
            flags = [f for f in [c.flag, "imf_estimate" if pd.notna(la) and r.imf_year > la else ""] if f]
            country_rows.append({
                "review": r.review, "effective_date": r.effective_date, "country": c.country,
                "iso3_members": c.iso3_members, "ppp_gdp_bn": gdp[c.country][0], "usd_gdp_bn": gdp[c.country][1],
                "country_weight": cw, "imf_year": r.imf_year, "imf_vintage": r.imf_vintage,
                "imf_latest_actual": la, "icio_year": r.icio_year,
                "icio_source": c.icio_proxy or c.iso3_members, "flags": ";".join(flags),
            })
            for b, s in sh.items():
                long_rows.append({
                    "review": r.review, "effective_date": r.effective_date, "event": "review",
                    "country": c.country, "bucket_id": b, "within_country_share": s,
                    "country_weight": cw, "weight": cw * s,
                })

    w = pd.DataFrame(long_rows)
    cw = pd.DataFrame(country_rows)

    # intra-review deletions: weight redistributed pro rata across all remaining constituents
    events = []
    for c in u[u["exit_type"] == "intra_review"].itertuples():
        prev = cal[cal["review"] <= c.last_review]["review"].max()
        base = w[(w["review"] == prev) & (w["event"] == "review")]
        rem = base[base["country"] != c.country].copy()
        rem["weight"] = rem["weight"] / rem["weight"].sum()
        cws = rem.groupby("country")["weight"].transform("sum")
        rem["country_weight"] = cws
        rem["effective_date"] = dt.date.fromisoformat(c.exit_effective)
        rem["event"] = f"intra_review_deletion:{c.country}"
        events.append(rem)
    if events:
        w = pd.concat([w, *events], ignore_index=True)
    w = w.sort_values(["effective_date", "country", "bucket_id"]).reset_index(drop=True)

    cal_out = cal.merge(
        cw.groupby("review").agg(n_countries=("country", "nunique")).reset_index(), on="review")
    return {"weights": w, "country_weights": cw, "calendar": cal_out}


def global_bucket_weights(w: pd.DataFrame) -> pd.DataFrame:
    return w.groupby(["effective_date", "review", "event", "bucket_id"], as_index=False)["weight"].sum()


def turnover(w: pd.DataFrame) -> pd.DataFrame:
    """One-way turnover between consecutive weight sets (reviews and intra-review events)."""
    piv = w.pivot_table(index=["country", "bucket_id"], columns="effective_date", values="weight",
                        aggfunc="sum").fillna(0.0)
    cpiv = piv.groupby(level="country").sum()
    bpiv = piv.groupby(level="bucket_id").sum()
    dates = list(piv.columns)
    rows = []
    for a, b in zip(dates[:-1], dates[1:]):
        rows.append({
            "effective_date": b,
            "total_turnover": 0.5 * (piv[b] - piv[a]).abs().sum(),
            "country_level_turnover": 0.5 * (cpiv[b] - cpiv[a]).abs().sum(),
            "global_bucket_turnover": 0.5 * (bpiv[b] - bpiv[a]).abs().sum(),
        })
    return pd.DataFrame(rows)
