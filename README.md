# Industry All Weather

Bridgewater-style All Weather portfolios built from Kenneth French US industry portfolios
(5, 10, 12, 17, 30, 38, 48, 49 industries). Industries are classified into growth/inflation
up/down quadrants, relative to the equity market, in two ways:

- **(a)** macro-economic judgement scores (`allweather/classify.py`)
- **(b)** regressions of industry-minus-market returns on changes in YoY real GDP growth and CPI
  inflation, full sample and expanding-window out-of-sample

Quadrant portfolios (EW / inverse-vol / ERC within) are combined into All Weather (EW / ERC across).

```
pip install pandas numpy statsmodels scipy matplotlib adjustText
python run.py         # downloads data, runs the grid  -> results/results.pkl
python report.py      # figures + tables               -> results/report_parts.pkl
python build_html.py  # report                         -> results/industry_all_weather.html
```

Outputs: `results/industry_all_weather.html`, `results/classification_all_levels.csv`,
`results/all_weather_monthly_returns.csv`.
