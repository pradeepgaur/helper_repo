# Step 1: Compute vendor approval rates (vendors with >= 10 estimates only)
vendor_rates = (
    df.groupby("vr_vndr_id")["first_pass"]
    .agg(
        vendor_approval_rate="mean",
        vendor_est_count="count"
    )
    .reset_index()
    .query("vendor_est_count >= 10")  # mirrors WHERE total_estimates >= 10
)

# Step 2: Explicitly compute percentile thresholds (mirrors percentiles CTE)
q25 = vendor_rates["vendor_approval_rate"].quantile(0.25)
q50 = vendor_rates["vendor_approval_rate"].quantile(0.50)
q75 = vendor_rates["vendor_approval_rate"].quantile(0.75)

print(f"  Thresholds → q25: {q25:.4f} | q50: {q50:.4f} | q75: {q75:.4f}")

# Step 3: Assign tiers via explicit conditions (mirrors CASE WHEN in vendor_tiers CTE)
def assign_tier(rate):
    if rate <= q25:
        return "low"
    elif rate <= q50:
        return "below_avg"
    elif rate <= q75:
        return "above_avg"
    else:
        return "trusted"

vendor_rates["vendor_tier"] = vendor_rates["vendor_approval_rate"].apply(assign_tier)

# Step 4: Merge back to main df (same as before)
df = df.merge(
    vendor_rates[["vr_vndr_id", "vendor_approval_rate", "vendor_tier"]],
    on="vr_vndr_id",
    how="left"
)

# Vendors with < 10 estimates get flagged
df["vendor_tier"] = df["vendor_tier"].fillna("insufficient_history")

print("  Engineered: cost_per_lbr_hr, veh_age, est_amt_bucket,")
print("              lbr_hr_bucket, vendor_approval_rate, vendor_tier")
