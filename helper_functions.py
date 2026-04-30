"""
Auto-Approval Rule Evaluator
=============================
Rule:  vendor_tier = trusted
  AND  est_tot_amt        <= 500
  AND  lbr_hr_qty         <= 6
  AND  line_item_count    <= 10
  AND  negative_or_null_est_ind = 0

True label  : first_pass = 1  (estimate approved on revision 1, i.e. rvsn_nbr = 1)
Prediction  : auto_approve = 1 (estimate satisfies all rule conditions)

Confusion matrix interpretation
---------------------------------
  TP  Rule says approve  →  actually was approved first pass   (correct auto-approval)
  FP  Rule says approve  →  actually needed revisions          (wrong auto-approval)
  TN  Rule says don't    →  actually needed revisions          (correct hold-back)
  FN  Rule says don't    →  actually was approved first pass   (missed auto-approval)

Precision  = TP / (TP + FP)  →  of all auto-approved, how many were truly fine?
Recall     = TP / (TP + FN)  →  of all truly first-pass, how many did we catch?
Accuracy   = (TP + TN) / N   →  overall correctness across all estimates
F1         = harmonic mean of precision & recall
"""

import pandas as pd
import numpy as np
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# 0.  CONFIG  ← update these two paths
# ─────────────────────────────────────────────
DATA_PATH   = "your_estimates_file.csv"   # raw input file
OUTPUT_PATH = "rule_evaluation_results.xlsx"

# Minimum number of past estimates a vendor needs before
# they can be classified as "trusted" (avoids small-sample noise)
VENDOR_MIN_ESTIMATES = 10


# ─────────────────────────────────────────────
# 1.  LOAD
# ─────────────────────────────────────────────
print("── Loading data ─────────────────────────")
df = pd.read_csv(DATA_PATH, low_memory=False)
print(f"   Rows: {len(df):,}   Columns: {df.shape[1]}")


# ─────────────────────────────────────────────
# 2.  TARGET VARIABLE
# ─────────────────────────────────────────────
print("\n── Building target variable ─────────────")
df["first_pass"] = (df["rvsn_nbr"] == 1).astype(int)
print(f"   First-pass approvals : {df['first_pass'].sum():,}  "
      f"({df['first_pass'].mean():.1%})")
print(f"   Needed revisions     : {(df['first_pass']==0).sum():,}  "
      f"({1 - df['first_pass'].mean():.1%})")


# ─────────────────────────────────────────────
# 3.  VENDOR TIER  (trusted / other)
# ─────────────────────────────────────────────
print("\n── Computing vendor tiers ───────────────")

vendor_stats = (
    df.groupby("vr_vndr_id")["first_pass"]
    .agg(vendor_approval_rate="mean", vendor_est_count="count")
    .reset_index()
)

# Quartile-based tiering (same logic as the analysis script)
eligible = vendor_stats["vendor_est_count"] >= VENDOR_MIN_ESTIMATES

vendor_stats["vendor_tier"] = "insufficient_history"
vendor_stats.loc[eligible, "vendor_tier"] = pd.qcut(
    vendor_stats.loc[eligible, "vendor_approval_rate"],
    q=[0, 0.25, 0.5, 0.75, 1.0],
    labels=["low", "below_avg", "above_avg", "trusted"],
    duplicates="drop"
).astype(str)

df = df.merge(
    vendor_stats[["vr_vndr_id", "vendor_approval_rate", "vendor_tier"]],
    on="vr_vndr_id", how="left"
)

tier_counts = df["vendor_tier"].value_counts()
print(f"   Trusted vendors cover : "
      f"{(df['vendor_tier']=='trusted').sum():,} estimates "
      f"({(df['vendor_tier']=='trusted').mean():.1%})")
for tier, cnt in tier_counts.items():
    print(f"   {tier:<25} {cnt:>6,} estimates")


# ─────────────────────────────────────────────
# 4.  APPLY THE RULE
# ─────────────────────────────────────────────
print("\n── Applying auto-approval rule ──────────")

rule_conditions = {
    "vendor_tier = trusted"        : df["vendor_tier"] == "trusted",
    "est_tot_amt <= $500"          : df["est_tot_amt"] <= 500,
    "lbr_hr_qty <= 6 hrs"         : df["lbr_hr_qty"] <= 6,
    "line_item_count <= 10"        : df["line_item_count"] <= 10,
    "negative_or_null_est_ind = 0" : df["negative_or_null_est_ind"] == 0,
}

# Show how many estimates each individual condition passes
print("\n   Individual condition coverage:")
for name, mask in rule_conditions.items():
    print(f"   {name:<38} passes {mask.sum():>6,}  ({mask.mean():.1%})")

# Combined rule — all conditions must be true
df["auto_approve"] = np.ones(len(df), dtype=bool)
for mask in rule_conditions.values():
    df["auto_approve"] &= mask
df["auto_approve"] = df["auto_approve"].astype(int)

print(f"\n   Estimates flagged for auto-approval : "
      f"{df['auto_approve'].sum():,}  "
      f"({df['auto_approve'].mean():.1%} of all estimates)")


# ─────────────────────────────────────────────
# 5.  CONFUSION MATRIX
# ─────────────────────────────────────────────
print("\n── Confusion matrix ─────────────────────")

y_true = df["first_pass"]      # 1 = truly approved first pass
y_pred = df["auto_approve"]    # 1 = rule says auto-approve

TP = int(((y_pred == 1) & (y_true == 1)).sum())   # correct auto-approvals
FP = int(((y_pred == 1) & (y_true == 0)).sum())   # wrong auto-approvals
TN = int(((y_pred == 0) & (y_true == 0)).sum())   # correctly held back
FN = int(((y_pred == 0) & (y_true == 1)).sum())   # missed auto-approvals

print(f"""
                        Actual: first-pass    Actual: needed revision
   Rule: auto-approve       TP = {TP:>6,}              FP = {FP:>6,}
   Rule: hold for review    FN = {FN:>6,}              TN = {TN:>6,}
""")


# ─────────────────────────────────────────────
# 6.  METRICS
# ─────────────────────────────────────────────
print("── Performance metrics ──────────────────")

accuracy  = (TP + TN) / len(df)
precision = TP / (TP + FP) if (TP + FP) > 0 else 0
recall    = TP / (TP + FN) if (TP + FN) > 0 else 0
f1        = (2 * precision * recall / (precision + recall)
             if (precision + recall) > 0 else 0)

# Additional business-relevant metrics
wrong_approval_rate = FP / (TP + FP) if (TP + FP) > 0 else 0
coverage            = (TP + FP) / len(df)   # % of all estimates auto-approved
missed_savings      = FN                    # first-pass estimates we didn't auto-approve

print(f"""
   Accuracy               {accuracy:.1%}
     (how often the rule is correct across ALL estimates)

   Precision              {precision:.1%}
     (of estimates we auto-approved, % that were truly fine)

   Recall                 {recall:.1%}
     (of all truly first-pass estimates, % we caught)

   F1 Score               {f1:.3f}
     (balance of precision and recall)

   ── Business framing ──────────────────────

   Wrong approval rate    {wrong_approval_rate:.1%}
     ({FP:,} estimates auto-approved that actually needed revisions)

   Coverage               {coverage:.1%}
     ({TP + FP:,} of {len(df):,} total estimates would be auto-approved)

   Missed opportunities   {missed_savings:,}
     (first-pass estimates the rule didn't capture — manual review overhead)
""")


# ─────────────────────────────────────────────
# 7.  BREAKDOWN — WHERE DO ERRORS COME FROM?
# ─────────────────────────────────────────────
print("── FP deep-dive: wrong auto-approvals ───")

fp_df = df[(df["auto_approve"] == 1) & (df["first_pass"] == 0)].copy()

print(f"\n   Total wrong auto-approvals (FP): {len(fp_df):,}")

if len(fp_df) > 0:
    print(f"\n   Revision distribution of FPs:")
    print(fp_df["rvsn_nbr"].value_counts().sort_index()
          .rename("count").to_string())

    print(f"\n   FP amount distribution:")
    print(fp_df["est_tot_amt"].describe().round(1).to_string())

    print(f"\n   FP labour hours distribution:")
    print(fp_df["lbr_hr_qty"].describe().round(1).to_string())

    print(f"\n   FP line item count distribution:")
    print(fp_df["line_item_count"].describe().round(1).to_string())

    if "licplte_st" in fp_df.columns:
        print(f"\n   Top 10 states in FPs:")
        print(fp_df["licplte_st"].value_counts().head(10).to_string())

print("\n── FN note: missed first-pass estimates ─")
fn_df = df[(df["auto_approve"] == 0) & (df["first_pass"] == 1)]
print(f"   {len(fn_df):,} first-pass estimates not caught by the rule.")
print(f"   These still go to manual review — not wrong, just not automated.")


# ─────────────────────────────────────────────
# 8.  SENSITIVITY ANALYSIS
#     What happens if we relax/tighten thresholds?
# ─────────────────────────────────────────────
print("\n── Sensitivity analysis ─────────────────")
print("   (varying est_tot_amt threshold, trusted vendors only)\n")

results = []
for amt_limit in [250, 350, 500, 600, 750, 1000, 1500]:
    mask = (
        (df["vendor_tier"] == "trusted") &
        (df["est_tot_amt"] <= amt_limit) &
        (df["lbr_hr_qty"] <= 6) &
        (df["line_item_count"] <= 10) &
        (df["negative_or_null_est_ind"] == 0)
    )
    tp_ = int((mask & (y_true == 1)).sum())
    fp_ = int((mask & (y_true == 0)).sum())
    fn_ = int((~mask & (y_true == 1)).sum())
    tn_ = int((~mask & (y_true == 0)).sum())
    prec_ = tp_ / (tp_ + fp_) if (tp_ + fp_) > 0 else 0
    rec_  = tp_ / (tp_ + fn_) if (tp_ + fn_) > 0 else 0
    results.append({
        "amt_limit"   : f"<= ${amt_limit:,}",
        "auto_approved": tp_ + fp_,
        "coverage_pct" : f"{(tp_+fp_)/len(df)*100:.1f}%",
        "precision_pct": f"{prec_*100:.1f}%",
        "recall_pct"   : f"{rec_*100:.1f}%",
        "wrong_approvals": fp_,
        "wrong_pct"    : f"{fp_/(tp_+fp_)*100:.1f}%" if (tp_+fp_)>0 else "0%",
    })

sens_df = pd.DataFrame(results)
print(sens_df.to_string(index=False))


# ─────────────────────────────────────────────
# 9.  EXPORT TO EXCEL
# ─────────────────────────────────────────────
print(f"\n── Writing results → {OUTPUT_PATH} ──")

metrics_df = pd.DataFrame({
    "Metric": [
        "Total estimates",
        "True positives (TP) — correct auto-approvals",
        "False positives (FP) — wrong auto-approvals",
        "True negatives (TN) — correctly held back",
        "False negatives (FN) — missed auto-approvals",
        "Accuracy",
        "Precision",
        "Recall",
        "F1 Score",
        "Wrong approval rate",
        "Coverage (auto-approved %)",
        "Missed first-pass opportunities",
    ],
    "Value": [
        len(df),
        TP, FP, TN, FN,
        f"{accuracy:.1%}",
        f"{precision:.1%}",
        f"{recall:.1%}",
        f"{f1:.3f}",
        f"{wrong_approval_rate:.1%}",
        f"{coverage:.1%}",
        missed_savings,
    ]
})

export_cols = [
    "est_id", "vr_vndr_id", "vendor_tier", "vendor_approval_rate",
    "est_tot_amt", "lbr_hr_qty", "line_item_count",
    "negative_or_null_est_ind", "rvsn_nbr",
    "first_pass", "auto_approve",
]
export_cols = [c for c in export_cols if c in df.columns]

# Label each row for easy filtering in Excel
df["outcome"] = "TN"
df.loc[(df["auto_approve"]==1) & (df["first_pass"]==1), "outcome"] = "TP"
df.loc[(df["auto_approve"]==1) & (df["first_pass"]==0), "outcome"] = "FP"
df.loc[(df["auto_approve"]==0) & (df["first_pass"]==1), "outcome"] = "FN"
export_cols.append("outcome")

with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
    metrics_df.to_excel(writer, sheet_name="Metrics_Summary", index=False)
    sens_df.to_excel(writer, sheet_name="Sensitivity_Analysis", index=False)
    df[export_cols].to_excel(writer, sheet_name="All_Estimates_Labelled", index=False)
    df[export_cols][df["outcome"]=="FP"].to_excel(
        writer, sheet_name="FP_Wrong_Approvals", index=False)
    df[export_cols][df["outcome"]=="FN"].to_excel(
        writer, sheet_name="FN_Missed_Opportunities", index=False)

print(f"""
   Sheets written:
     1  Metrics_Summary         — accuracy, precision, recall, F1
     2  Sensitivity_Analysis    — how metrics shift at different $ thresholds
     3  All_Estimates_Labelled  — every row tagged TP / FP / TN / FN
     4  FP_Wrong_Approvals      — estimates auto-approved but needed revision
     5  FN_Missed_Opportunities — first-pass estimates the rule didn't capture

── Done ─────────────────────────────────\n""")
