

DROP TABLE IF EXISTS vendor_quartiles;
CREATE TEMP TABLE vendor_quartiles AS
SELECT
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY vendor_approval_rate) AS q25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY vendor_approval_rate) AS q50,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY vendor_approval_rate) AS q75
FROM vendor_stats
WHERE vendor_est_count >= 10;

-- Inspect the boundaries
SELECT
    ROUND(q25::numeric * 100, 2) AS q25_pct,
    ROUND(q50::numeric * 100, 2) AS q50_pct,
    ROUND(q75::numeric * 100, 2) AS q75_pct
FROM vendor_quartiles;


-- ─────────────────────────────────────────────────────────────
-- STEP 4: ASSIGN VENDOR TIERS (from training data)
-- ─────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS vendor_tiers;
CREATE TEMP TABLE vendor_tiers AS
SELECT
    vs.vr_vndr_id,
    vs.vendor_est_count,
    vs.vendor_approval_rate,
    CASE
        WHEN vs.vendor_est_count < 10
            THEN 'insufficient_history'
        WHEN vs.vendor_approval_rate >= vq.q75
            THEN 'trusted'
        WHEN vs.vendor_approval_rate >= vq.q50
            THEN 'above_avg'
        WHEN vs.vendor_approval_rate >= vq.q25
            THEN 'below_avg'
        ELSE
            'low'
    END AS vendor_tier
FROM vendor_stats vs
CROSS JOIN vendor_quartiles vq;

-- Tier distribution summary
SELECT
    vendor_tier,
    COUNT(*)                                AS vendor_count,
    ROUND(AVG(vendor_approval_rate)*100, 1) AS avg_approval_rate_pct
FROM vendor_tiers
GROUP BY vendor_tier
ORDER BY avg_approval_rate_pct DESC;
