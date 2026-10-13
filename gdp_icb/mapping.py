"""ICIO industry <-> ICB subsector mapping and derivation of the non-splitting buckets.

Each ICB subsector is assigned to the ICIO industry (or industries) that carries its
primary economic activity. Buckets are the connected components of the bipartite graph
ICIO industry <-> ICB subsector. By construction:
  * every ICIO industry lies in exactly one bucket (no I/O industry is split), and
  * every ICB subsector lies in exactly one bucket (no stock needs to be split),
which makes the buckets the finest partition satisfying both constraints.
"""
from __future__ import annotations

import pandas as pd

from . import config as C


def load_icb() -> pd.DataFrame:
    icb = pd.read_csv(C.REFERENCE / "icb_structure.csv")
    for col in ("industry", "supersector", "sector", "subsector"):
        icb[col] = icb[col].str.strip()
    m = pd.read_csv(C.REFERENCE / "icb_to_icio.csv")
    out = icb.merge(m, on="sub_code", how="left", validate="1:1")
    missing = out[out["icio_codes"].isna()]
    if len(missing):
        raise ValueError(f"ICB subsectors without ICIO mapping: {missing['sub_code'].tolist()}")
    return out


def build_buckets() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (icio_to_bucket, icb_to_bucket)."""
    icio = pd.read_csv(C.REFERENCE / "icio_industries.csv")
    icb = load_icb()

    # union-find over ICIO codes; each subsector links the ICIO codes it spans
    parent = {c: c for c in icio["icio_code"]}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for codes in icb["icio_codes"]:
        cs = codes.split(";")
        unknown = set(cs) - set(parent)
        if unknown:
            raise ValueError(f"unknown ICIO codes in mapping: {unknown}")
        for c in cs[1:]:
            parent[find(c)] = find(cs[0])

    order = {c: i for i, c in enumerate(icio["icio_code"])}
    comp: dict[str, list[str]] = {}
    for c in icio["icio_code"]:
        comp.setdefault(find(c), []).append(c)
    key_of = {c: ";".join(sorted(members, key=order.get)) for members in comp.values() for c in members}

    names = pd.read_csv(C.REFERENCE / "bucket_names.csv")
    icio_b = icio.assign(icio_codes=icio["icio_code"].map(key_of)).merge(names, on="icio_codes", how="left")
    if icio_b["bucket_id"].isna().any():
        raise ValueError(f"unnamed buckets: {icio_b.loc[icio_b.bucket_id.isna(), 'icio_codes'].unique()}")

    icb_b = icb.assign(first=icb["icio_codes"].str.split(";").str[0])
    icb_b = icb_b.merge(icio_b[["icio_code", "bucket_id", "bucket_name"]], left_on="first", right_on="icio_code")
    icb_b = icb_b.drop(columns=["first", "icio_code"])

    # bucket scope = in_scope of its ICIO members (a bucket never mixes in/out-of-scope industries)
    scope = icio_b.groupby("bucket_id")["in_scope"].agg(["min", "max"])
    if (scope["min"] != scope["max"]).any():
        raise ValueError("bucket mixes in-scope and out-of-scope ICIO industries")
    icb_b["in_scope"] = icb_b["bucket_id"].map(scope["min"])
    return icio_b, icb_b


def bucket_table() -> pd.DataFrame:
    """One row per bucket with its ICIO members, ICB subsectors and ICB industries spanned."""
    icio_b, icb_b = build_buckets()
    rows = []
    for bid, g in icio_b.groupby("bucket_id", sort=False):
        s = icb_b[icb_b["bucket_id"] == bid]
        ind_counts = s["industry"].value_counts()
        rows.append({
            "bucket_id": bid,
            "bucket_name": g["bucket_name"].iloc[0],
            "in_scope": int(g["in_scope"].iloc[0]),
            "icio_codes": ";".join(g["icio_code"]),
            "n_icb_subsectors": len(s),
            "icb_industries": ";".join(ind_counts.index),
            # judgement-based primary ICB industry, used only to colour/group charts (never to split weight)
            "reporting_icb_industry": g["reporting_icb_industry"].iloc[0],
            "is_mixed_icb_industry": int(len(ind_counts) > 1),
            "icb_subsectors": "; ".join(f"{r.sub_code} {r.subsector.strip()}" for r in s.itertuples()),
        })
    return pd.DataFrame(rows)
