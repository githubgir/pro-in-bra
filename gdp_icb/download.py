"""Download raw inputs and compact them into tidy processed CSVs.

Run: python -m gdp_icb.download
Raw files land in data/raw (git-ignored); compact tidy files in data/processed (committed).
"""
from __future__ import annotations

import io
import time

import pandas as pd
import requests

from . import config as C

ICIO_ECONOMY_EXCLUDE = {
    # OECD aggregates present in the TiVA REF_AREA list
    "A5_A7", "APEC", "ASEAN", "E", "EA19", "EU15", "EU27_2020", "EU28", "EU28XEU15", "F",
    "G20", "NAFTA", "OECD", "S2", "S2_S8", "W", "WXD", "WXOECD",
}


def _get(url: str, accept: str | None = None, retries: int = 4) -> bytes:
    headers = dict(C.UA)
    if accept:
        headers["Accept"] = accept
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=300)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 ** (i + 1))
    raise RuntimeError("unreachable")


def download_icio_va() -> pd.DataFrame:
    """Value added by country x ICIO industry, USD mn, 1995-2022 (TiVA 2025 = ICIO 2025 edition)."""
    raw = _get(C.OECD_TIVA_URL.format(measure="VALU"), "application/vnd.sdmx.data+csv; charset=utf-8")
    (C.RAW / "oecd_tiva2025_valu.csv").write_bytes(raw)
    d = pd.read_csv(io.BytesIO(raw))
    icio = pd.read_csv(C.REFERENCE / "icio_industries.csv")
    d = d[d["ACTIVITY"].isin(icio["icio_code"]) & ~d["REF_AREA"].isin(ICIO_ECONOMY_EXCLUDE)]
    out = (
        d.rename(columns={"REF_AREA": "iso3", "ACTIVITY": "icio_code", "TIME_PERIOD": "year", "OBS_VALUE": "va_usd_mn"})
        [["iso3", "icio_code", "year", "va_usd_mn"]]
        .sort_values(["iso3", "year", "icio_code"])
    )
    out.to_csv(C.PROCESSED / "icio_va.csv", index=False)
    return out


def download_imf_weo() -> pd.DataFrame:
    frames = []
    for flow, (version, pub) in C.IMF_VINTAGES.items():
        raw = _get(C.IMF_WEO_URL.format(flow=flow, version=version), "application/vnd.sdmx.data+csv;version=1.0.0")
        (C.RAW / f"imf_{flow.lower()}_gdp.csv").write_bytes(raw)
        d = pd.read_csv(io.BytesIO(raw), low_memory=False)
        d = d.rename(columns={"COUNTRY": "iso3", "INDICATOR": "indicator", "TIME_PERIOD": "year"})
        d["value"] = pd.to_numeric(d["OBS_VALUE"], errors="coerce") * 10.0 ** (pd.to_numeric(d["SCALE"]) - 9)
        d["latest_actual"] = d["LATEST_ACTUAL_ANNUAL_DATA"].astype(str).str.extract(r"(\d{4})")[0].astype(float)
        # FY2024/25-style labels: the fiscal year mostly overlaps the first calendar year in WEO conventions
        d["vintage"] = flow
        d["vintage_pub"] = pub
        frames.append(d[["vintage", "vintage_pub", "iso3", "indicator", "year", "value", "latest_actual"]])
    out = pd.concat(frames).dropna(subset=["value"]).sort_values(["vintage", "iso3", "indicator", "year"])
    out["value_unit"] = "USD bn (NGDPD) / intl. USD bn PPP (PPPGDP)"
    out.to_csv(C.PROCESSED / "imf_weo_gdp.csv", index=False)
    return out


def download_imputed_rent() -> pd.DataFrame:
    raw = _get(C.OECD_T6_URL, "application/vnd.sdmx.data+csv; charset=utf-8")
    (C.RAW / "oecd_table6a_l68.csv").write_bytes(raw)
    d = pd.read_csv(io.BytesIO(raw))
    p = d.pivot_table(index=["REF_AREA", "TIME_PERIOD"], columns="ACTIVITY", values="OBS_VALUE").reset_index()
    p = p.rename(columns={"REF_AREA": "iso3", "TIME_PERIOD": "year", "L": "va_L", "L68A": "va_L68A", "_T": "va_total"})
    p["imputed_rent_share_of_L"] = p["va_L68A"] / p["va_L"]
    p.to_csv(C.PROCESSED / "oecd_imputed_rent.csv", index=False)
    return p


def download_icb() -> None:
    raw = _get(C.ICB_XLSX_URL)
    (C.RAW / "icb-structure-and-definitions.xlsx").write_bytes(raw)


def main() -> None:
    for p in (C.RAW, C.PROCESSED):
        p.mkdir(parents=True, exist_ok=True)
    print("ICIO value added ...", len(download_icio_va()))
    print("IMF WEO GDP ...", len(download_imf_weo()))
    print("OECD imputed rent ...", len(download_imputed_rent()))
    download_icb()
    print("done")


if __name__ == "__main__":
    main()
