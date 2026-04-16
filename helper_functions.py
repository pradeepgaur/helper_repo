"""
Decision Tree Auto-Approval Model  — clean rewrite
=====================================================
Target  : first_pass = 1 if rvsn_nbr == 1, else 0
Outputs : charts in dt_output/, results in decision_tree_results.xlsx

Update DATA_PATH before running.
pip install scikit-learn matplotlib openpyxl pandas numpy
"""

import pandas as pd
import numpy as np
import warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix, roc_auc_score,
    roc_curve, precision_recall_curve
)
from sklearn.tree import _tree

warnings.filterwarnings("ignore")

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_PATH  = "your_estimates_file.csv"
OUTPUT_DIR = "dt_output"
EXCEL_PATH = "decision_tree_results.xlsx"

# Leaf predicts AUTO-APPROVE when first-pass rate >= this value
# Lower (0.60) = more coverage  |  Higher (0.80) = higher precision
APPROVAL_THRESHOLD = 0.65

# Minimum samples per leaf — key guard against overfitting
MIN_LEAF = 300

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# ── Chart style ───────────────────────────────────────────────────────────────
GOLD, GREEN, RED, BLUE, AMBER, MUTED, WHITE = (
    "#e0a84b", "#3fb950", "#f85149", "#58a6ff", "#d29922", "#7a8899", "#f0f4f8"
)
plt.rcParams.update({
    "figure.facecolor": "#0d1117", "axes.facecolor": "#161b22",
    "axes.edgecolor":   "#2a3444", "axes.labelcolor": MUTED,
    "axes.titlecolor":  WHITE,     "text.color":      WHITE,
    "xtick.color":      MUTED,     "ytick.color":     MUTED,
    "grid.color":       "#2a3444", "grid.linestyle":  "--",
    "grid.alpha":       0.5,       "font.family":     "monospace",
    "figure.dpi":       130,
})

# ═════════════════════════════════════════════════════════════════
# 1. LOAD
# ═════════════════════════════════════════════════════════════════
print("── 1. Loading ───────────────────────────")
df = pd.read_csv(DATA_PATH, low_memory=False)
print(f"   {len(df):,} rows  x  {df.shape[1]} columns")

if "time_to_approve_days" in df.columns:
    df["time_to_approve_days"] = df["time_to_approve_days"].clip(lower=0)

# ═════════════════════════════════════════════════════════════════
# 2. TARGET
# ═════════════════════════════════════════════════════════════════
df["first_pass"] = (df["rvsn_nbr"] == 1).astype(int)
pos = df["first_pass"].mean()
print(f"   first_pass=1 : {df['first_pass'].sum():,}  ({pos:.1%})")
print(f"   first_pass=0 : {(df['first_pass']==0).sum():,}  ({1-pos:.1%})")

# ═════════════════════════════════════════════════════════════════
# 3. FEATURES
# ═════════════════════════════════════════════════════════════════
print("\n── 2. Feature engineering ───────────────")

global_mean = df["first_pass"].mean()

# Vendor score with Bayesian shrinkage, rounded to 2dp
# (rounding reduces unique split points so tree stays readable)
vstats = (
    df.groupby("vr_vndr_id")["first_pass"]
    .agg(vrate="mean", vcnt="count")
    .reset_index()
)
K = 20
vstats["vendor_score"] = (
    (vstats["vrate"] * vstats["vcnt"] + global_mean * K)
    / (vstats["vcnt"] + K)
).round(2)
df = df.merge(vstats[["vr_vndr_id", "vendor_score"]], on="vr_vndr_id", how="left")

# Cost per labour hour — capped and rounded
df["cost_per_lbr_hr"] = np.where(
    df["lbr_hr_qty"] > 0,
    (df["est_tot_amt"] / df["lbr_hr_qty"]).clip(upper=2000).round(0),
    0
)

# Vehicle age
if "veh_yr" in df.columns:
    df["veh_age"] = (pd.Timestamp.now().year - df["veh_yr"]).clip(lower=0, upper=30)

print("   vendor_score (Bayesian-smoothed, 2dp)")
print("   cost_per_lbr_hr (capped $2k, rounded)")
print("   veh_age")

# ═════════════════════════════════════════════════════════════════
# 4. FEATURE SELECTION
# ═════════════════════════════════════════════════════════════════
CANDIDATES = [
    "vendor_score",
    "line_item_count",
    "est_tot_amt",
    "lbr_hr_qty",
    "cost_per_lbr_hr",
    "negative_or_null_est_ind",
    "veh_age",
    "est_disc_ind",
]
FEATURES = [f for f in CANDIDATES if f in df.columns]

model_df = df[FEATURES + ["first_pass"]].dropna().reset_index(drop=True)

# Force all features to float64 — CRITICAL
# If any column is object/string dtype the tree ignores min_samples_leaf
# and splits to n=1 leaves (which is exactly what happened).
print("\n   Dtypes before coercion:")
for f in FEATURES:
    print(f"   {f:<30} {model_df[f].dtype}")

for f in FEATURES:
    model_df[f] = pd.to_numeric(model_df[f], errors="coerce")
model_df = model_df.dropna().reset_index(drop=True)

print("\n   Dtypes after coercion (must all be float64 or int64):")
for f in FEATURES:
    print(f"   {f:<30} {model_df[f].dtype}")

print(f"\n   Features  : {FEATURES}")
print(f"   Model rows: {len(model_df):,}")
print(f"   MIN_LEAF={MIN_LEAF} — max leaves expected ~{int(len(model_df)*0.75/MIN_LEAF*2)}")

X = model_df[FEATURES].values.astype(np.float64)
y = model_df["first_pass"].values.astype(int)

# ═════════════════════════════════════════════════════════════════
# 5. TRAIN / TEST SPLIT
# ═════════════════════════════════════════════════════════════════
X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.25, random_state=42, stratify=y
)
print(f"\n── 3. Train/test split ──────────────────")
print(f"   Train: {len(X_tr):,}   Test: {len(X_te):,}")

# ═════════════════════════════════════════════════════════════════
# 6. TRAIN TREES AT DEPTH 3, 4, 5
# ═════════════════════════════════════════════════════════════════
print(f"\n── 4. Training trees ────────────────────")
print(f"   MIN_LEAF={MIN_LEAF}  APPROVAL_THRESHOLD={APPROVAL_THRESHOLD:.0%}\n")

results = {}
for depth in [3, 4, 5]:
    t = DecisionTreeClassifier(
        max_depth=depth,
        min_samples_leaf=MIN_LEAF,
        min_samples_split=MIN_LEAF * 2,
        class_weight=None,
        criterion="gini",
        random_state=42,
    )
    t.fit(X_tr, y_tr)
    prob = t.predict_proba(X_te)[:, 1]
    pred = (prob >= APPROVAL_THRESHOLD).astype(int)
    cv   = cross_val_score(
        t, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=42),
        scoring="f1"
    ).mean()
    results[depth] = dict(
        clf=t, prob=prob, pred=pred,
        precision = precision_score(y_te, pred, zero_division=0),
        recall    = recall_score(y_te, pred, zero_division=0),
        f1        = f1_score(y_te, pred, zero_division=0),
        auc       = roc_auc_score(y_te, prob),
        accuracy  = accuracy_score(y_te, pred),
        cv_f1     = cv,
    )
    r = results[depth]
    print(f"   depth={depth}  P={r['precision']:.3f}  R={r['recall']:.3f}  "
          f"F1={r['f1']:.3f}  AUC={r['auc']:.3f}  CV-F1={cv:.3f}")

best_depth = max(results, key=lambda d: results[d]["f1"])
best = results[best_depth]
clf  = best["clf"]
print(f"\n   Best depth: {best_depth}  F1={best['f1']:.3f}")

# ═════════════════════════════════════════════════════════════════
# 7. METRICS
# ═════════════════════════════════════════════════════════════════
print("\n── 5. Metrics ───────────────────────────")
cm = confusion_matrix(y_te, best["pred"])
TN, FP, FN, TP = cm.ravel()
print(f"   Precision={best['precision']:.1%}  Recall={best['recall']:.1%}  "
      f"F1={best['f1']:.3f}  AUC={best['auc']:.3f}")
print(f"   TP={TP:,}  FP={FP:,}  TN={TN:,}  FN={FN:,}")

# ═════════════════════════════════════════════════════════════════
# 8. FEATURE IMPORTANCE
# ═════════════════════════════════════════════════════════════════
fi = (
    pd.DataFrame({"feature": FEATURES, "importance": clf.feature_importances_})
    .sort_values("importance", ascending=False)
)
print("\n── 6. Feature importances ───────────────")
print(fi.to_string(index=False))

# ═════════════════════════════════════════════════════════════════
# 9. PRINT TREE TEXT
# ═════════════════════════════════════════════════════════════════
print("\n── 7. Tree structure ────────────────────")
print(export_text(clf, feature_names=FEATURES))

# ═════════════════════════════════════════════════════════════════
# 10. LEAF DIAGNOSTICS
# ═════════════════════════════════════════════════════════════════
print("── 8. Leaf diagnostics ──────────────────")

t_      = clf.tree_
left_ch = t_.children_left
rght_ch = t_.children_right

leaf_rates_list = []
for nid in range(t_.node_count):
    if left_ch[nid] == _tree.TREE_LEAF:
        cnts  = t_.value[nid][0]
        total = int(cnts.sum())
        c1    = int(cnts[1]) if len(cnts) > 1 else 0
        rate  = c1 / total if total > 0 else 0.0
        leaf_rates_list.append(rate)
        tag = ">>> AUTO-APPROVE" if rate >= APPROVAL_THRESHOLD else "    manual review"
        print(f"   node {nid:>3}  n={total:>6,}  fp={c1:>6,}  "
              f"rate={rate:.1%}  {tag}")

max_leaf_rate = max(leaf_rates_list) if leaf_rates_list else 0.0
print(f"\n   Max leaf rate      : {max_leaf_rate:.1%}")
print(f"   APPROVAL_THRESHOLD : {APPROVAL_THRESHOLD:.1%}")

eff_threshold = APPROVAL_THRESHOLD
if max_leaf_rate < APPROVAL_THRESHOLD:
    eff_threshold = round(max_leaf_rate - 0.005, 3)
    print(f"\n   No leaf met {APPROVAL_THRESHOLD:.0%} — auto-adjusted to {eff_threshold:.1%}")
    print(f"   To set manually: change APPROVAL_THRESHOLD at top of script")

# ═════════════════════════════════════════════════════════════════
# 11. EXTRACT RULES FROM LEAVES
# ═════════════════════════════════════════════════════════════════
def extract_rules(clf, feature_names, threshold):
    """Walk tree via children_left/right — never node*2+1."""
    t_      = clf.tree_
    left    = t_.children_left
    right   = t_.children_right
    feature = t_.feature
    splits  = t_.threshold
    vals    = t_.value
    rows    = []

    def walk(node, path):
        if left[node] == _tree.TREE_LEAF:
            cnts  = vals[node][0]
            total = int(cnts.sum())
            c1    = int(cnts[1]) if len(cnts) > 1 else 0
            rate  = c1 / total if total > 0 else 0.0
            rows.append({
                "rule_conditions"  : "\n  AND ".join(path) if path else "ALL",
                "samples"          : total,
                "first_pass_n"     : c1,
                "approval_rate_pct": round(rate * 100, 1),
                "prediction"       : 1 if rate >= threshold else 0,
                "action"           : "AUTO-APPROVE" if rate >= threshold
                                     else "MANUAL REVIEW",
            })
        else:
            fname = feature_names[feature[node]]
            thr   = round(float(splits[node]), 4)
            walk(left[node],  path + [f"{fname} <= {thr}"])
            walk(right[node], path + [f"{fname} >  {thr}"])

    walk(0, [])
    return (
        pd.DataFrame(rows)
        .sort_values("approval_rate_pct", ascending=False)
        .reset_index(drop=True)
    )


rules_df = extract_rules(clf, FEATURES, eff_threshold)
auto_df  = rules_df[rules_df["prediction"] == 1].reset_index(drop=True)
hold_df  = rules_df[rules_df["prediction"] == 0].reset_index(drop=True)

print(f"\n   AUTO-APPROVE leaves : {len(auto_df)}")
print(f"   MANUAL REVIEW leaves: {len(hold_df)}")

print("\n── All leaves sorted by approval rate ───")
for _, row in rules_df.iterrows():
    print(f"\n   [{row['action']}]  rate={row['approval_rate_pct']}%  "
          f"n={row['samples']:,}")
    for line in row["rule_conditions"].split("\n"):
        print(f"     {line}")

# ═════════════════════════════════════════════════════════════════
# 12. FINAL RULES PRINT
# ═════════════════════════════════════════════════════════════════
sep = "=" * 64
print(f"\n{sep}")
print("   DECISION TREE  —  FINAL AUTO-APPROVAL RULES")
print(sep)
print(f"\n   Model     : DecisionTree depth={best_depth} "
      f"min_leaf={MIN_LEAF} threshold={eff_threshold:.0%}")
print(f"   Precision : {best['precision']:.1%}   "
      f"Recall : {best['recall']:.1%}   F1 : {best['f1']:.3f}\n")

if len(auto_df) == 0:
    print("   No leaves exceeded the approval threshold.")
    print(f"   Best leaf rate found: {max_leaf_rate:.1%}")
    print(f"   Suggestion: set APPROVAL_THRESHOLD = {round(max_leaf_rate-0.02,2):.0%}"
          f" to get {round(max_leaf_rate-0.02,0):.0%}+ auto-approval leaves.")
else:
    for i, row in auto_df.iterrows():
        bar = "─" * 56
        print(f"   Rule {i+1}  |  approval rate: {row['approval_rate_pct']}%"
              f"  |  estimates: {row['samples']:,}")
        print(f"   {bar}")
        print(f"   IF:")
        for cond in row["rule_conditions"].split("\n"):
            print(f"      {cond.strip()}")
        print(f"   THEN: AUTO-APPROVE")
        print(f"   {bar}\n")

print("   All other estimates  →  MANUAL REVIEW")
print(f"{sep}\n")

# ═════════════════════════════════════════════════════════════════
# 13. CHARTS
# ═════════════════════════════════════════════════════════════════
print("── 9. Generating charts ─────────────────")

# 1 — Feature importance
fig, ax = plt.subplots(figsize=(9, 4.5))
clrs = [GOLD if i == 0 else BLUE for i in range(len(fi))]
bars = ax.barh(fi["feature"][::-1], fi["importance"][::-1]*100,
               color=clrs[::-1], height=0.6, edgecolor="none")
for b, v in zip(bars, fi["importance"][::-1]*100):
    ax.text(v+0.3, b.get_y()+b.get_height()/2,
            f"{v:.1f}%", va="center", ha="left", fontsize=9, color=WHITE)
ax.set_xlabel("Importance (%)", color=MUTED)
ax.set_title("Feature importance", color=WHITE, fontsize=12, pad=10)
ax.set_xlim(0, fi["importance"].max()*118)
ax.grid(axis="x"); ax.spines[:].set_visible(False)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/01_feature_importance.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   01_feature_importance.png")

# 2 — Depth comparison
fig, ax = plt.subplots(figsize=(8, 4))
mets = ["precision","recall","f1","auc"]
cols_m = [GREEN, GOLD, BLUE, AMBER]
xp = np.arange(3); w = 0.2
for i, (m, c) in enumerate(zip(mets, cols_m)):
    vals = [results[d][m]*100 for d in [3,4,5]]
    bs   = ax.bar(xp+i*w, vals, w, label=m.upper(),
                  color=c, alpha=0.85, edgecolor="none")
    for b, v in zip(bs, vals):
        ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.5,
                f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=c)
ax.set_xticks(xp+w*1.5)
ax.set_xticklabels([f"Depth {d}" for d in [3,4,5]])
ax.set_ylim(0, 110); ax.set_ylabel("Score (%)", color=MUTED)
ax.set_title("Performance by tree depth", color=WHITE, fontsize=12, pad=10)
ax.legend(frameon=False, labelcolor=WHITE, fontsize=9)
ax.axvline([3,4,5].index(best_depth)+w*1.5,
           color=GOLD, linestyle="--", alpha=0.4, lw=1.5)
ax.grid(axis="y"); ax.spines[:].set_visible(False)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/02_depth_comparison.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   02_depth_comparison.png")

# 3 — Confusion matrix
fig, ax = plt.subplots(figsize=(5.5, 4.5))
cmap    = LinearSegmentedColormap.from_list("c", ["#161b22", GOLD])
cm_n    = cm.astype(float) / cm.sum(axis=1, keepdims=True)
ax.imshow(cm_n, cmap=cmap, aspect="auto")
for i in range(2):
    for j in range(2):
        lbl = [["TN","FP"],["FN","TP"]][i][j]
        col = WHITE if cm_n[i,j] < 0.5 else "#0d1117"
        ax.text(j, i, f"{lbl}\n{cm[i,j]:,}\n({cm_n[i,j]:.1%})",
                ha="center", va="center", fontsize=11,
                color=col, fontweight="bold")
ax.set_xticks([0,1]); ax.set_yticks([0,1])
ax.set_xticklabels(["Pred: Hold","Pred: Auto-approve"], fontsize=9)
ax.set_yticklabels(["Actual: Revised","Actual: First-pass"], fontsize=9)
ax.set_title(f"Confusion matrix — depth {best_depth}", color=WHITE, pad=10)
ax.spines[:].set_visible(False)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/03_confusion_matrix.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   03_confusion_matrix.png")

# 4 — ROC
fig, ax = plt.subplots(figsize=(6, 5))
fpr, tpr, _ = roc_curve(y_te, best["prob"])
ax.plot(fpr, tpr, color=GOLD, lw=2,
        label=f"Decision Tree  AUC={best['auc']:.3f}")
ax.plot([0,1],[0,1], color=MUTED, lw=1, linestyle="--",
        label="Random  AUC=0.500")
ax.fill_between(fpr, tpr, alpha=0.07, color=GOLD)
ax.set_xlabel("False Positive Rate", color=MUTED)
ax.set_ylabel("True Positive Rate", color=MUTED)
ax.set_title("ROC Curve", color=WHITE, fontsize=12, pad=10)
ax.legend(frameon=False, labelcolor=WHITE, fontsize=10)
ax.grid(); ax.spines[:].set_visible(False)
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/04_roc_curve.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   04_roc_curve.png")

# 5 — Precision-Recall
fig, ax = plt.subplots(figsize=(6, 5))
pc, rc, _ = precision_recall_curve(y_te, best["prob"])
ax.plot(rc, pc, color=BLUE, lw=2)
ax.fill_between(rc, pc, alpha=0.07, color=BLUE)
ax.scatter([best["recall"]], [best["precision"]], color=GOLD, s=70, zorder=5,
           label=f"P={best['precision']:.2f}  R={best['recall']:.2f}")
ax.set_xlabel("Recall", color=MUTED)
ax.set_ylabel("Precision", color=MUTED)
ax.set_title("Precision-Recall Curve", color=WHITE, fontsize=12, pad=10)
ax.legend(frameon=False, labelcolor=WHITE, fontsize=9)
ax.grid(); ax.spines[:].set_visible(False)
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/05_precision_recall.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   05_precision_recall.png")

# 6 — Leaf approval rates
fig, ax = plt.subplots(figsize=(10, max(4, len(rules_df)*0.55+1.5)))
sr   = rules_df.sort_values("approval_rate_pct")
clrs = [GREEN if p==1 else RED for p in sr["prediction"]]
yl   = [f"Leaf {i+1}  (n={r['samples']:,})"
        for i, (_,r) in enumerate(sr.iterrows())]
bars = ax.barh(range(len(sr)), sr["approval_rate_pct"],
               color=clrs, height=0.65, edgecolor="none")
for b, v in zip(bars, sr["approval_rate_pct"]):
    ax.text(v+0.5, b.get_y()+b.get_height()/2,
            f"{v:.1f}%", va="center", ha="left", fontsize=9, color=WHITE)
ax.set_yticks(range(len(sr))); ax.set_yticklabels(yl, fontsize=8)
ax.set_xlabel("First-pass approval rate (%)", color=MUTED)
ax.set_title(f"Approval rate per leaf — depth {best_depth} "
             f"(threshold {eff_threshold:.0%})",
             color=WHITE, fontsize=12, pad=10)
ax.axvline(eff_threshold*100, color=MUTED, linestyle="--", alpha=0.5, lw=1)
ax.text(eff_threshold*100+0.5, -0.6,
        f"{eff_threshold:.0%}", color=MUTED, fontsize=8)
ax.set_xlim(0, 110)
ax.legend(handles=[
    mpatches.Patch(color=GREEN, label="AUTO-APPROVE"),
    mpatches.Patch(color=RED,   label="MANUAL REVIEW"),
], frameon=False, labelcolor=WHITE, fontsize=9, loc="lower right")
ax.grid(axis="x"); ax.spines[:].set_visible(False)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/06_leaf_rates.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   06_leaf_rates.png")

# 7 — Tree diagram
fig, ax = plt.subplots(
    figsize=(max(14, best_depth*5), max(7, best_depth*2.5))
)
plot_tree(clf, feature_names=FEATURES,
          class_names=["Revised","First-pass"],
          filled=True, rounded=True, fontsize=7,
          impurity=False, proportion=True, ax=ax)
ax.set_title(f"Decision tree structure — depth {best_depth}",
             color=WHITE, fontsize=13, pad=12)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/07_tree_structure.png",
            bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("   07_tree_structure.png")

# ═════════════════════════════════════════════════════════════════
# 14. FULL DATA PREDICTIONS
# ═════════════════════════════════════════════════════════════════
print("\n── 10. Full dataset predictions ─────────")
full_prob = clf.predict_proba(X)[:, 1]
full_pred = (full_prob >= eff_threshold).astype(int)
model_df  = model_df.copy()
model_df["dt_probability"] = full_prob.round(4)
model_df["dt_prediction"]  = full_pred
model_df["outcome"] = "TN"
model_df.loc[(full_pred==1)&(y==1), "outcome"] = "TP"
model_df.loc[(full_pred==1)&(y==0), "outcome"] = "FP"
model_df.loc[(full_pred==0)&(y==1), "outcome"] = "FN"
fp_p = precision_score(y, full_pred, zero_division=0)
fp_r = recall_score(y, full_pred,    zero_division=0)
print(f"   Precision={fp_p:.1%}  Recall={fp_r:.1%}  "
      f"Auto-approved={full_pred.sum():,} ({full_pred.mean():.1%})")

# ═════════════════════════════════════════════════════════════════
# 15. EXPORT EXCEL
# ═════════════════════════════════════════════════════════════════
print(f"\n── 11. Excel -> {EXCEL_PATH} ─────────────")

metrics_out = pd.DataFrame({
    "Metric": ["Best depth","Threshold","Precision","Recall","F1",
               "AUC","CV F1","TP","FP","TN","FN",
               "Full data auto-approved","Full data auto-approved %"],
    "Value":  [best_depth, f"{eff_threshold:.0%}",
               f"{best['precision']:.1%}", f"{best['recall']:.1%}",
               f"{best['f1']:.3f}", f"{best['auc']:.3f}",
               f"{best['cv_f1']:.3f}",
               TP, FP, TN, FN,
               int(full_pred.sum()), f"{full_pred.mean():.1%}"]
})
depth_out = pd.DataFrame([
    {"depth": d,
     "precision": f"{r['precision']:.1%}", "recall": f"{r['recall']:.1%}",
     "f1":        f"{r['f1']:.3f}",        "auc":    f"{r['auc']:.3f}",
     "cv_f1":     f"{r['cv_f1']:.3f}",
     "selected":  "YES" if d == best_depth else ""}
    for d, r in results.items()
])
rules_out = rules_df[["rule_conditions","samples","first_pass_n",
                       "approval_rate_pct","action"]].copy()
auto_out  = (
    auto_df[["rule_conditions","samples","first_pass_n","approval_rate_pct"]]
    if len(auto_df) > 0
    else pd.DataFrame({"note": ["No leaves met threshold — lower APPROVAL_THRESHOLD"]})
)

with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as w:
    metrics_out.to_excel(w, sheet_name="Metrics",             index=False)
    depth_out.to_excel(  w, sheet_name="Depth_Comparison",    index=False)
    fi.to_excel(         w, sheet_name="Feature_Importance",   index=False)
    rules_out.to_excel(  w, sheet_name="All_Leaf_Rules",       index=False)
    auto_out.to_excel(   w, sheet_name="AutoApprove_Rules",    index=False)
    model_df.to_excel(   w, sheet_name="Full_Data_Predictions",index=False)

print("   Done — 6 sheets written.")
print(f"\nCharts : ./{OUTPUT_DIR}/")
print(f"Excel  : {EXCEL_PATH}")
print()
