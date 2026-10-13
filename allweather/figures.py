"""Matplotlib figures rendered in a light and a dark variant (PNG, base64) for the HTML report."""
import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                  s=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
                  ref="#52514e", neg="#e34948", pos="#2a78d6", mid="#f0efec"),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835",
                 s=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
                 ref="#c3c2b7", neg="#e66767", pos="#3987e5", mid="#383835"),
}
# quadrant -> categorical slot (fixed, never cycled)
QSLOT = {"GU_IU": 1, "GU_ID": 0, "GD_IU": 3, "GD_ID": 2}


def _style(T):
    plt.rcParams.update({
        "figure.facecolor": T["surface"], "axes.facecolor": T["surface"], "savefig.facecolor": T["surface"],
        "axes.edgecolor": T["axis"], "axes.labelcolor": T["ink2"], "text.color": T["ink"],
        "xtick.color": T["muted"], "ytick.color": T["muted"], "axes.grid": True, "grid.color": T["grid"],
        "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
        "font.family": "DejaVu Sans", "font.size": 9.5, "axes.titlesize": 11, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "legend.frameon": False, "lines.linewidth": 1.6,
        "legend.labelcolor": T["ink2"],
    })


def render(draw, size=(9, 4.2)):
    """draw(fig, T) -> None. Returns {'light': b64, 'dark': b64}."""
    out = {}
    for name, T in THEMES.items():
        _style(T)
        fig = plt.figure(figsize=size, dpi=130)
        rect = draw(fig, T)
        fig.tight_layout(rect=rect or (0, 0, 1, 1))
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        out[name] = base64.b64encode(buf.getvalue()).decode()
    return out


def ts(idx):
    return idx.to_timestamp() if isinstance(idx, pd.PeriodIndex) else idx


def date_axis(ax, every=10):
    ax.xaxis.set_major_locator(mdates.YearLocator(every))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def pct(ax, axis="y", dec=0):
    from matplotlib.ticker import PercentFormatter
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(PercentFormatter(1.0, decimals=dec))
