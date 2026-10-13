"""Run the full industry All-Weather study and cache results to results/results.pkl."""
import os
import pickle
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from allweather import analytics as A
from allweather import classify as C
from allweather import data as D
from allweather import portfolio as P

WITHIN = ["EW", "IV", "ERC"]
ACROSS = ["EW", "ERC"]
START = "1952-01"
OOS_START = "1965-01"


def run_level(n):
    f = D.factors()
    rets = D.industries(n)
    macro = D.macro_quarterly()
    ind_q = D.to_quarterly(rets)
    mkt_q = D.to_quarterly(f[["Mkt"]])["Mkt"]

    scores = {"a": C.macro_scores(n), "b": C.regression_scores(ind_q, mkt_q, macro)}
    quads = {k: C.assign(v) for k, v in scores.items()}
    oos_at, oos_fits = C.rolling_regression_quads(ind_q, mkt_q, macro, rets.index, first_year=1965)
    members = {"a": P.static(quads["a"]), "b": P.static(quads["b"]), "b_oos": oos_at}

    runs = {}
    for cls, qa in members.items():
        for wi in WITHIN:
            qret, ind_w = P.quad_returns(rets, qa, wi)
            for ac in ACROSS:
                res = P.combine(qret, ind_w, ac, START)
                res["turnover"] = P.turnover(res["w"], rets)
                runs[(cls, wi, ac)] = res
    # equal-weight-all-industries benchmark (same eligibility rule)
    ew_all = P.build(rets, P.static({"GU_IU": list(rets.columns), "GU_ID": [], "GD_IU": [], "GD_ID": []}), "EW", "EW", START)
    return n, {"scores": scores, "quads": quads, "oos_fits": oos_fits, "runs": runs, "ew_all": ew_all["aw"],
               "rets": rets}


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    f = D.factors()
    macro = D.macro_quarterly()
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
        out = dict(ex.map(run_level, D.LEVELS))
    with open("results/results.pkl", "wb") as fh:
        pickle.dump({"levels": out, "factors": f, "macro": macro}, fh)
    for n in D.LEVELS:
        r = out[n]["runs"][("a", "EW", "EW")]["aw"]
        print(n, A.stats(r, f.RF, f.Mkt)[["CAGR", "Vol", "Sharpe", "MaxDD"]].round(3).to_dict())
