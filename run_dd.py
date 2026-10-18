"""(c) Drawdown-anchored classification: run all levels / schemes plus asset-class All Weather benchmarks."""
import os
import pickle
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from allweather import assets as S
from allweather import data as D
from allweather import ddcluster as DC
from allweather import portfolio as P

WITHIN = ["EW", "IV", "ERC"]
ACROSS = ["EW", "ERC"]
START = "1970-01"
END = "2026-08"


def load():
    f = D.factors()
    a = S.all_assets(f.RF).loc[:END]
    return f, a


def run_level(n):
    f, a = load()
    rets = D.industries(n)
    full = DC.fit(rets, a, f.Mkt, f.RF)
    oos_at, oos_fits = DC.rolling_quads(rets, a, f.Mkt, f.RF, first_year=2000, last_year=2026)
    members = {"c": P.static(full["quads"]), "c_oos": oos_at}
    runs = {}
    for cls, qa in members.items():
        for wi in WITHIN:
            qret, ind_w = P.quad_returns(rets, qa, wi)
            for ac in ACROSS:
                res = P.combine(qret, ind_w, ac, "1965-01")
                res["turnover"] = P.turnover(res["w"], rets)
                runs[(cls, wi, ac)] = res
    return n, {"fit": full, "oos_fits": oos_fits, "runs": runs}


def asset_aw():
    f, a = load()
    a = a.copy()
    quads = {"GD_IU": ["Gold", "TIPS"], "GU_IU": ["Commodities"], "GD_ID": ["Treasuries"], "GU_ID": ["Cyclicals"]}
    out = {}
    for ac in ACROSS:
        qret, ind_w = P.quad_returns(a, P.static(quads), "EW", warmup="1968-05")
        out[ac] = P.combine(qret, ind_w, ac, START)
    return out


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=4) as ex:
        out = dict(ex.map(run_level, D.LEVELS))
    f, a = load()
    pickle.dump({"levels": out, "assets": a, "asset_aw": asset_aw()}, open("results/results_dd.pkl", "wb"))
    print("done")
