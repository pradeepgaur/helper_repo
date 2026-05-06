# ─────────────────────────────────────────────
# 9.  CORRELATION CHARTS
# ─────────────────────────────────────────────
print("\n── Correlation charts ───────────────────")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from scipy import stats

    CHART_PATH = OUTPUT_PATH.replace(".xlsx", "_correlation_charts.png")

    BG="#0d1117"; SURF="161b22"; BORDER="#2a3444"
    GOLD="#e0a84b"; BLUE="#58a6ff"; GREEN="#3fb950"
    AMBER="#d29922"; MUTED="#7a8899"; WHITE="#f0f4f8"

    plt.rcParams.update({
        "figure.facecolor":BG, "axes.facecolor":SURF,
        "axes.edgecolor":BORDER, "axes.labelcolor":MUTED,
        "axes.titlecolor":WHITE, "text.color":WHITE,
        "xtick.color":MUTED, "ytick.color":MUTED,
        "grid.color":BORDER, "grid.linestyle":"--",
        "grid.alpha":0.4, "font.family":"monospace", "figure.dpi":150,
    })

    tier_map = {"insufficient_history":0,"low":1,"below_avg":2,"above_avg":3,"trusted":4}
    df["vendor_tier_num"] = df["vendor_tier"].map(tier_map)

    rvsn_cap = int(df["rvsn_nbr"].quantile(0.99))
    plot_df  = df[df["rvsn_nbr"] <= rvsn_cap].copy()

    charts = [
        {"y_col":"vendor_tier_num","y_label":"Vendor tier","title":"Vendor tier vs revision number",
         "color":GOLD,"jitter":0.08,"cap_y":None,"yticks":[0,1,2,3,4],
         "ylabels":["insuff.","low","below\navg","above\navg","trusted"]},
        {"y_col":"line_item_count","y_label":"Line item count","title":"Line items vs revision number",
         "color":BLUE,"jitter":0.15,"cap_y":99,"yticks":None,"ylabels":None},
        {"y_col":"est_tot_amt","y_label":"Estimate total ($)","title":"Estimate amount vs revision number",
         "color":GREEN,"jitter":0.15,"cap_y":99,"yticks":None,"ylabels":None},
        {"y_col":"lbr_hr_qty","y_label":"Labour hours","title":"Labour hours vs revision number",
         "color":AMBER,"jitter":0.15,"cap_y":99,"yticks":None,"ylabels":None},
    ]

    fig, axes = plt.subplots(2, 2, figsize=(9, 8), constrained_layout=True)
    fig.patch.set_facecolor(BG)
    fig.suptitle("Correlation: revision number vs approval drivers",
                 color=WHITE, fontsize=13, fontweight="bold", y=1.02)

    rng = np.random.default_rng(42)
    corr_rows = []

    for ax, cfg in zip(axes.flatten(), charts):
        col = cfg["y_col"]; color = cfg["color"]
        sub = plot_df[["rvsn_nbr", col]].dropna().copy()
        if cfg["cap_y"] is not None:
            sub = sub[sub[col] <= sub[col].quantile(cfg["cap_y"]/100)]
        x = sub["rvsn_nbr"].values.astype(float)
        y = sub[col].values.astype(float)
        r, p_val             = stats.pearsonr(x, y)
        slope, intercept, *_ = stats.linregress(x, y)
        corr_rows.append({"variable":col,"correlation_with_rvsn_nbr":round(r,4),
                           "slope":round(slope,4),"p_value":round(p_val,6),"n":len(sub)})
        x_line = np.linspace(x.min(), x.max(), 300)
        y_line = slope * x_line + intercept
        x_jit  = x + rng.uniform(-cfg["jitter"], cfg["jitter"], size=len(x))
        ax.scatter(x_jit, y, color=color, alpha=0.15, s=5, linewidths=0, rasterized=True)
        means = sub.groupby("rvsn_nbr")[col].mean()
        ax.plot(means.index, means.values, color=color, alpha=0.6,
                linewidth=1.4, linestyle="--", label="Mean per revision")
        ax.plot(x_line, y_line, color=WHITE, linewidth=2.2, linestyle="-",
                label=f"Trend  slope={slope:+.2f}")
        sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else "*")
        ax.text(0.97, 0.95, f"r = {r:+.3f}{sig}\nslope = {slope:+.3f}",
                transform=ax.transAxes, ha="right", va="top", fontsize=9, color=color,
                bbox=dict(boxstyle="round,pad=0.35", facecolor=SURF,
                          edgecolor=color, alpha=0.88))
        ax.set_title(cfg["title"], color=WHITE, fontsize=10, pad=7)
        ax.set_xlabel("Revision number (rvsn_nbr)", color=MUTED, fontsize=9)
        ax.set_ylabel(cfg["y_label"], color=MUTED, fontsize=9)
        ax.set_xlim(x.min()-0.4, x.max()+0.4)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        ax.grid(True)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(BORDER); ax.spines["bottom"].set_color(BORDER)
        if cfg["yticks"] is not None:
            ax.set_yticks(cfg["yticks"])
            ax.set_yticklabels(cfg["ylabels"], fontsize=8, color=MUTED)
        ax.legend(fontsize=8, frameon=True, framealpha=0.6, labelcolor=WHITE,
                  facecolor=SURF, edgecolor=BORDER, loc="lower right")

    fig.text(0.5, -0.01,
             "*** p<0.001  |  dashed = mean per revision  |  solid white = OLS trendline",
             ha="center", fontsize=8, color=MUTED)
    plt.savefig(CHART_PATH, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    corr_chart_df = pd.DataFrame(corr_rows)
    print(f"   Saved: {CHART_PATH}")

except ImportError as e:
    print(f"   Skipping charts — install matplotlib and scipy: {e}")
    corr_chart_df = pd.DataFrame()
