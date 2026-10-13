# GDP × ICB-industry weighted All-World

This project extends the FTSE All-World GDP Weighted methodology down to **country × ICB-industry** buckets.

- **Country weight:** IMF WEO PPP GDP for the latest *reported* year (not forecasts), taken from the WEO vintage that the FTSE GDP-Adjusted timing rule points to.
- **Within-country split:** OECD ICIO 2025 market-sector value added (A–N and R–S, with owner-occupier imputed rent removed from L). Each review uses the latest ICIO edition published before its data cut-off.
- **Buckets:** the finest partition in which no ICIO industry and no ICB subsector is split. There are 39 in-scope buckets, derived automatically from `data/reference/icb_to_icio.csv`.
- **History:** semi-annual reviews (3rd Friday of March and September) from Mar-2000 to Mar-2027 (Mar-2027 is provisional). The universe follows historical FTSE All-World membership, and intra-review deletions (Morocco 2015, Russia 2022) are applied as separate weight sets.

`w[c,b] = GDP%_IMF[c] × VA%_ICIO[b | c]`

The full rationale, dataset description, charts and caveats are in **`output/report/index.html`**.

## Reproduce

```bash
pip install -r requirements.txt
python -m gdp_icb.download   # OECD TiVA/ICIO 2025, IMF WEO (3 vintages), OECD Table 6A, ICB structure
python -m gdp_icb.report     # builds weights (gdp_icb.pipeline) + HTML report
pytest -q
```

## Layout

| Path | Content |
|---|---|
| `gdp_icb/download.py` | API downloads (OECD SDMX, IMF SDMX) → `data/raw` (ignored) and tidy `data/processed` |
| `gdp_icb/mapping.py` | ICB subsector → ICIO assignment; derives the buckets as connected components |
| `gdp_icb/weights.py` | Review calendar, publication-lag rules, universe, imputed-rent adjustment, weights, turnover |
| `gdp_icb/pipeline.py` | Writes all `output/*.csv` |
| `gdp_icb/report.py` | Writes `output/report/index.html` |
| `data/reference/` | Hand-curated inputs: ICIO industries & scope, ICB→ICIO mapping with rationale, bucket names, FTSE universe history, ICIO edition dates |
| `output/weights_country_bucket_long.csv` | Main deliverable: weight per weight set × country × bucket |
| `output/icb_subsector_to_bucket.csv` | Lookup for applying the weights to stocks |
