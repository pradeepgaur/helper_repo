"""
Add vendor_tier column (all 4 categories) to original Excel file.

Tiers:
  trusted             — top 25% of vendors by first-pass approval rate
  above_avg           — 50th–75th percentile
  below_avg           — 25th–50th percentile
  low                 — bottom 25%
  insufficient_history— fewer than VENDOR_MIN_ESTIMATES estimates

Update INPUT_PATH and OUTPUT_PATH below before running.
"""

import pandas as pd
import numpy as np

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_PATH  = "your_input_file.xlsx"         # ← your original Excel file
OUTPUT_PATH = "output_with_vendor_tier.xlsx" # ← where to save the result
SHEET_NAME  = 0                              # ← 0 = first sheet, or "Sheet1" etc.
VENDOR_MIN_ESTIMATES = 10                    # minimum estimates to qualify for tiering
# ─────────────────────────────────────────────────────────────────────────────

print(f"Reading: {INPUT_PATH}")
df = pd.read_excel(INPUT_PATH, sheet_name=SHEET_NAME, engine="openpyxl")
print(f"Loaded {len(df):,} rows, {df.shape[1]} columns")

# ── Step 1: build first_pass label ───────────────────────────────────────────
df["_first_pass"] = (df["rvsn_nbr"] == 1).astype(int)

# ── Step 2: compute per-vendor approval rate ──────────────────────────────────
vendor_stats = (
    df.groupby("vr_vndr_id")["_first_pass"]
    .agg(vendor_approval_rate="mean", vendor_est_count="count")
    .reset_index()
)

# ── Step 3: compute quartile cutoffs from eligible vendors only ───────────────
eligible = vendor_stats["vendor_est_count"] >= VENDOR_MIN_ESTIMATES
eligible_rates = vendor_stats.loc[eligible, "vendor_approval_rate"]

q25 = eligible_rates.quantile(0.25)
q50 = eligible_rates.quantile(0.50)
q75 = eligible_rates.quantile(0.75)

print(f"\nVendor approval rate quartile cutoffs:")
print(f"  25th percentile (low / below_avg boundary)   : {q25:.4f}  ({q25:.1%})")
print(f"  50th percentile (below_avg / above_avg boundary): {q50:.4f}  ({q50:.1%})")
print(f"  75th percentile (above_avg / trusted boundary)  : {q75:.4f}  ({q75:.1%})")

# ── Step 4: assign tier ───────────────────────────────────────────────────────
def assign_tier(row):
    if row["vendor_est_count"] < VENDOR_MIN_ESTIMATES:
        return "insufficient_history"
    rate = row["vendor_approval_rate"]
    if rate >= q75:
        return "trusted"
    elif rate >= q50:
        return "above_avg"
    elif rate >= q25:
        return "below_avg"
    else:
        return "low"

vendor_stats["vendor_tier"] = vendor_stats.apply(assign_tier, axis=1)

# ── Step 5: merge back ────────────────────────────────────────────────────────
df = df.merge(
    vendor_stats[["vr_vndr_id", "vendor_approval_rate", "vendor_tier"]],
    on="vr_vndr_id",
    how="left"
)

df.drop(columns=["_first_pass"], inplace=True)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nvendor_tier distribution:")
tier_order = ["trusted", "above_avg", "below_avg", "low", "insufficient_history"]
for tier in tier_order:
    cnt = (df["vendor_tier"] == tier).sum()
    avg = df.loc[df["vendor_tier"] == tier, "vendor_approval_rate"].mean()
    print(f"  {tier:<25} {cnt:>6,} estimates   avg approval rate: {avg:.1%}")

# ── Step 6: save ──────────────────────────────────────────────────────────────
print(f"\nSaving to: {OUTPUT_PATH}")
df.to_excel(OUTPUT_PATH, index=False, engine="openpyxl")
print("Done.")
