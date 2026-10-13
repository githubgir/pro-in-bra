"""Paths and constants for the GDP x ICB weighting pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REFERENCE = DATA / "reference"
OUTPUT = ROOT / "output"

UA = {"User-Agent": "Mozilla/5.0 (gdp-icb research pipeline)"}

# OECD TiVA 2025 edition: principal indicators (levels). VALU = value added, USD mn, current prices.
OECD_TIVA_URL = (
    "https://sdmx.oecd.org/sti-public/rest/data/"
    "OECD.STI.PIE,DSD_TIVA_MAINLV@DF_MAINLV,1.1/{measure}......"
    "?dimensionAtObservation=AllDimensions"
)
# OECD National Accounts Table 6A: gross value added by activity, current prices, national currency.
OECD_T6_URL = (
    "https://sdmx.oecd.org/public/rest/data/"
    "OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE6,2.0/A..S1.S1.B1G._Z.L+L68A+_T._Z.XDC.V.N."
    "?dimensionAtObservation=AllDimensions&startPeriod=1995"
)
# IMF WEO via the IMF SDMX 2.1 API. 'WEO' is the latest vintage; named vintages are frozen snapshots.
IMF_WEO_URL = (
    "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,{flow},{version}/.PPPGDP+NGDPD.A"
    "?dimensionAtObservation=AllDimensions"
)
IMF_VINTAGES = {
    # flow id: (version, publication month)
    "WEO": ("9.0.0", "2026-10"),
    "WEO_2026_APR_VINTAGE": ("1.0.0", "2026-04"),
    "WEO_2025_OCT_VINTAGE": ("1.0.0", "2025-10"),
}
ICB_XLSX_URL = (
    "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/"
    "icb-structure-and-definitions.xlsx"
)

# Calendar
FIRST_REVIEW = (2000, 3)
LAST_REVIEW = (2027, 3)  # Mar-2027 is provisional: all inputs (Oct-2026 WEO, ICIO 2025) are already published
AS_OF = "2026-10-13"

# ICIO years before the first ICIO release: simulate a 4-year lag relative to the review year
PRE_ICIO_LAG_YEARS = 4

# Imputed-rent share validity band (L68A / L). Values outside are treated as missing:
# shares of ~1.0 indicate that a country reports L68A = L (no split), not a true share.
IMPUTED_RENT_VALID = (0.15, 0.97)
