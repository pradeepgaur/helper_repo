"""
Correlation Charts — rvsn_nbr vs vendor_tier, line_item_count, est_tot_amt, lbr_hr_qty
========================================================================================
Fully standalone — just update DATA_PATH and run.
Saves: correlation_charts.png  (2x2 grid) in same folder as the script.

pip install pandas numpy matplotlib scipy
"""

import pandas as pd
import numpy as np
import warnings
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats

warnings.filterwarnings("ignore")

# ── CONFIG ────────────────────────────────────────────────────
DATA_PATH            = "your_estimates_file.csv"   # <- update
OUTPUT_PATH          = "correlation_charts.png"
VENDOR_MIN_ESTIMATES = 10

# ── Colours ───────────────────────────────────────────────────
BG     = "#0d1117"
SURF   = "#161b22"
BORDER = "#2a3444"
GOLD   = "#e0a84b"
BLUE   = "#58a6ff"
GREEN  = "#3fb950"
AMBER  = "#d29922"
MUTED  = "#7a8899"
WHITE  = "#f0f4f8"

plt.rcParams.update({
    "figure.facecolor": BG,     "axes.facecolor":  SURF,
    "axes.edgecolor":   BORDER, "axes.labelcolor": MUTED,
    "axes.titlecolor":  WHITE,  "text.color":      WHITE,
    "xtick.color":      MUTED,  "ytick.color":     MUTED,
    "grid.color":       BORDER, "grid.linestyle":  "--",
    "grid.alpha":       0.4,    "font.family":     "monospace",
    "figure.dpi":       150,
})

# ════════════════════════════════════════════════════════════════
# 1. LOAD
# ════════════════════════════════════════════════════════════════
print("── 1. Loading ───────────────────────────")
df = pd.read_csv(DATA_PATH, low_memory=False)
print(f"   {len(df):,} rows  x  {df.shape[1]} columns")

if "time_to_approve_days" in df.columns:
    df["time_to_approve_days"] = df["time_to_approve_days"].clip(lower=0)

# ════════════════════════════════════════════════════════════════
# 2. TARGET
# ════════════════════════════════════════════════════════════════
df["first_pass"] = (df["rvsn_nbr"] == 1).astype(int)
print(f"   first_pass rate : {df['first_pass'].mean():.1%}")
print(f"   rvsn_nbr range  : {int(df['rvsn_nbr'].min())} - {int(df['rvsn_nbr'].max())}")

# ════════════════════════════════════════════════════════════════
# 3. VENDOR TIER
# ════════════════════════════════════════════════════════════════
print("\n── 2. Vendor tiers ──────────────────────")

vendor_rates = (
    df.groupby("vr_vndr_id")["first_pass"]
    .agg(vendor_approval_rate="mean", vendor_est_count="count")
    .reset_index()
)

eligible = vendor_rates.loc[
    vendor_rates["vendor_est_count"] >= VENDOR_MIN_ESTIMATES,
    "vendor_approval_rate"
]
q25 = eligible.quantile(0.25)
q50 = eligible.quantile(0.50)
q75 = eligible.quantile(0.75)
print(f"   Q25={q25:.4f}  Q50={q50:.4f}  Q75={q75:.4f}")

def assign_tier(row):
    if row["vendor_est_count"] < VENDOR_MIN_ESTIMATES:
        return "insufficient_history"
    r = row["vendor_approval_rate"]
    if r >= q75: return "trusted"
    if r >= q50: return "above_avg"
    if r >= q25: return "below_avg"
    return "low"

vendor_rates["vendor_tier"] = vendor_rates.apply(assign_tier, axis=1)
df = df.merge(
    vendor_rates[["vr_vndr_id", "vendor_approval_rate", "vendor_tier"]],
    on="vr_vndr_id", how="left"
)

for tier, cnt in df["vendor_tier"].value_counts().items():
    print(f"   {tier:<25} {cnt:>6,}")

# Numeric encoding for correlation
tier_map = {
    "insufficient_history": 0,
    "low":                  1,
    "below_avg":            2,
    "above_avg":            3,
    "trusted":              4,
}
df["vendor_tier_num"] = df["vendor_tier"].map(tier_map)

# ════════════════════════════════════════════════════════════════
# 4. CAP rvsn_nbr AT 99TH PERCENTILE
# ════════════════════════════════════════════════════════════════
rvsn_cap = int(df["rvsn_nbr"].quantile(0.99))
plot_df  = df[df["rvsn_nbr"] <= rvsn_cap].copy()
print(f"\n── 3. Plot data — rvsn_nbr capped at {rvsn_cap} ──")
print(f"   {len(plot_df):,} estimates included")

# ════════════════════════════════════════════════════════════════
# 5. CHART CONFIG
# ════════════════════════════════════════════════════════════════
charts = [
    {
        "y_col"  : "vendor_tier_num",
        "y_label": "Vendor tier",
        "title"  : "Vendor tier vs revision number",
        "color"  : GOLD,
        "jitter" : 0.08,
        "cap_y"  : None,
        "yticks" : [0, 1, 2, 3, 4],
        "ylabels": ["insuff.", "low", "below\navg", "above\navg", "trusted"],
    },
    {
        "y_col"  : "line_item_count",
        "y_label": "Line item count",
        "title"  : "Line items vs revision number",
        "color"  : BLUE,
        "jitter" : 0.15,
        "cap_y"  : 99,
        "yticks" : None,
        "ylabels": None,
    },
    {
        "y_col"  : "est_tot_amt",
        "y_label": "Estimate total ($)",
        "title"  : "Estimate amount vs revision number",
        "color"  : GREEN,
        "jitter" : 0.15,
        "cap_y"  : 99,
        "yticks" : None,
        "ylabels": None,
    },
    {
        "y_col"  : "lbr_hr_qty",
        "y_label": "Labour hours",
        "title"  : "Labour hours vs revision number",
        "color"  : AMBER,
        "jitter" : 0.15,
        "cap_y"  : 99,
        "yticks" : None,
        "ylabels": None,
    },
]

# ════════════════════════════════════════════════════════════════
# 6. BUILD FIGURE
# ════════════════════════════════════════════════════════════════
print("\n── 4. Building charts ───────────────────")

fig, axes = plt.subplots(
    2, 2,
    figsize=(9, 8),
    constrained_layout=True
)
fig.patch.set_facecolor(BG)
fig.suptitle(
    "Correlation: revision number vs approval drivers",
    color=WHITE, fontsize=13, fontweight="bold", y=1.02
)

rng = np.random.default_rng(42)

print(f"\n   {'Variable':<22} {'r':>8}  {'Slope':>12}  Direction")
print(f"   {'─'*62}")

for ax, cfg in zip(axes.flatten(), charts):
    col   = cfg["y_col"]
    color = cfg["color"]

    # Subset
    sub = plot_df[["rvsn_nbr", col]].dropna().copy()
    if cfg["cap_y"] is not None:
        y_cap = sub[col].quantile(cfg["cap_y"] / 100)
        sub   = sub[sub[col] <= y_cap]

    x = sub["rvsn_nbr"].values.astype(float)
    y = sub[col].values.astype(float)

    # Stats
    r, p_val              = stats.pearsonr(x, y)
    slope, intercept, *_  = stats.linregress(x, y)
    x_line = np.linspace(x.min(), x.max(), 300)
    y_line = slope * x_line + intercept

    # Jittered scatter
    x_jit = x + rng.uniform(-cfg["jitter"], cfg["jitter"], size=len(x))
    ax.scatter(x_jit, y, color=color, alpha=0.15, s=5,
               linewidths=0, rasterized=True)

    # Mean per revision (dashed)
    means = sub.groupby("rvsn_nbr")[col].mean()
    ax.plot(means.index, means.values,
            color=color, alpha=0.6, linewidth=1.4,
            linestyle="--", label="Mean per revision")

    # OLS trendline (solid white)
    ax.plot(x_line, y_line,
            color=WHITE, linewidth=2.2, linestyle="-",
            label=f"Trend  slope={slope:+.2f}")

    # Annotation
    sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else "*")
    ax.text(
        0.97, 0.95,
        f"r = {r:+.3f}{sig}\nslope = {slope:+.3f}",
        transform=ax.transAxes,
        ha="right", va="top", fontsize=9, color=color,
        bbox=dict(boxstyle="round,pad=0.35",
                  facecolor=SURF, edgecolor=color, alpha=0.88)
    )

    # Formatting
    ax.set_title(cfg["title"], color=WHITE, fontsize=10, pad=7)
    ax.set_xlabel("Revision number", color=MUTED, fontsize=9)
    ax.set_ylabel(cfg["y_label"], color=MUTED, fontsize=9)
    ax.set_xlim(x.min() - 0.4, x.max() + 0.4)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BORDER)
    ax.spines["bottom"].set_color(BORDER)

    if cfg["yticks"] is not None:
        ax.set_yticks(cfg["yticks"])
        ax.set_yticklabels(cfg["ylabels"], fontsize=8, color=MUTED)

    ax.legend(fontsize=8, frameon=True, framealpha=0.6,
              labelcolor=WHITE, facecolor=SURF, edgecolor=BORDER,
              loc="lower right")

    # Console summary
    direction = "increases with revisions" if slope > 0 else "decreases with revisions"
    print(f"   {col:<22} {r:>+8.3f}  {slope:>+12.4f}  {direction}")

fig.text(
    0.5, -0.01,
    "*** p<0.001  |  dashed = mean per revision  |  "
    "solid white = OLS trendline",
    ha="center", fontsize=8, color=MUTED
)

# ════════════════════════════════════════════════════════════════
# 7. SAVE
# ════════════════════════════════════════════════════════════════
plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close()

abs_path = os.path.abspath(OUTPUT_PATH)
print(f"\n── 5. Saved ─────────────────────────────")
print(f"   {abs_path}")
print(f"   File size: {os.path.getsize(abs_path)/1024:.0f} KB")
