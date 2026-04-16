"""
Diagnostic script — run this FIRST before decision_tree_model.py
It will tell us exactly why min_samples_leaf is being ignored.
"""

import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.tree import _tree

DATA_PATH = "your_estimates_file.csv"   # <- same path as main script

# ── Load ──────────────────────────────────────────────────────
df = pd.read_csv(DATA_PATH, low_memory=False)
print(f"Loaded: {len(df):,} rows\n")

# ── Target ────────────────────────────────────────────────────
df["first_pass"] = (df["rvsn_nbr"] == 1).astype(int)

# ── Vendor score ──────────────────────────────────────────────
global_mean = df["first_pass"].mean()
vstats = df.groupby("vr_vndr_id")["first_pass"].agg(
    vrate="mean", vcnt="count").reset_index()
vstats["vendor_score"] = (
    (vstats["vrate"] * vstats["vcnt"] + global_mean * 20)
    / (vstats["vcnt"] + 20)
).round(2)
df = df.merge(vstats[["vr_vndr_id", "vendor_score"]],
              on="vr_vndr_id", how="left")

# ── Pick just 2 features to keep it simple ───────────────────
FEATURES = ["vendor_score", "line_item_count"]

model_df = df[FEATURES + ["first_pass"]].dropna().reset_index(drop=True)

print("=== DTYPE CHECK ===")
for f in FEATURES:
    print(f"  {f}: {model_df[f].dtype}  |  "
          f"sample values: {model_df[f].head(5).tolist()}")

# Force numeric
for f in FEATURES:
    model_df[f] = pd.to_numeric(model_df[f], errors="coerce")
model_df.dropna(inplace=True)
model_df.reset_index(drop=True, inplace=True)

print("\n=== AFTER COERCION ===")
for f in FEATURES:
    print(f"  {f}: {model_df[f].dtype}  |  "
          f"unique values: {model_df[f].nunique()}")

print(f"\n  Total rows: {len(model_df):,}")
print(f"  first_pass=1: {model_df['first_pass'].sum():,}  "
      f"({model_df['first_pass'].mean():.1%})")

# ── Build X, y explicitly ─────────────────────────────────────
X = model_df[FEATURES].values.astype(np.float64)
y = model_df["first_pass"].values.astype(np.int32)

print(f"\n  X dtype: {X.dtype}  shape: {X.shape}")
print(f"  y dtype: {y.dtype}  shape: {y.shape}")
print(f"  X has NaN: {np.isnan(X).any()}")
print(f"  X has inf: {np.isinf(X).any()}")

# ── Train a depth-3 tree with MIN_LEAF=500 ────────────────────
# If this still produces n=1 leaves something very unexpected is happening
MIN_LEAF = 500
print(f"\n=== TRAINING depth=3 min_samples_leaf={MIN_LEAF} ===")

clf = DecisionTreeClassifier(
    max_depth=3,
    min_samples_leaf=MIN_LEAF,
    min_samples_split=MIN_LEAF * 2,
    random_state=42
)
clf.fit(X, y)

print(export_text(clf, feature_names=FEATURES))

# ── Check every leaf ──────────────────────────────────────────
t_   = clf.tree_
left = t_.children_left
right= t_.children_right

print("=== LEAF CHECK ===")
all_good = True
for nid in range(t_.node_count):
    if left[nid] == _tree.TREE_LEAF:
        cnts  = t_.value[nid][0]
        total = int(cnts.sum())
        c1    = int(cnts[1]) if len(cnts) > 1 else 0
        rate  = c1 / total if total > 0 else 0
        print(f"  node {nid:>3}  n={total:>6,}  "
              f"first_pass={c1:>6,}  rate={rate:.1%}")
        if total < MIN_LEAF:
            all_good = False
            print(f"  *** WARNING: leaf has {total} samples "
                  f"< MIN_LEAF={MIN_LEAF}. Something is wrong.")

if all_good:
    print(f"\n  All leaves have >= {MIN_LEAF} samples. Tree is working correctly.")
    print("  The main script should now also work — re-run decision_tree_model.py")
else:
    print(f"\n  min_samples_leaf is being ignored.")
    print(f"  sklearn version: ", end="")
    import sklearn; print(sklearn.__version__)
    print(f"  Try: pip install --upgrade scikit-learn")
