"""
Decision Tree Auto-Approval Model
===================================
Target  : first_pass = 1 if rvsn_nbr == 1, else 0
Approach: Shallow decision tree (max_depth 3-5) trained on historical estimates.
          Outputs human-readable IF/THEN rules, feature importances,
          performance metrics, and saves all charts + results to Excel.

Update DATA_PATH before running.
"""

import pandas as pd
import numpy as np
import warnings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path

warnings.filterwarnings("ignore")

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_PATH   = "your_estimates_file.csv"
OUTPUT_DIR  = "dt_output"
EXCEL_PATH  = "decision_tree_results.xlsx"

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# ── STYLE ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor" : "#0d1117",
    "axes.facecolor"   : "#161b22",
    "axes.edgecolor"   : "#2a3444",
    "axes.labelcolor"  : "#7a8899",
    "axes.titlecolor"  : "#f0f4f8",
    "text.color"       : "#f0f4f8",
    "xtick.color"      : "#7a8899",
    "ytick.color"      : "#7a8899",
    "grid.color"       : "#2a3444",
    "grid.linestyle"   : "--",
    "grid.alpha"       : 0.5,
    "font.family"      : "monospace",
    "figure.dpi"       : 130,
})

GOLD   = "#e0a84b"
GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
MUTED  = "#7a8899"
WHITE  = "#f0f4f8"
AMBER  = "#d29922"


# ════════════════════════════════════════════════════════════════
# 1.  LOAD & CLEAN
# ════════════════════════════════════════════════════════════════
print("── 1. Loading data ──────────────────────")
df = pd.read_csv(DATA_PATH, low_memory=False)
print(f"   Rows: {len(df):,}   Columns: {df.shape[1]}")

# Fix negative time_to_approve
if "time_to_approve_days" in df.columns:
    df["time_to_approve_days"] = df["time_to_approve_days"].clip(lower=0)

# Parse dates for feature engineering
for col in ["est_recv_dte", "apprv_dte"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")


# ════════════════════════════════════════════════════════════════
# 2.  TARGET VARIABLE
# ════════════════════════════════════════════════════════════════
print("\n── 2. Target variable ───────────────────")
df["first_pass"] = (df["rvsn_nbr"] == 1).astype(int)
print(f"   First-pass (1): {df['first_pass'].sum():,}  ({df['first_pass'].mean():.1%})")
print(f"   Revised    (0): {(df['first_pass']==0).sum():,}  ({1-df['first_pass'].mean():.1%})")


# ════════════════════════════════════════════════════════════════
# 3.  FEATURE ENGINEERING
# ════════════════════════════════════════════════════════════════
print("\n── 3. Feature engineering ───────────────")

# Vendor trust score (approval rate per vendor, shrunk toward mean)
vendor_stats = (
    df.groupby("vr_vndr_id")["first_pass"]
    .agg(vendor_rate="mean", vendor_count="count")
    .reset_index()
)
# Bayesian shrinkage: pull small-sample vendors toward global mean
global_mean = df["first_pass"].mean()
vendor_stats["vendor_trust_score"] = (
    (vendor_stats["vendor_rate"] * vendor_stats["vendor_count"] + global_mean * 10)
    / (vendor_stats["vendor_count"] + 10)
)
df = df.merge(vendor_stats[["vr_vndr_id","vendor_trust_score","vendor_count"]],
              on="vr_vndr_id", how="left")

# Cost per labour hour
df["cost_per_lbr_hr"] = np.where(
    df["lbr_hr_qty"] > 0,
    df["est_tot_amt"] / df["lbr_hr_qty"],
    0
)

# Vehicle age
if "veh_yr" in df.columns:
    df["veh_age"] = pd.Timestamp.now().year - df["veh_yr"]

# Month of estimate (seasonality)
if "est_recv_dte" in df.columns:
    df["est_month"] = df["est_recv_dte"].dt.month.fillna(0).astype(int)

# Parts-to-total ratio proxy (if parts data available via discount cols)
if "dmstc_part_disc_amt" in df.columns and "frn_part_disc_amt" in df.columns:
    df["total_part_disc"] = df["dmstc_part_disc_amt"].fillna(0) + df["frn_part_disc_amt"].fillna(0)

print("   Features engineered: vendor_trust_score, cost_per_lbr_hr, veh_age, est_month")


# ════════════════════════════════════════════════════════════════
# 4.  FEATURE SELECTION
# ════════════════════════════════════════════════════════════════
FEATURE_CANDIDATES = [
    "est_tot_amt",
    "lbr_hr_qty",
    "line_item_count",
    "vendor_trust_score",
    "cost_per_lbr_hr",
    "negative_or_null_est_ind",
    "est_disc_ind",
    "veh_age",
    "est_month",
    "total_part_disc",
]

# Keep only features that exist in the dataframe
FEATURES = [f for f in FEATURE_CANDIDATES if f in df.columns]
print(f"\n   Features used: {FEATURES}")

# Drop rows with any NaN in features or target
model_df = df[FEATURES + ["first_pass"]].dropna()
print(f"   Rows after dropping NaNs: {len(model_df):,}")

X = model_df[FEATURES].values
y = model_df["first_pass"].values


# ════════════════════════════════════════════════════════════════
# 5.  TRAIN / TEST SPLIT
# ════════════════════════════════════════════════════════════════
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report, roc_auc_score,
    roc_curve, precision_recall_curve
)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42, stratify=y
)
print(f"\n── 4. Train/test split ──────────────────")
print(f"   Train: {len(X_train):,}   Test: {len(X_test):,}")


# ════════════════════════════════════════════════════════════════
# 6.  TRAIN TREES AT MULTIPLE DEPTHS — PICK BEST
# ════════════════════════════════════════════════════════════════
# NOTE ON CLASS_WEIGHT:
# We use None (no reweighting) because the dataset is only mildly
# imbalanced (~57% first-pass). Using "balanced" over-penalises the
# majority class and pushes ALL leaves to predict class 0 — which
# is why auto-approve rules were empty in the previous run.
# APPROVAL_THRESHOLD controls the precision/recall tradeoff:
#   raise it (e.g. 0.75) → fewer but higher-confidence auto-approvals
#   lower it  (e.g. 0.55) → more coverage, slightly lower precision

APPROVAL_THRESHOLD = 0.65

print("\n── 5. Training trees (depth 3–5) ────────")
print(f"   Auto-approve threshold : {APPROVAL_THRESHOLD:.0%} leaf approval rate\n")

results_by_depth = {}
for depth in [3, 4, 5]:
    clf = DecisionTreeClassifier(
        max_depth=depth,
        min_samples_leaf=100,
        class_weight=None,
        criterion="gini",
        random_state=42
    )
    clf.fit(X_train, y_train)
    y_prob  = clf.predict_proba(X_test)[:, 1]
    y_pred  = (y_prob >= APPROVAL_THRESHOLD).astype(int)
    prec    = precision_score(y_test, y_pred, zero_division=0)
    rec     = recall_score(y_test, y_pred, zero_division=0)
    f1      = f1_score(y_test, y_pred, zero_division=0)
    auc     = roc_auc_score(y_test, y_prob)
    acc     = accuracy_score(y_test, y_pred)
    cv_f1   = cross_val_score(clf, X, y, cv=5, scoring="f1").mean()
    results_by_depth[depth] = {
        "clf": clf, "y_pred": y_pred, "y_prob": y_prob,
        "precision": prec, "recall": rec, "f1": f1,
        "auc": auc, "accuracy": acc, "cv_f1": cv_f1
    }
    print(f"   Depth {depth}:  precision={prec:.3f}  recall={rec:.3f}  "
          f"f1={f1:.3f}  AUC={auc:.3f}  CV-F1={cv_f1:.3f}")

# Select best by F1
best_depth = max(results_by_depth, key=lambda d: results_by_depth[d]["f1"])
best       = results_by_depth[best_depth]
clf        = best["clf"]
y_pred     = best["y_pred"]
y_prob     = best["y_prob"]

print(f"\n   Best depth: {best_depth}  (F1 = {best['f1']:.3f})")


# ════════════════════════════════════════════════════════════════
# 7.  METRICS
# ════════════════════════════════════════════════════════════════
print("\n── 6. Test set metrics ──────────────────")
cm = confusion_matrix(y_test, y_pred)
TP, FP, FN, TN = cm[1,1], cm[0,1], cm[1,0], cm[0,0]

print(f"""
   Accuracy    : {best['accuracy']:.1%}
   Precision   : {best['precision']:.1%}
   Recall      : {best['recall']:.1%}
   F1          : {best['f1']:.3f}
   ROC-AUC     : {best['auc']:.3f}
   CV F1 (5-fold): {best['cv_f1']:.3f}

   Confusion matrix (test set):
            Predicted 0   Predicted 1
   Actual 0     TN={TN:>5}     FP={FP:>5}
   Actual 1     FN={FN:>5}     TP={TP:>5}
""")


# ════════════════════════════════════════════════════════════════
# 8.  FEATURE IMPORTANCE
# ════════════════════════════════════════════════════════════════
fi = pd.DataFrame({
    "feature"    : FEATURES,
    "importance" : clf.feature_importances_
}).sort_values("importance", ascending=False)
print("── 7. Feature importances ───────────────")
print(fi.to_string(index=False))


# ════════════════════════════════════════════════════════════════
# 9.  EXTRACT HUMAN-READABLE RULES
# ════════════════════════════════════════════════════════════════
print("\n── 8. Decision tree rules ───────────────")
rules_text = export_text(clf, feature_names=FEATURES)
print(rules_text)

# ── Extract leaf-level rules as structured table ──────────────
from sklearn.tree import _tree

def extract_rules(tree, feature_names):
    """Walk the tree and extract one rule per leaf.
    Uses tree_.children_left / children_right (sklearn's actual node arrays)
    instead of the broken node*2+1 shortcut which assumes a perfect binary tree.
    """
    tree_   = tree.tree_
    left    = tree_.children_left    # left child index for each node
    right   = tree_.children_right   # right child index for each node
    feature = tree_.feature          # split feature index (-2 = leaf)
    threshold = tree_.threshold      # split threshold
    value   = tree_.value            # sample counts [node, 1, n_classes]
    rules   = []

    def recurse(node, conditions):
        if left[node] == _tree.TREE_LEAF:
            # leaf node — record the rule
            counts     = value[node][0]
            total      = int(counts.sum())
            class_1    = int(counts[1]) if len(counts) > 1 else 0
            approval_r = class_1 / total if total > 0 else 0
            rules.append({
                "conditions"   : " AND ".join(conditions) if conditions else "ALL",
                "samples"      : total,
                "first_pass_n" : class_1,
                "approval_rate" : round(approval_r * 100, 1),
                "prediction"   : 1 if approval_r >= APPROVAL_THRESHOLD else 0,
                "leaf_node"    : node,
            })
        else:
            fname  = feature_names[feature[node]]
            thresh = round(float(threshold[node]), 4)
            recurse(left[node],  conditions + [f"{fname} <= {thresh}"])
            recurse(right[node], conditions + [f"{fname} >  {thresh}"])

    recurse(0, [])
    return pd.DataFrame(rules)

rules_df = extract_rules(clf, FEATURES)
rules_df = rules_df.sort_values("approval_rate", ascending=False)

print("\n── Leaf rules sorted by approval rate ───")
print(rules_df[["conditions","samples","approval_rate","prediction"]].to_string(index=False))

# Separate auto-approve vs reject leaves
auto_approve_rules = rules_df[rules_df["prediction"] == 1].reset_index(drop=True)
reject_rules       = rules_df[rules_df["prediction"] == 0].reset_index(drop=True)

print(f"\n   AUTO-APPROVE leaves : {len(auto_approve_rules)}")
print(f"   REJECT leaves       : {len(reject_rules)}")

print("\n══════════════════════════════════════════")
print("   FINAL AUTO-APPROVAL RULES")
print("══════════════════════════════════════════")
for i, row in auto_approve_rules.iterrows():
    print(f"\n   Rule {i+1}  (approval rate: {row['approval_rate']}%  |  samples: {row['samples']:,})")
    print(f"   IF  {row['conditions']}")
    print(f"   → AUTO-APPROVE")
print("══════════════════════════════════════════\n")


# ════════════════════════════════════════════════════════════════
# 10.  CHARTS
# ════════════════════════════════════════════════════════════════
print("── 9. Generating charts ─────────────────")

# ── Chart 1: Feature Importance ──────────────────────────────
fig, ax = plt.subplots(figsize=(9, 4.5))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")

colors = [GOLD if i == 0 else BLUE for i in range(len(fi))]
bars = ax.barh(fi["feature"][::-1], fi["importance"][::-1] * 100,
               color=colors[::-1], height=0.6, edgecolor="none")

for bar, val in zip(bars, fi["importance"][::-1] * 100):
    ax.text(val + 0.3, bar.get_y() + bar.get_height()/2,
            f"{val:.1f}%", va="center", ha="left", fontsize=9, color=WHITE)

ax.set_xlabel("Feature importance (%)", color=MUTED, fontsize=10)
ax.set_title("Feature importance — decision tree", color=WHITE, fontsize=12, pad=12)
ax.grid(axis="x", color="#2a3444", linestyle="--", alpha=0.5)
ax.tick_params(axis="y", labelsize=10, labelcolor=WHITE)
ax.spines[:].set_visible(False)
ax.set_xlim(0, fi["importance"].max() * 110)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/01_feature_importance.png", dpi=130, bbox_inches="tight",
            facecolor="#0d1117")
plt.close()
print("   Saved: 01_feature_importance.png")


# ── Chart 2: Depth Comparison ────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")

depths  = list(results_by_depth.keys())
metrics = ["precision", "recall", "f1", "auc"]
colors_m = [GREEN, GOLD, BLUE, AMBER]
x = np.arange(len(depths))
w = 0.2

for i, (m, c) in enumerate(zip(metrics, colors_m)):
    vals = [results_by_depth[d][m] for d in depths]
    bars = ax.bar(x + i*w, [v*100 for v in vals], w, label=m.upper(),
                  color=c, alpha=0.85, edgecolor="none")
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{val*100:.1f}", ha="center", va="bottom", fontsize=8, color=c)

ax.set_xticks(x + w*1.5)
ax.set_xticklabels([f"Depth {d}" for d in depths], fontsize=10)
ax.set_ylabel("Score (%)", color=MUTED)
ax.set_title("Performance by tree depth", color=WHITE, fontsize=12, pad=12)
ax.set_ylim(0, 105)
ax.legend(frameon=False, labelcolor=WHITE, fontsize=9)
ax.grid(axis="y", color="#2a3444", linestyle="--", alpha=0.5)
ax.spines[:].set_visible(False)
ax.axvline(x=depths.index(best_depth) + w*1.5, color=GOLD, linestyle="--",
           alpha=0.4, linewidth=1)
ax.text(depths.index(best_depth) + w*1.5 + 0.05, 100,
        "  selected", color=GOLD, fontsize=9)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/02_depth_comparison.png", dpi=130, bbox_inches="tight",
            facecolor="#0d1117")
plt.close()
print("   Saved: 02_depth_comparison.png")


# ── Chart 3: Confusion Matrix ────────────────────────────────
fig, ax = plt.subplots(figsize=(5.5, 4.5))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")

cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
cmap    = LinearSegmentedColormap.from_list("custom", ["#161b22", "#e0a84b"])
im      = ax.imshow(cm_norm, cmap=cmap, aspect="auto")

labels   = [["TN", "FP"], ["FN", "TP"]]
for i in range(2):
    for j in range(2):
        color = WHITE if cm_norm[i,j] < 0.5 else "#0d1117"
        ax.text(j, i, f"{labels[i][j]}\n{cm[i,j]:,}\n({cm_norm[i,j]:.1%})",
                ha="center", va="center", fontsize=11, color=color, fontweight="bold")

ax.set_xticks([0,1]); ax.set_yticks([0,1])
ax.set_xticklabels(["Predicted: No auto", "Predicted: Auto"], fontsize=9)
ax.set_yticklabels(["Actual: Revised", "Actual: First-pass"], fontsize=9)
ax.set_title(f"Confusion matrix — depth {best_depth} tree (test set)", color=WHITE, fontsize=11, pad=12)
ax.spines[:].set_visible(False)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/03_confusion_matrix.png", dpi=130, bbox_inches="tight",
            facecolor="#0d1117")
plt.close()
print("   Saved: 03_confusion_matrix.png")


# ── Chart 4: ROC Curve ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(6, 5))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")

fpr, tpr, _ = roc_curve(y_test, y_prob)
ax.plot(fpr, tpr, color=GOLD, linewidth=2,
        label=f"Decision Tree (AUC = {best['auc']:.3f})")
ax.plot([0,1], [0,1], color=MUTED, linestyle="--", linewidth=1, label="Random (AUC = 0.500)")
ax.fill_between(fpr, tpr, alpha=0.08, color=GOLD)

ax.set_xlabel("False Positive Rate", color=MUTED, fontsize=10)
ax.set_ylabel("True Positive Rate", color=MUTED, fontsize=10)
ax.set_title("ROC Curve", color=WHITE, fontsize=12, pad=12)
ax.legend(frameon=False, labelcolor=WHITE, fontsize=10)
ax.grid(color="#2a3444", linestyle="--", alpha=0.5)
ax.spines[:].set_visible(False)
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/04_roc_curve.png", dpi=130, bbox_inches="tight",
            facecolor="#0d1117")
plt.close()
print("   Saved: 04_roc_curve.png")


# ── Chart 5: Precision-Recall Curve ─────────────────────────
fig, ax = plt.subplots(figsize=(6, 5))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")

prec_c, rec_c, thresholds = precision_recall_curve(y_test, y_prob)
ax.plot(rec_c, prec_c, color=BLUE, linewidth=2)
ax.fill_between(rec_c, prec_c, alpha=0.08, color=BLUE)
ax.axhline(y=best["precision"], color=GOLD, linestyle="--", alpha=0.6, linewidth=1)
ax.axvline(x=best["recall"],    color=GREEN, linestyle="--", alpha=0.6, linewidth=1)
ax.scatter([best["recall"]], [best["precision"]], color=GOLD, zorder=5, s=60,
           label=f"Operating point\n(P={best['precision']:.2f}, R={best['recall']:.2f})")

ax.set_xlabel("Recall", color=MUTED, fontsize=10)
ax.set_ylabel("Precision", color=MUTED, fontsize=10)
ax.set_title("Precision–Recall Curve", color=WHITE, fontsize=12, pad=12)
ax.legend(frameon=False, labelcolor=WHITE, fontsize=9)
ax.grid(color="#2a3444", linestyle="--", alpha=0.5)
ax.spines[:].set_visible(False)
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/05_precision_recall.png", dpi=130, bbox_inches="tight",
            facecolor="#0d1117")
plt.close()
print("   Saved: 05_precision_recall.png")


# ── Chart 6: Leaf approval rates ────────────────────────────
fig, ax = plt.subplots(figsize=(10, max(4, len(rules_df) * 0.5 + 1.5)))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")

sorted_rules = rules_df.sort_values("approval_rate")
colors_bar   = [GREEN if p == 1 else RED for p in sorted_rules["prediction"]]
short_labels = [f"Leaf {i+1}  ({row['samples']:,} est.)"
                for i, (_, row) in enumerate(sorted_rules.iterrows())]

bars = ax.barh(range(len(sorted_rules)), sorted_rules["approval_rate"],
               color=colors_bar, height=0.65, edgecolor="none")

for bar, val in zip(bars, sorted_rules["approval_rate"]):
    ax.text(val + 0.5, bar.get_y() + bar.get_height()/2,
            f"{val:.1f}%", va="center", ha="left", fontsize=9, color=WHITE)

ax.set_yticks(range(len(sorted_rules)))
ax.set_yticklabels(short_labels, fontsize=8)
ax.set_xlabel("First-pass approval rate in leaf (%)", color=MUTED)
ax.set_title(f"Approval rate per decision tree leaf — depth {best_depth}", color=WHITE,
             fontsize=12, pad=12)
ax.axvline(50, color=MUTED, linestyle="--", alpha=0.4, linewidth=1)
ax.text(50.5, -0.6, "50% threshold", color=MUTED, fontsize=8)
ax.set_xlim(0, 110)
ax.grid(axis="x", color="#2a3444", linestyle="--", alpha=0.5)
ax.spines[:].set_visible(False)

legend_patches = [
    mpatches.Patch(color=GREEN, label="AUTO-APPROVE (prediction = 1)"),
    mpatches.Patch(color=RED,   label="HOLD FOR REVIEW (prediction = 0)"),
]
ax.legend(handles=legend_patches, frameon=False, labelcolor=WHITE, fontsize=9,
          loc="lower right")
plt.tight_layout(pad=1.5)
plt.savefig(f"{OUTPUT_DIR}/06_leaf_approval_rates.png", dpi=130, bbox_inches="tight",
            facecolor="#0d1117")
plt.close()
print("   Saved: 06_leaf_approval_rates.png")


# ── Chart 7: Tree visualisation ──────────────────────────────
try:
    from sklearn.tree import plot_tree
    fig, ax = plt.subplots(figsize=(max(14, best_depth * 5), max(7, best_depth * 2.5)))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    plot_tree(
        clf, feature_names=FEATURES,
        class_names=["Revised", "First-pass"],
        filled=True, rounded=True, fontsize=7,
        impurity=False, proportion=True, ax=ax
    )
    ax.set_title(f"Decision tree structure — depth {best_depth}", color=WHITE,
                 fontsize=13, pad=14)
    plt.tight_layout(pad=1.5)
    plt.savefig(f"{OUTPUT_DIR}/07_tree_structure.png", dpi=110, bbox_inches="tight",
                facecolor="#0d1117")
    plt.close()
    print("   Saved: 07_tree_structure.png")
except Exception as e:
    print(f"   Tree viz skipped: {e}")


# ════════════════════════════════════════════════════════════════
# 11.  APPLY TREE PREDICTIONS TO FULL DATASET
# ════════════════════════════════════════════════════════════════
print("\n── 10. Applying model to full dataset ───")

full_X = model_df[FEATURES].values
model_df = model_df.copy()
model_df["dt_prediction"]   = (clf.predict_proba(full_X)[:, 1] >= APPROVAL_THRESHOLD).astype(int)
model_df["dt_probability"]  = clf.predict_proba(full_X)[:, 1]

full_prec = precision_score(model_df["first_pass"], model_df["dt_prediction"])
full_rec  = recall_score(model_df["first_pass"],    model_df["dt_prediction"])
full_acc  = accuracy_score(model_df["first_pass"],  model_df["dt_prediction"])
print(f"   Full dataset — Precision: {full_prec:.1%}  Recall: {full_rec:.1%}  Accuracy: {full_acc:.1%}")
print(f"   Auto-approved by model : {model_df['dt_prediction'].sum():,}  "
      f"({model_df['dt_prediction'].mean():.1%})")


# ════════════════════════════════════════════════════════════════
# 12.  EXPORT TO EXCEL
# ════════════════════════════════════════════════════════════════
print(f"\n── 11. Writing Excel → {EXCEL_PATH} ─────")

metrics_df = pd.DataFrame({
    "Metric": [
        "Best tree depth",
        "Test set — Accuracy",
        "Test set — Precision",
        "Test set — Recall",
        "Test set — F1",
        "Test set — ROC AUC",
        "5-fold CV F1",
        "TP (correct auto-approvals)",
        "FP (wrong auto-approvals)",
        "TN (correctly held back)",
        "FN (missed auto-approvals)",
        "Full dataset auto-approved",
        "Full dataset auto-approved %",
    ],
    "Value": [
        best_depth,
        f"{best['accuracy']:.1%}",
        f"{best['precision']:.1%}",
        f"{best['recall']:.1%}",
        f"{best['f1']:.3f}",
        f"{best['auc']:.3f}",
        f"{best['cv_f1']:.3f}",
        TP, FP, TN, FN,
        int(model_df["dt_prediction"].sum()),
        f"{model_df['dt_prediction'].mean():.1%}",
    ]
})

depth_df = pd.DataFrame([
    {
        "depth"     : d,
        "precision" : f"{r['precision']:.1%}",
        "recall"    : f"{r['recall']:.1%}",
        "f1"        : f"{r['f1']:.3f}",
        "auc"       : f"{r['auc']:.3f}",
        "cv_f1"     : f"{r['cv_f1']:.3f}",
        "selected"  : "YES" if d == best_depth else "",
    }
    for d, r in results_by_depth.items()
])

rules_export = rules_df[[
    "conditions", "samples", "first_pass_n", "approval_rate", "prediction"
]].copy()
rules_export["action"] = rules_export["prediction"].map(
    {1: "AUTO-APPROVE", 0: "MANUAL REVIEW"}
)

with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
    metrics_df.to_excel(writer, sheet_name="Metrics", index=False)
    depth_df.to_excel(writer, sheet_name="Depth_Comparison", index=False)
    fi.to_excel(writer, sheet_name="Feature_Importance", index=False)
    rules_export.to_excel(writer, sheet_name="All_Leaf_Rules", index=False)
    auto_approve_rules[["conditions","samples","approval_rate"]]\
        .to_excel(writer, sheet_name="AutoApprove_Rules", index=False)
    model_df.to_excel(writer, sheet_name="Full_Data_Predictions", index=False)

print(f"   Sheets: Metrics, Depth_Comparison, Feature_Importance,")
print(f"           All_Leaf_Rules, AutoApprove_Rules, Full_Data_Predictions")


# ════════════════════════════════════════════════════════════════
# 13.  PRINT FINAL CLEAN RULES SUMMARY
# ════════════════════════════════════════════════════════════════
print("""
╔══════════════════════════════════════════════════════════════╗
║              DECISION TREE — FINAL RULES SUMMARY            ║
╚══════════════════════════════════════════════════════════════╝
""")
print(f"  Model     : Decision Tree, max_depth={best_depth}, min_samples_leaf=150")
print(f"  Target    : first_pass = 1 (rvsn_nbr == 1)")
print(f"  Precision : {best['precision']:.1%}   Recall : {best['recall']:.1%}")
print(f"  F1        : {best['f1']:.3f}      AUC    : {best['auc']:.3f}")
print()
print("  ── AUTO-APPROVE rules (prediction = 1) ──────────────")
for i, row in auto_approve_rules.iterrows():
    print(f"""
  Rule {i+1}
  ┌─ Condition ──────────────────────────────────────────────
  │  {row['conditions'].replace(' AND ', chr(10) + '  │  AND ')}
  ├─ Performance ────────────────────────────────────────────
  │  Approval rate : {row['approval_rate']}%
  │  Estimates     : {row['samples']:,}
  └─ Action ─────────────────────────────────────────────────
     → AUTO-APPROVE""")

print("""
  ── MANUAL REVIEW rules (prediction = 0) ──────────────────
  All estimates NOT matching the above rules → MANUAL REVIEW
""")
print("  Charts saved to:", OUTPUT_DIR)
print("  Excel  saved to:", EXCEL_PATH)
print()
