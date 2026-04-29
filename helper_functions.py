-- =============================================================
-- Auto-Approval Rule Analysis — PostgreSQL
-- =============================================================
-- Step 1: Build vendor trust tiers from Jan–Nov data
-- Step 2: Apply tiers to December estimates
-- Step 3: Evaluate rule performance on December
-- Step 4: Confusion matrix + metrics
-- Step 5: Sensitivity analysis on $ threshold
-- Step 6: FP deep-dive
--
-- ASSUMPTION: Your table is named "estimates"
-- Update the table name and date column below if different.
-- Date column used: est_recv_dte (cast to date)
-- =============================================================


-- ─────────────────────────────────────────────────────────────
-- CONFIG — update these if your table/column names differ
-- ─────────────────────────────────────────────────────────────
-- Table name  : estimates
-- Date column : est_recv_dte
-- Training    : January through November (months 1–11)
-- Test        : December (month 12)
-- =============================================================


-- ─────────────────────────────────────────────────────────────
-- STEP 1: TRAINING DATA — Jan to Nov
--         Compute first_pass label and vendor approval rates
-- ─────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS train_data;
CREATE TEMP TABLE train_data AS
SELECT
    est_id,
    vr_vndr_id,
    rvsn_nbr,
    est_tot_amt,
    lbr_hr_qty,
    line_item_count,
    negative_or_null_est_ind,
    licplte_st,
    est_recv_dte,
    -- Target variable: 1 if approved first pass, 0 otherwise
    CASE WHEN rvsn_nbr = 1 THEN 1 ELSE 0 END AS first_pass
FROM estimates
WHERE
    -- Training window: January through November
    -- Adjust year as needed
    EXTRACT(MONTH FROM est_recv_dte::date) BETWEEN 1 AND 11;

-- Quick check
SELECT
    COUNT(*)                                        AS total_estimates,
    SUM(first_pass)                                 AS first_pass_count,
    ROUND(AVG(first_pass::numeric) * 100, 1)        AS first_pass_rate_pct
FROM train_data;


-- ─────────────────────────────────────────────────────────────
-- STEP 2: VENDOR APPROVAL RATES from training data
-- ─────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS vendor_stats;
CREATE TEMP TABLE vendor_stats AS
SELECT
    vr_vndr_id,
    COUNT(*)                                                AS vendor_est_count,
    ROUND(AVG(first_pass::numeric), 4)                      AS vendor_approval_rate
FROM train_data
GROUP BY vr_vndr_id;


-- ─────────────────────────────────────────────────────────────
-- STEP 3: COMPUTE QUARTILE BOUNDARIES
--         Only from vendors with >= 10 estimates (same as Python)
-- ─────────────────────────────────────────────────────────────

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


-- ─────────────────────────────────────────────────────────────
-- STEP 5: DECEMBER TEST DATA
--         Join with vendor tiers built on Jan–Nov
-- ─────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS dec_data;
CREATE TEMP TABLE dec_data AS
SELECT
    e.est_id,
    e.vr_vndr_id,
    e.rvsn_nbr,
    e.est_tot_amt,
    e.lbr_hr_qty,
    e.line_item_count,
    e.negative_or_null_est_ind,
    e.licplte_st,
    e.est_recv_dte,
    -- Target: 1 = first-pass approval
    CASE WHEN e.rvsn_nbr = 1 THEN 1 ELSE 0 END AS first_pass,
    -- Vendor tier from Jan–Nov training (NULL = vendor not seen in training)
    COALESCE(vt.vendor_tier, 'insufficient_history')    AS vendor_tier,
    COALESCE(vt.vendor_approval_rate, 0)                AS vendor_approval_rate,
    COALESCE(vt.vendor_est_count, 0)                    AS vendor_est_count,
    -- AUTO-APPROVAL RULE (R4)
    CASE
        WHEN COALESCE(vt.vendor_tier, 'insufficient_history') = 'trusted'
         AND e.est_tot_amt      <= 500
         AND e.lbr_hr_qty       <= 6
         AND e.line_item_count  <= 10
         AND e.negative_or_null_est_ind = 0
        THEN 1
        ELSE 0
    END AS auto_approve
FROM estimates e
LEFT JOIN vendor_tiers vt ON e.vr_vndr_id = vt.vr_vndr_id
WHERE
    EXTRACT(MONTH FROM e.est_recv_dte::date) = 12;

-- December data overview
SELECT
    COUNT(*)                                        AS dec_total,
    SUM(first_pass)                                 AS first_pass_count,
    ROUND(AVG(first_pass::numeric)*100,1)           AS first_pass_rate_pct,
    SUM(auto_approve)                               AS auto_approve_count,
    ROUND(AVG(auto_approve::numeric)*100,1)         AS auto_approve_rate_pct
FROM dec_data;


-- ─────────────────────────────────────────────────────────────
-- STEP 6: CONFUSION MATRIX on December
-- ─────────────────────────────────────────────────────────────

SELECT
    '── December Confusion Matrix ──'                AS label,
    SUM(CASE WHEN auto_approve=1 AND first_pass=1 THEN 1 ELSE 0 END) AS TP,
    SUM(CASE WHEN auto_approve=1 AND first_pass=0 THEN 1 ELSE 0 END) AS FP,
    SUM(CASE WHEN auto_approve=0 AND first_pass=0 THEN 1 ELSE 0 END) AS TN,
    SUM(CASE WHEN auto_approve=0 AND first_pass=1 THEN 1 ELSE 0 END) AS FN
FROM dec_data;


-- ─────────────────────────────────────────────────────────────
-- STEP 7: PERFORMANCE METRICS on December
-- ─────────────────────────────────────────────────────────────

WITH cm AS (
    SELECT
        SUM(CASE WHEN auto_approve=1 AND first_pass=1 THEN 1 ELSE 0 END)::numeric AS tp,
        SUM(CASE WHEN auto_approve=1 AND first_pass=0 THEN 1 ELSE 0 END)::numeric AS fp,
        SUM(CASE WHEN auto_approve=0 AND first_pass=0 THEN 1 ELSE 0 END)::numeric AS tn,
        SUM(CASE WHEN auto_approve=0 AND first_pass=1 THEN 1 ELSE 0 END)::numeric AS fn,
        COUNT(*)::numeric                                                           AS n
    FROM dec_data
)
SELECT
    -- Core ML metrics
    ROUND((tp + tn) / n * 100, 1)                           AS accuracy_pct,
    ROUND(tp / NULLIF(tp + fp, 0) * 100, 1)                 AS precision_pct,
    ROUND(tp / NULLIF(tp + fn, 0) * 100, 1)                 AS recall_pct,
    ROUND(
        2 * (tp / NULLIF(tp+fp,0)) * (tp / NULLIF(tp+fn,0))
        / NULLIF((tp/NULLIF(tp+fp,0)) + (tp/NULLIF(tp+fn,0)), 0)
    , 3)                                                     AS f1_score,

    -- Business metrics
    ROUND(fp / NULLIF(tp + fp, 0) * 100, 1)                 AS wrong_approval_rate_pct,
    ROUND((tp + fp) / n * 100, 1)                           AS coverage_pct,

    -- Raw counts
    tp::int                                                  AS correct_auto_approvals,
    fp::int                                                  AS wrong_auto_approvals,
    tn::int                                                  AS correctly_held_back,
    fn::int                                                  AS missed_opportunities,
    n::int                                                   AS total_dec_estimates
FROM cm;


-- ─────────────────────────────────────────────────────────────
-- STEP 8: COMPARE DECEMBER vs JAN–NOV TRAINING METRICS
--         (check if rule performance has drifted)
-- ─────────────────────────────────────────────────────────────

WITH
train_cm AS (
    SELECT
        SUM(CASE
            WHEN vt.vendor_tier = 'trusted'
             AND t.est_tot_amt <= 500
             AND t.lbr_hr_qty  <= 6
             AND t.line_item_count <= 10
             AND t.negative_or_null_est_ind = 0
             AND t.first_pass = 1 THEN 1 ELSE 0 END)::numeric AS tp,
        SUM(CASE
            WHEN vt.vendor_tier = 'trusted'
             AND t.est_tot_amt <= 500
             AND t.lbr_hr_qty  <= 6
             AND t.line_item_count <= 10
             AND t.negative_or_null_est_ind = 0
             AND t.first_pass = 0 THEN 1 ELSE 0 END)::numeric AS fp,
        COUNT(*)::numeric AS n
    FROM train_data t
    LEFT JOIN vendor_tiers vt ON t.vr_vndr_id = vt.vr_vndr_id
),
dec_cm AS (
    SELECT
        SUM(CASE WHEN auto_approve=1 AND first_pass=1 THEN 1 ELSE 0 END)::numeric AS tp,
        SUM(CASE WHEN auto_approve=1 AND first_pass=0 THEN 1 ELSE 0 END)::numeric AS fp,
        COUNT(*)::numeric AS n
    FROM dec_data
)
SELECT
    'Jan–Nov (training)'                                        AS period,
    ROUND(tp / NULLIF(tp+fp,0) * 100, 1)                       AS precision_pct,
    ROUND((tp+fp) / n * 100, 1)                                AS coverage_pct,
    ROUND(fp / NULLIF(tp+fp,0) * 100, 1)                       AS wrong_approval_pct
FROM train_cm
UNION ALL
SELECT
    'December (test)'                                           AS period,
    ROUND(tp / NULLIF(tp+fp,0) * 100, 1)                       AS precision_pct,
    ROUND((tp+fp) / n * 100, 1)                                AS coverage_pct,
    ROUND(fp / NULLIF(tp+fp,0) * 100, 1)                       AS wrong_approval_pct
FROM dec_cm;


-- ─────────────────────────────────────────────────────────────
-- STEP 9: SENSITIVITY ANALYSIS on December
--         Vary $ threshold, keep other conditions fixed
-- ─────────────────────────────────────────────────────────────

WITH thresholds AS (
    SELECT unnest(ARRAY[250,350,500,600,750,1000,1500]) AS amt_limit
),
results AS (
    SELECT
        t.amt_limit,
        SUM(CASE
            WHEN d.vendor_tier='trusted'
             AND d.est_tot_amt <= t.amt_limit
             AND d.lbr_hr_qty <= 6
             AND d.line_item_count <= 10
             AND d.negative_or_null_est_ind = 0
             AND d.first_pass = 1 THEN 1 ELSE 0 END)::numeric AS tp,
        SUM(CASE
            WHEN d.vendor_tier='trusted'
             AND d.est_tot_amt <= t.amt_limit
             AND d.lbr_hr_qty <= 6
             AND d.line_item_count <= 10
             AND d.negative_or_null_est_ind = 0
             AND d.first_pass = 0 THEN 1 ELSE 0 END)::numeric AS fp,
        COUNT(*)::numeric AS n
    FROM dec_data d
    CROSS JOIN thresholds t
    GROUP BY t.amt_limit
)
SELECT
    '$<= ' || amt_limit                                         AS threshold,
    (tp + fp)::int                                              AS auto_approved,
    ROUND((tp+fp)/n*100, 1)                                     AS coverage_pct,
    ROUND(tp/NULLIF(tp+fp,0)*100, 1)                            AS precision_pct,
    fp::int                                                     AS wrong_approvals,
    ROUND(fp/NULLIF(tp+fp,0)*100, 1)                            AS wrong_pct
FROM results
ORDER BY amt_limit;


-- ─────────────────────────────────────────────────────────────
-- STEP 10: VENDOR TIER PERFORMANCE in December
--          (approval rate per tier in Dec vs training)
-- ─────────────────────────────────────────────────────────────

SELECT
    vendor_tier,
    COUNT(*)                                        AS dec_estimates,
    SUM(first_pass)                                 AS first_pass_count,
    ROUND(AVG(first_pass::numeric)*100,1)           AS approval_rate_pct,
    SUM(auto_approve)                               AS auto_approved,
    ROUND(AVG(auto_approve::numeric)*100,1)         AS auto_approve_rate_pct
FROM dec_data
GROUP BY vendor_tier
ORDER BY approval_rate_pct DESC;


-- ─────────────────────────────────────────────────────────────
-- STEP 11: FP DEEP-DIVE — wrong auto-approvals in December
--          (which vendors / states / amounts caused errors)
-- ─────────────────────────────────────────────────────────────

-- FP by revision number (how many revisions did wrong approvals need?)
SELECT
    rvsn_nbr,
    COUNT(*)        AS fp_count
FROM dec_data
WHERE auto_approve = 1 AND first_pass = 0
GROUP BY rvsn_nbr
ORDER BY rvsn_nbr;

-- FP by state
SELECT
    licplte_st,
    COUNT(*)                                        AS fp_count,
    ROUND(AVG(est_tot_amt)::numeric, 0)             AS avg_amt,
    ROUND(AVG(lbr_hr_qty)::numeric, 1)              AS avg_lbr_hrs
FROM dec_data
WHERE auto_approve = 1 AND first_pass = 0
GROUP BY licplte_st
ORDER BY fp_count DESC
LIMIT 10;

-- FP amount distribution
SELECT
    ROUND(MIN(est_tot_amt)::numeric, 0)             AS min_amt,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP
          (ORDER BY est_tot_amt)::numeric, 0)        AS q25_amt,
    ROUND(AVG(est_tot_amt)::numeric, 0)             AS avg_amt,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP
          (ORDER BY est_tot_amt)::numeric, 0)        AS q75_amt,
    ROUND(MAX(est_tot_amt)::numeric, 0)             AS max_amt
FROM dec_data
WHERE auto_approve = 1 AND first_pass = 0;

-- FP by vendor — which trusted vendors caused most errors?
SELECT
    vr_vndr_id,
    vendor_approval_rate,
    COUNT(*)                                        AS fp_count,
    ROUND(AVG(est_tot_amt)::numeric, 0)             AS avg_amt
FROM dec_data
WHERE auto_approve = 1 AND first_pass = 0
GROUP BY vr_vndr_id, vendor_approval_rate
ORDER BY fp_count DESC
LIMIT 15;


-- ─────────────────────────────────────────────────────────────
-- STEP 12: NEW VENDORS IN DECEMBER
--          (vendors that appeared in Dec but not in training)
-- ─────────────────────────────────────────────────────────────

SELECT
    COUNT(DISTINCT d.vr_vndr_id)    AS new_vendors_in_dec,
    COUNT(*)                        AS estimates_from_new_vendors,
    ROUND(AVG(d.first_pass::numeric)*100,1) AS their_approval_rate_pct
FROM dec_data d
WHERE d.vendor_est_count = 0;  -- vendor_est_count=0 means not seen in training


-- ─────────────────────────────────────────────────────────────
-- STEP 13: FULL LABELLED OUTPUT
--          Every December estimate tagged TP / FP / TN / FN
--          Export this result to review in Excel
-- ─────────────────────────────────────────────────────────────

SELECT
    est_id,
    vr_vndr_id,
    vendor_tier,
    ROUND(vendor_approval_rate::numeric * 100, 1)   AS vendor_approval_rate_pct,
    vendor_est_count                                AS vendor_training_estimates,
    est_tot_amt,
    lbr_hr_qty,
    line_item_count,
    negative_or_null_est_ind,
    rvsn_nbr,
    first_pass,
    auto_approve,
    licplte_st,
    est_recv_dte,
    CASE
        WHEN auto_approve=1 AND first_pass=1 THEN 'TP — correct auto-approval'
        WHEN auto_approve=1 AND first_pass=0 THEN 'FP — wrong auto-approval'
        WHEN auto_approve=0 AND first_pass=0 THEN 'TN — correctly held back'
        WHEN auto_approve=0 AND first_pass=1 THEN 'FN — missed opportunity'
    END AS outcome
FROM dec_data
ORDER BY
    -- Show FPs first so you can review errors immediately
    CASE WHEN auto_approve=1 AND first_pass=0 THEN 0 ELSE 1 END,
    est_tot_amt DESC;
