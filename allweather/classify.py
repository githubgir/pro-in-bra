"""Industry -> growth/inflation quadrant classification.

Quadrants (Bridgewater 'four environments', expressed relative to the equity market):
    GU_IU : growth rising,  inflation rising   ('inflationary boom / reflation')
    GU_ID : growth rising,  inflation falling  ('goldilocks')
    GD_IU : growth falling, inflation rising   ('stagflation')
    GD_ID : growth falling, inflation falling  ('deflationary bust / disinflation')

Each industry carries a growth score g and an inflation score i. Its quadrant is
(sign g, sign i). If a quadrant would be empty, the industry with the highest
quadrant score s_g*g + s_i*i is borrowed into it (it then sits in two quadrants).
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

QUADS = ["GU_IU", "GU_ID", "GD_IU", "GD_ID"]
QUAD_SIGNS = {"GU_IU": (1, 1), "GU_ID": (1, -1), "GD_IU": (-1, 1), "GD_ID": (-1, -1)}
QUAD_LABEL = {"GU_IU": "Growth ↑ / Inflation ↑", "GU_ID": "Growth ↑ / Inflation ↓",
              "GD_IU": "Growth ↓ / Inflation ↑", "GD_ID": "Growth ↓ / Inflation ↓"}

# ---------------------------------------------------------------------------
# (a) Macro-economic (judgemental) scores: g, i in {-2,-1,+1,+2}; |2| = strong conviction.
# Rationale strings are reproduced in the report.
# ---------------------------------------------------------------------------
_A49 = {
    "Agric": (-1, 2, "Farm output = food commodities; inelastic demand, prices spike in supply shocks"),
    "Food":  (-1, 1, "Staple demand, owns commodity inventory and passes food inflation through"),
    "Soda":  (-1, -1, "Branded long-duration staple; bond-proxy, margin squeezed by input costs"),
    "Beer":  (-1, -1, "Defensive branded staple; long-duration cash flows"),
    "Smoke": (-2, 1, "Most inelastic demand in the market; proven pricing power through excise hikes"),
    "Toys":  (2, -1, "Discretionary spend, imported inputs"),
    "Fun":   (2, -1, "Leisure / entertainment is first to be cut in a slowdown"),
    "Books": (1, -1, "Publishing & advertising cyclical; paper cost squeeze"),
    "Hshld": (-2, -1, "Consumer staples (soap, cosmetics); bond-like"),
    "Clths": (1, -1, "Discretionary apparel; cotton/labour input costs"),
    "Hlth":  (-2, -1, "Healthcare services: non-cyclical, reimbursement lags inflation"),
    "MedEq": (-1, -2, "Defensive growth, long duration"),
    "Drugs": (-2, -1, "Defensive, long-duration patents; regulated pricing"),
    "Chems": (1, 1, "Commodity chemicals: volume cyclical, prices track oil/feedstock"),
    "Rubbr": (1, -1, "Cyclical volumes, oil-based inputs squeeze margins"),
    "Txtls": (1, -1, "Cyclical, commodity fibre inputs squeeze margins"),
    "BldMt": (2, 1, "Construction materials: capex/housing cycle, real-asset pricing"),
    "Cnstr": (2, 1, "Construction volume pro-cyclical; contracts re-price with inflation"),
    "Steel": (2, 2, "Highest-beta industrial commodity producer"),
    "FabPr": (1, 1, "Metal fabrication; industrial cycle"),
    "Mach":  (2, 1, "Capex cycle, late-cycle when capacity is tight"),
    "ElcEq": (1, -1, "Capital goods with tech content; long-duration"),
    "Autos": (2, -1, "Durable credit-financed purchase, hurt by rising rates"),
    "Aero":  (1, -1, "Aircraft demand follows travel/capex; fuel cost sensitive"),
    "Ships": (1, 1, "Ship/rail equipment; trade & commodity-transport cycle"),
    "Guns":  (-1, 1, "Defence: counter-cyclical government spend, war-time inflation"),
    "Gold":  (-2, 2, "Gold = real store of value; rallies on stagflation and falling real rates"),
    "Mines": (1, 2, "Industrial metals: global growth and commodity inflation"),
    "Coal":  (1, 2, "Energy commodity tied to industrial power demand"),
    "Oil":   (-1, 2, "Energy price shocks are the archetypal stagflation (1973, 1979, 2022)"),
    "Util":  (-2, -2, "Regulated bond-proxy; tariffs lag inflation, rates hurt valuation"),
    "Telcm": (-1, -2, "Utility-like, leveraged, long duration"),
    "PerSv": (-1, -1, "Personal services (education, funeral): defensive"),
    "BusSv": (1, -1, "Business services/IT services: corporate spend, long duration"),
    "Comps": (2, -2, "Technology: long-duration growth, hurt by rising discount rates"),
    "Hardw": (2, -2, "Technology hardware: long-duration growth"),
    "Softw": (2, -2, "Software: longest-duration growth"),
    "Chips": (2, -2, "Semis: highest-beta tech cycle, long duration"),
    "LabEq": (1, -1, "Instruments: capex & R&D spend"),
    "Paper": (1, 1, "Pulp & paper commodity cycle"),
    "Boxes": (1, 1, "Packaging volumes track industrial production; pass-through pricing"),
    "Trans": (1, 1, "Freight volumes cyclical; railroads own real assets"),
    "Whlsl": (1, 1, "Inventory gains when prices rise; volume cyclical"),
    "Rtail": (1, -1, "Consumer discretionary; real-income squeeze under inflation"),
    "Meals": (1, -1, "Restaurants: discretionary, food & wage cost squeeze"),
    "Banks": (1, 1, "Steeper curve & higher rates lift NIM; credit losses fall with growth"),
    "Insur": (-1, -1, "Bond portfolios + claims inflation; defensive"),
    "RlEst": (1, 1, "Real assets re-price with inflation; development is cyclical"),
    "Fin":   (1, -1, "Brokers/asset managers: asset-price levels, falling rates"),
    "Other": (-1, -1, "Residual conglomerates; no clear exposure (assigned defensive)"),
}

_A_OTHER = {
    5: {"Cnsmr": (1, -1, "Consumer durables, retail, services: discretionary"),
        "Manuf": (1, 2, "Manufacturing + energy + utilities: commodity/real-asset heavy"),
        "HiTec": (2, -2, "Business equipment, telecom, TV: long-duration growth"),
        "Hlth":  (-2, -2, "Healthcare, drugs: defensive, long duration"),
        "Other": (1, 1, "Mines, construction, transport, finance: cyclical/real assets")},
    10: {"NoDur": (-2, -1, "Consumer staples"),
         "Durbl": (2, -1, "Consumer durables, credit-financed"),
         "Manuf": (2, 1, "Manufacturing: capex & industrial cycle"),
         "Enrgy": (-1, 2, "Oil, gas, coal: supply-shock stagflation hedge"),
         "HiTec": (2, -2, "Tech: long-duration growth"),
         "Telcm": (-1, -2, "Utility-like bond proxy"),
         "Shops": (1, -1, "Retail & services: discretionary"),
         "Hlth":  (-2, -1, "Healthcare: defensive"),
         "Utils": (-2, -2, "Regulated bond proxy"),
         "Other": (1, 1, "Mines, construction, transport, finance")},
    12: {"NoDur": (-2, -1, "Consumer staples"),
         "Durbl": (2, -1, "Consumer durables, credit-financed"),
         "Manuf": (2, 1, "Manufacturing: capex & industrial cycle"),
         "Enrgy": (-1, 2, "Oil, gas, coal: supply-shock stagflation hedge"),
         "Chems": (1, 2, "Chemicals: feedstock-linked commodity pricing"),
         "BusEq": (2, -2, "Tech: long-duration growth"),
         "Telcm": (-1, -2, "Utility-like bond proxy"),
         "Utils": (-2, -2, "Regulated bond proxy"),
         "Shops": (1, -1, "Retail & services: discretionary"),
         "Hlth":  (-2, -1, "Healthcare: defensive"),
         "Money": (1, 1, "Banks/finance: steeper curve, credit cycle"),
         "Other": (1, 1, "Mines, construction, transport, hotels")},
    17: {"Food":  (-1, 1, "Food: staple demand, commodity pass-through"),
         "Mines": (1, 2, "Mining: industrial & precious metals"),
         "Oil":   (-1, 2, "Oil & petroleum: supply-shock stagflation hedge"),
         "Clths": (1, -1, "Apparel: discretionary"),
         "Durbl": (2, -1, "Consumer durables"),
         "Chems": (1, 1, "Chemicals"),
         "Cnsum": (-2, -1, "Drugs, soap, tobacco: defensive staples"),
         "Cnstr": (2, 1, "Construction & materials"),
         "Steel": (2, 1, "Steel works"),
         "FabPr": (1, 1, "Fabricated products"),
         "Machn": (2, -1, "Machinery & business equipment (incl. computers)"),
         "Cars":  (2, -1, "Autos: credit-financed durable"),
         "Trans": (1, 1, "Transport: freight cycle, real assets"),
         "Utils": (-2, -2, "Regulated bond proxy"),
         "Rtail": (1, -1, "Retail: discretionary"),
         "Finan": (1, 1, "Banks, insurance, real estate"),
         "Other": (1, -1, "Residual incl. services and tech")},
    30: {"Food": (-1, 1, "Food"), "Beer": (-1, -1, "Beer & liquor"), "Smoke": (-2, 1, "Tobacco: pricing power"),
         "Games": (2, -1, "Recreation"), "Books": (1, -1, "Publishing"), "Hshld": (-2, -1, "Household staples"),
         "Clths": (1, -1, "Apparel"), "Hlth": (-2, -1, "Healthcare, med-eq, drugs"), "Chems": (1, 1, "Chemicals"),
         "Txtls": (1, -1, "Textiles"), "Cnstr": (2, 1, "Construction & materials"), "Steel": (2, 1, "Steel"),
         "FabPr": (2, 1, "Fabricated products & machinery"), "ElcEq": (1, -1, "Electrical equipment"),
         "Autos": (2, -1, "Autos"), "Carry": (1, -1, "Aircraft, ships, rail equipment"),
         "Mines": (1, 2, "Metal mining"), "Coal": (1, 2, "Coal"), "Oil": (-1, 2, "Petroleum & gas"),
         "Util": (-2, -2, "Utilities"), "Telcm": (-1, -2, "Telecom"), "Servs": (1, -1, "Personal & business services"),
         "BusEq": (2, -2, "Business equipment / tech"), "Paper": (1, 1, "Paper & packaging"),
         "Trans": (1, 1, "Transport"), "Whlsl": (1, 1, "Wholesale"), "Rtail": (1, -1, "Retail"),
         "Meals": (1, -1, "Restaurants & hotels"), "Fin": (1, 1, "Banks, insurance, finance"),
         "Other": (-1, -1, "Residual")},
    38: {"Agric": (-1, 2, "Agriculture"), "Mines": (1, 2, "Metal & coal mining"), "Oil": (-1, 2, "Oil & gas extraction"),
         "Stone": (1, 1, "Stone, clay, quarrying"), "Cnstr": (2, 1, "Construction"), "Food": (-1, 1, "Food"),
         "Smoke": (-2, 1, "Tobacco"), "Txtls": (1, -1, "Textiles"), "Apprl": (1, -1, "Apparel"),
         "Wood": (2, 1, "Lumber (housing cycle, commodity)"), "Chair": (2, -1, "Furniture"),
         "Paper": (1, 1, "Paper"), "Print": (1, -1, "Printing & publishing"),
         "Chems": (-1, -1, "Chemicals incl. pharma & soap (pharma-dominated by cap)"),
         "Ptrlm": (-1, 2, "Petroleum refining"), "Rubbr": (1, -1, "Rubber & plastics"),
         "Lethr": (1, -1, "Leather"), "Glass": (1, 1, "Glass, cement"), "Metal": (2, 1, "Primary metals"),
         "MtlPr": (2, 1, "Fabricated metal"), "Machn": (2, -1, "Machinery incl. computers"),
         "Elctr": (2, -2, "Electronic equipment incl. semis"), "Cars": (2, -1, "Transport equipment"),
         "Instr": (1, -1, "Instruments"), "Manuf": (1, -1, "Misc. manufacturing"), "Trans": (1, 1, "Transport"),
         "Phone": (-1, -2, "Telephone"), "TV": (1, -1, "Broadcasting"), "Utils": (-2, -2, "Electric utilities"),
         "Garbg": (-1, -1, "Sanitary services"), "Steam": (-2, -1, "Steam supply"), "Water": (-2, -2, "Water supply"),
         "Whlsl": (1, 1, "Wholesale"), "Rtail": (1, -1, "Retail"), "Money": (1, 1, "Finance, insurance, real estate"),
         "Srvc": (1, -1, "Services"), "Govt": (-1, 1, "Public administration"), "Other": (-1, -1, "Residual")},
}


def macro_scores(n):
    """(a) judgemental scores for French n-industry set -> DataFrame[g, i, why]."""
    if n in (48, 49):
        cols = [c for c in _A49 if not (n == 48 and c in ("Hardw", "Softw")) and not (n == 49 and c == "Comps")]
        d = {c: _A49[c] for c in cols}
    else:
        d = _A_OTHER[n]
    return pd.DataFrame(d, index=["g", "i", "why"]).T.astype({"g": float, "i": float})


def regression_scores(ind_q, mkt_q, macro, start=None, end=None):
    """(b) Regress quarterly industry-minus-market returns on standardised dG, dI.

    Returns DataFrame with betas (in % excess return per 1-sd move), HAC t-stats,
    and g/i scores = t-stats (used for sign and for empty-quadrant fallback).
    """
    X = macro[["dG", "dI"]]
    X = X.loc[start:end] if (start or end) else X
    z = (X - X.mean()) / X.std()
    z = z.clip(-3, 3)                       # tame the 2020 GDP swing
    out = {}
    for c in ind_q.columns:
        y = (ind_q[c] - mkt_q).reindex(z.index) * 100
        ok = y.notna()
        if ok.sum() < 40:
            continue
        res = sm.OLS(y[ok], sm.add_constant(z[ok])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        out[c] = {"b_g": res.params["dG"], "b_i": res.params["dI"],
                  "t_g": res.tvalues["dG"], "t_i": res.tvalues["dI"],
                  "r2": res.rsquared, "nobs": int(ok.sum())}
    df = pd.DataFrame(out).T
    df["g"], df["i"] = df["t_g"], df["t_i"]
    return df


def assign(scores, available=None):
    """scores: DataFrame with g, i. Returns dict quad -> list of industries."""
    s = scores if available is None else scores.loc[[c for c in scores.index if c in available]]
    q = {k: [] for k in QUADS}
    for c, r in s.iterrows():
        q[_quad_of(r["g"], r["i"])].append(c)
    for k, (sg, si) in QUAD_SIGNS.items():
        if not q[k] and len(s):
            q[k] = [(sg * s["g"] + si * s["i"]).idxmax()]   # borrow best fit
    return q


def _quad_of(g, i):
    return ("GU" if g > 0 else "GD") + "_" + ("IU" if i > 0 else "ID")


def quad_table(scores):
    return pd.Series({c: _quad_of(r["g"], r["i"]) for c, r in scores.iterrows()})


def rolling_regression_quads(ind_q, mkt_q, macro, ind_m_index, first_year=1965, lag_q=1):
    """(b-OOS) Re-estimate the regressions every January on an expanding window.

    Membership used during calendar year Y is estimated with macro/returns data through
    Q3 of Y-1 (one quarter of publication lag). Years before `first_year` reuse the first fit
    (only used to warm up risk models, never reported).
    Returns callable(period)->quad dict, and dict year->scores.
    """
    fits = {}
    last_year = ind_m_index[-1].year
    for y in range(first_year, last_year + 1):
        end = pd.Period(f"{y - 1}Q4") - lag_q
        sc = regression_scores(ind_q.loc[:end], mkt_q.loc[:end], macro.loc[:end])
        fits[y] = sc
    cache = {y: assign(s) for y, s in fits.items()}

    def quads_at(t):
        y = max(first_year, min(t.year, last_year))
        return cache[y]
    return quads_at, fits
