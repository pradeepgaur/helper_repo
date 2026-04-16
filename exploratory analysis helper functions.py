"""
Vehicle Repair Estimate Auto-Approval Analysis
================================================
Purpose : Find variable thresholds and business rules for auto-approving
          repair estimates on the first pass.
Input   : Your estimates DataFrame (CSV or DB query result).
          Update LOAD DATA section to point at your file.
Output  : Console summaries + an Excel workbook with all analysis sheets.
"""

import pandas as pd
import numpy as np
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# 0. LOAD DATA  ← update this path
# ─────────────────────────────────────────────
DATA_PATH = "your_estimates_file.csv"   # <-- change to your file path
OUTPUT_PATH = "auto_approval_analysis.xlsx"

df = pd.read_csv(DATA_PATH, low_memory=False)
print(f"Loaded {len(df):,} rows, {df.shape[1]} columns")


# ─────────────────────────────────────────────
# 1. DATA CLEANING
# ─────────────────────────────────────────────
print("\n── 1. Cleaning ─────────────────────────")

# Drop columns with no signal (single unique value or near-total nulls)
DROP_COLS = [
    "is_glass_est_ind",   # all zeros
    "temp_est_ind",       # all zeros
    "is_bulk_ind",        # single value
    "is_electronic_est_ind",  # single value
    "cdr_vndr_flag",      # single value
    "expd_cmpl_dte",      # 99.99% null
    "slvg_amt",           # all null
    "email_txt",          # all null
]
df.drop(columns=[c for c in DROP_COLS if c in df.columns], inplace=True)

# Fix time_to_approve_days — negative values are data errors, cap at 0
if "time_to_approve_days" in df.columns:
    df["time_to_approve_days"] = df["time_to_approve_days"].clip(lower=0)

# Parse key dates
for col in ["est_recv_dte", "apprv_dte", "act_cmpl_dte"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")

print(f"  Cleaned shape: {df.shape}")


# ─────────────────────────────────────────────
# 2. TARGET VARIABLE
# ─────────────────────────────────────────────
print("\n── 2. Target variable ──────────────────")

# first_pass = 1 if the estimate was approved on revision 1
df["first_pass"] = (df["rvsn_nbr"] == 1).astype(int)

overall_rate = df["first_pass"].mean()
print(f"  Overall first-pass approval rate : {overall_rate:.1%}")
print(f"  First-pass approvals             : {df['first_pass'].sum():,}")
print(f"  Needed revisions                 : {(df['first_pass'] == 0).sum():,}")


# ─────────────────────────────────────────────
# 3. FEATURE ENGINEERING
# ─────────────────────────────────────────────
print("\n── 3. Feature engineering ──────────────")

# Cost per labour hour
df["cost_per_lbr_hr"] = np.where(
    df["lbr_hr_qty"] > 0,
    df["est_tot_amt"] / df["lbr_hr_qty"],
    np.nan
)

# Vehicle age
if "veh_yr" in df.columns:
    current_year = pd.Timestamp.now().year
    df["veh_age"] = current_year - df["veh_yr"]

# Estimate amount buckets
bucket_edges = [0, 250, 500, 750, 1000, 1500, 2500, np.inf]
bucket_labels = ["$0–250", "$251–500", "$501–750", "$751–1k",
                 "$1k–1.5k", "$1.5k–2.5k", "$2.5k+"]
df["est_amt_bucket"] = pd.cut(
    df["est_tot_amt"], bins=bucket_edges, labels=bucket_labels, right=True
)

# Labour hour buckets
lbr_edges = [0, 2, 4, 8, 16, np.inf]
lbr_labels = ["0–2 hrs", "2–4 hrs", "4–8 hrs", "8–16 hrs", "16+ hrs"]
df["lbr_hr_bucket"] = pd.cut(
    df["lbr_hr_qty"], bins=lbr_edges, labels=lbr_labels, right=True
)

# Vendor tier — based on historical first-pass rate
vendor_rates = df.groupby("vr_vndr_id")["first_pass"].agg(
    vendor_approval_rate="mean",
    vendor_est_count="count"
).reset_index()
# Only tier vendors with enough history (≥10 estimates)
vendor_rates["vendor_tier"] = np.where(
    vendor_rates["vendor_est_count"] < 10,
    "insufficient_history",
    pd.qcut(
        vendor_rates["vendor_approval_rate"],
        q=[0, 0.25, 0.5, 0.75, 1.0],
        labels=["low", "below_avg", "above_avg", "trusted"],
        duplicates="drop"
    ).astype(str)
)
df = df.merge(vendor_rates[["vr_vndr_id", "vendor_approval_rate", "vendor_tier"]],
              on="vr_vndr_id", how="left")

print("  Engineered: cost_per_lbr_hr, veh_age, est_amt_bucket,")
print("              lbr_hr_bucket, vendor_approval_rate, vendor_tier")


# ─────────────────────────────────────────────
# 4. ANALYSIS FUNCTIONS
# ─────────────────────────────────────────────

def approval_summary(series_or_df, group_col=None):
    """Return approval rate + count for a groupby or single series."""
    if group_col:
        g = series_or_df.groupby(group_col)["first_pass"].agg(
            approval_rate="mean",
            total_estimates="count",
            first_pass_count="sum"
        ).reset_index()
        g["revision_count"] = g["total_estimates"] - g["first_pass_count"]
        g["approval_rate_pct"] = (g["approval_rate"] * 100).round(1)
        g["coverage_pct"] = (g["total_estimates"] / len(df) * 100).round(1)
        return g.sort_values("approval_rate", ascending=False)
    return None


# ─────────────────────────────────────────────
# 5. UNIVARIATE THRESHOLD ANALYSIS
# ─────────────────────────────────────────────
print("\n── 5. Univariate threshold analysis ────")

# 5a. Estimate amount buckets
amt_analysis = approval_summary(df, "est_amt_bucket")
print("\n  Approval rate by estimate amount:")
print(amt_analysis[["est_amt_bucket", "approval_rate_pct",
                     "total_estimates", "coverage_pct"]].to_string(index=False))

# 5b. Labour hours buckets
lbr_analysis = approval_summary(df, "lbr_hr_bucket")
print("\n  Approval rate by labour hours:")
print(lbr_analysis[["lbr_hr_bucket", "approval_rate_pct",
                     "total_estimates", "coverage_pct"]].to_string(index=False))

# 5c. Vendor tier
vt_analysis = approval_summary(df, "vendor_tier")
print("\n  Approval rate by vendor tier:")
print(vt_analysis[["vendor_tier", "approval_rate_pct",
                    "total_estimates", "coverage_pct"]].to_string(index=False))

# 5d. Top 30 vendors by volume — approval rates
top_vendors = (
    df.groupby("vr_vndr_id")["first_pass"]
    .agg(approval_rate="mean", count="count")
    .query("count >= 20")
    .assign(approval_rate_pct=lambda x: (x["approval_rate"] * 100).round(1))
    .sort_values("count", ascending=False)
    .head(30)
    .reset_index()
)
print(f"\n  Top 30 vendors by volume (min 20 estimates):")
print(top_vendors[["vr_vndr_id", "approval_rate_pct", "count"]].to_string(index=False))

# 5e. State-level analysis
if "licplte_st" in df.columns:
    state_analysis = approval_summary(df, "licplte_st")
    print("\n  Top/bottom 10 states by approval rate (min 50 estimates):")
    state_filtered = state_analysis[state_analysis["total_estimates"] >= 50]
    print(state_filtered.head(5)[["licplte_st", "approval_rate_pct",
                                   "total_estimates"]].to_string(index=False))
    print("  ...")
    print(state_filtered.tail(5)[["licplte_st", "approval_rate_pct",
                                   "total_estimates"]].to_string(index=False))


# ─────────────────────────────────────────────
# 6. MULTIVARIATE RULE SIMULATION
# ─────────────────────────────────────────────
print("\n── 6. Multivariate rule simulation ─────")

rules = [
    {
        "rule": "R1: Amount ≤ $500",
        "mask": df["est_tot_amt"] <= 500,
    },
    {
        "rule": "R2: Amount ≤ $750 AND labour ≤ 4 hrs",
        "mask": (df["est_tot_amt"] <= 750) & (df["lbr_hr_qty"] <= 4),
    },
    {
        "rule": "R3: Trusted vendor AND amount ≤ $1,000",
        "mask": (df["vendor_tier"] == "trusted") & (df["est_tot_amt"] <= 1000),
    },
    {
        "rule": "R4: Trusted vendor AND amount ≤ $500 AND labour ≤ 6 hrs",
        "mask": (df["vendor_tier"] == "trusted")
                & (df["est_tot_amt"] <= 500)
                & (df["lbr_hr_qty"] <= 6),
    },
    {
        "rule": "R5: Amount ≤ $500 AND line items ≤ 10",
        "mask": (df["est_tot_amt"] <= 500) & (df["line_item_count"] <= 10),
    },
    {
        "rule": "R6: Above-avg+ vendor AND amount ≤ $750 AND labour ≤ 8 hrs",
        "mask": (df["vendor_tier"].isin(["above_avg", "trusted"]))
                & (df["est_tot_amt"] <= 750)
                & (df["lbr_hr_qty"] <= 8),
    },
]

rule_results = []
for r in rules:
    subset = df[r["mask"]]
    if len(subset) == 0:
        continue
    result = {
        "Rule": r["rule"],
        "Estimates covered": len(subset),
        "Coverage %": f"{len(subset)/len(df)*100:.1f}%",
        "Approval rate %": f"{subset['first_pass'].mean()*100:.1f}%",
        "Would auto-approve": len(subset),
        "Wrong approvals (revisions needed)": int((subset["first_pass"] == 0).sum()),
        "Wrong approval rate %": f"{(subset['first_pass']==0).mean()*100:.1f}%",
    }
    rule_results.append(result)

rules_df = pd.DataFrame(rule_results)
print(rules_df.to_string(index=False))


# ─────────────────────────────────────────────
# 7. CORRELATION ANALYSIS
# ─────────────────────────────────────────────
print("\n── 7. Numeric correlations with first_pass ─")

numeric_cols = [
    "est_tot_amt", "lbr_hr_qty", "line_item_count", "cost_per_lbr_hr",
    "time_to_approve_days", "vendor_approval_rate", "veh_age",
    "bdy_lbr_rate", "mchncl_lbr_rate", "frm_lbr_rate", "pnt_mtrl_rate",
    "dmstc_part_disc_amt", "frn_part_disc_amt",
]
numeric_cols = [c for c in numeric_cols if c in df.columns]

corr = (
    df[numeric_cols + ["first_pass"]]
    .corr()["first_pass"]
    .drop("first_pass")
    .sort_values(key=abs, ascending=False)
    .to_frame("correlation_with_first_pass")
    .round(4)
)
print(corr.to_string())


# ─────────────────────────────────────────────
# 8. VENDOR DEEP-DIVE
# ─────────────────────────────────────────────
vendor_detail = (
    df.groupby("vr_vndr_id").agg(
        total_estimates=("first_pass", "count"),
        first_pass_count=("first_pass", "sum"),
        approval_rate=("first_pass", "mean"),
        avg_est_amt=("est_tot_amt", "mean"),
        avg_lbr_hrs=("lbr_hr_qty", "mean"),
        avg_line_items=("line_item_count", "mean"),
        avg_time_to_approve=("time_to_approve_days", "mean"),
    )
    .query("total_estimates >= 10")
    .assign(
        approval_rate_pct=lambda x: (x["approval_rate"] * 100).round(1),
        avg_est_amt=lambda x: x["avg_est_amt"].round(0),
        avg_lbr_hrs=lambda x: x["avg_lbr_hrs"].round(1),
        avg_line_items=lambda x: x["avg_line_items"].round(1),
    )
    .sort_values("approval_rate", ascending=False)
    .reset_index()
)


# ─────────────────────────────────────────────
# 9. CROSS-TAB HEATMAP DATA
# ─────────────────────────────────────────────
cross_tab = (
    df.groupby(["est_amt_bucket", "lbr_hr_bucket"])["first_pass"]
    .agg(approval_rate="mean", count="count")
    .unstack("lbr_hr_bucket")
    .round(3)
)
# Flatten column names
cross_tab_rate = cross_tab["approval_rate"] * 100
cross_tab_count = cross_tab["count"]


# ─────────────────────────────────────────────
# 10. DECISION TREE RULES (optional ML)
# ─────────────────────────────────────────────
print("\n── 10. Decision tree rule extraction ───")

try:
    from sklearn.tree import DecisionTreeClassifier, export_text
    from sklearn.preprocessing import LabelEncoder

    feature_cols = [
        "est_tot_amt", "lbr_hr_qty", "line_item_count",
        "cost_per_lbr_hr", "vendor_approval_rate", "veh_age",
    ]
    feature_cols = [c for c in feature_cols if c in df.columns]

    X = df[feature_cols].copy()
    y = df["first_pass"]

    # Drop rows with any nulls in features
    mask = X.notna().all(axis=1) & y.notna()
    X, y = X[mask], y[mask]

    clf = DecisionTreeClassifier(
        max_depth=4,
        min_samples_leaf=100,
        class_weight="balanced",
        random_state=42
    )
    clf.fit(X, y)

    tree_rules = export_text(clf, feature_names=feature_cols)
    print("\n  Decision tree rules (max depth 4):")
    print(tree_rules)

    feature_importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": clf.feature_importances_
    }).sort_values("importance", ascending=False)
    print("\n  Feature importances:")
    print(feature_importance.to_string(index=False))

    dt_available = True

except ImportError:
    print("  scikit-learn not installed. Skipping decision tree.")
    print("  Install with: pip install scikit-learn")
    tree_rules = "scikit-learn not available"
    feature_importance = pd.DataFrame()
    dt_available = False


# ─────────────────────────────────────────────
# 11. EXPORT TO EXCEL
# ─────────────────────────────────────────────
print(f"\n── 11. Writing Excel output → {OUTPUT_PATH}")

with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:

    # Sheet 1: Summary
    summary_data = pd.DataFrame({
        "Metric": [
            "Total estimates",
            "First-pass approvals",
            "Needed revisions",
            "Overall first-pass rate",
            "Unique vendors",
            "Unique vendor groups",
            "Estimate amount range",
            "Labour hours range",
        ],
        "Value": [
            f"{len(df):,}",
            f"{df['first_pass'].sum():,}",
            f"{(df['first_pass']==0).sum():,}",
            f"{overall_rate:.1%}",
            f"{df['vr_vndr_id'].nunique():,}",
            f"{df['vndr_grp_nbr'].nunique() if 'vndr_grp_nbr' in df.columns else 'N/A'}",
            f"${df['est_tot_amt'].min():.0f} – ${df['est_tot_amt'].max():,.0f}",
            f"{df['lbr_hr_qty'].min():.0f} – {df['lbr_hr_qty'].max():.0f} hrs",
        ]
    })
    summary_data.to_excel(writer, sheet_name="Summary", index=False)

    # Sheet 2: Approval by amount bucket
    amt_analysis.to_excel(writer, sheet_name="By_Amount_Bucket", index=False)

    # Sheet 3: Approval by labour hours
    lbr_analysis.to_excel(writer, sheet_name="By_Labour_Hours", index=False)

    # Sheet 4: Vendor tier analysis
    vt_analysis.to_excel(writer, sheet_name="By_Vendor_Tier", index=False)

    # Sheet 5: All vendor detail
    vendor_detail.to_excel(writer, sheet_name="Vendor_Detail", index=False)

    # Sheet 6: Rule simulation
    rules_df.to_excel(writer, sheet_name="Rule_Simulation", index=False)

    # Sheet 7: Correlations
    corr.reset_index().rename(columns={"index": "feature"})\
        .to_excel(writer, sheet_name="Correlations", index=False)

    # Sheet 8: Cross-tab heatmap (approval rate %)
    cross_tab_rate.to_excel(writer, sheet_name="Crosstab_Approval_Rate")

    # Sheet 9: Cross-tab heatmap (count)
    cross_tab_count.to_excel(writer, sheet_name="Crosstab_Count")

    # Sheet 10: State analysis
    if "licplte_st" in df.columns:
        state_analysis.to_excel(writer, sheet_name="By_State", index=False)

    # Sheet 11: Decision tree feature importance
    if dt_available and not feature_importance.empty:
        feature_importance.to_excel(writer, sheet_name="DT_Feature_Importance",
                                    index=False)

    # Sheet 12: Full cleaned data with engineered features
    export_cols = [
        "est_id", "vr_vndr_id", "vndr_grp_nbr", "est_tot_amt", "lbr_hr_qty",
        "line_item_count", "rvsn_nbr", "first_pass",
        "cost_per_lbr_hr", "est_amt_bucket", "lbr_hr_bucket",
        "vendor_approval_rate", "vendor_tier",
        "time_to_approve_days", "licplte_st", "veh_yr", "veh_age",
        "veh_make", "veh_modl", "dmg_dsc",
    ]
    export_cols = [c for c in export_cols if c in df.columns]
    df[export_cols].to_excel(writer, sheet_name="Cleaned_Data", index=False)

print(f"  Done. Open {OUTPUT_PATH} to explore all sheets.")
print("\n  Sheets written:")
print("    1  Summary               — dataset overview")
print("    2  By_Amount_Bucket      — approval rate per $250 band")
print("    3  By_Labour_Hours       — approval rate per labour hour band")
print("    4  By_Vendor_Tier        — approval rate per vendor quality tier")
print("    5  Vendor_Detail         — per-vendor stats (all vendors ≥10 estimates)")
print("    6  Rule_Simulation       — 6 candidate rules with coverage & error rate")
print("    7  Correlations          — numeric feature correlations with first_pass")
print("    8  Crosstab_Approval_Rate— amount bucket × labour hours heatmap")
print("    9  Crosstab_Count        — same heatmap, count view")
print("   10  By_State              — approval rate by licence plate state")
print("   11  DT_Feature_Importance — decision tree feature ranking (if sklearn)")
print("   12  Cleaned_Data          — full dataset with all engineered features")
print("\n── Analysis complete ────────────────────\n")
