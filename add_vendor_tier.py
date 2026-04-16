"""
Add vendor_tier_trusted column to original Excel file.

Steps:
  1. Reads your Excel file
  2. Computes per-vendor approval rate from rvsn_nbr
  3. Classifies each vendor as trusted (top quartile) or not
  4. Adds vendor_tier_trusted column (values: "trusted" / "not_trusted" / "insufficient_history")
  5. Saves as a new Excel file

Update INPUT_PATH and OUTPUT_PATH below before running.
"""

import pandas as pd
import numpy as np

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_PATH  = "your_input_file.xlsx"      # ← your original Excel file
OUTPUT_PATH = "output_with_vendor_tier.xlsx"  # ← where to save the result
SHEET_NAME  = 0                           # ← 0 = first sheet, or use sheet name e.g. "Sheet1"
VENDOR_MIN_ESTIMATES = 10                 # minimum estimates before a vendor can be "trusted"
# ─────────────────────────────────────────────────────────────────────────────

print(f"Reading: {INPUT_PATH}")
df = pd.read_excel(INPUT_PATH, sheet_name=SHEET_NAME)
print(f"Loaded {len(df):,} rows, {df.shape[1]} columns")

# ── Step 1: build first_pass label from rvsn_nbr ─────────────────────────────
df["_first_pass"] = (df["rvsn_nbr"] == 1).astype(int)

# ── Step 2: compute per-vendor approval rate ──────────────────────────────────
vendor_stats = (
    df.groupby("vr_vndr_id")["_first_pass"]
    .agg(vendor_approval_rate="mean", vendor_est_count="count")
    .reset_index()
)

# ── Step 3: find the 75th percentile cutoff (trusted threshold) ───────────────
eligible_rates = vendor_stats.loc[
    vendor_stats["vendor_est_count"] >= VENDOR_MIN_ESTIMATES, "vendor_approval_rate"
]
trusted_cutoff = eligible_rates.quantile(0.75)
print(f"Trusted threshold (75th percentile): {trusted_cutoff:.4f}  ({trusted_cutoff:.1%})")

# ── Step 4: assign tier ───────────────────────────────────────────────────────
def assign_tier(row):
    if row["vendor_est_count"] < VENDOR_MIN_ESTIMATES:
        return "insufficient_history"
    return "trusted" if row["vendor_approval_rate"] >= trusted_cutoff else "not_trusted"

vendor_stats["vendor_tier_trusted"] = vendor_stats.apply(assign_tier, axis=1)

# ── Step 5: merge back into main dataframe ────────────────────────────────────
df = df.merge(
    vendor_stats[["vr_vndr_id", "vendor_tier_trusted"]],
    on="vr_vndr_id",
    how="left"
)

# Drop the temporary helper column
df.drop(columns=["_first_pass"], inplace=True)

# ── Summary ───────────────────────────────────────────────────────────────────
counts = df["vendor_tier_trusted"].value_counts()
print("\nvendor_tier_trusted distribution:")
for tier, cnt in counts.items():
    print(f"  {tier:<25} {cnt:>6,}  ({cnt/len(df):.1%})")

# ── Step 6: save ──────────────────────────────────────────────────────────────
print(f"\nSaving to: {OUTPUT_PATH}")
df.to_excel(OUTPUT_PATH, index=False)
print("Done.")
