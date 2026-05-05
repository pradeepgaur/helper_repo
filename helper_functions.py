-- =============================================================================
-- fn_dashboard_agg
-- Repair Estimate Rule Simulator — aggregation function
--
-- Run this file once on your PostgreSQL server:
--   psql -h <host> -U voadmin -d postgres -f pg_function.sql
--
-- Recommended indexes for performance on large tables:
--   CREATE INDEX IF NOT EXISTS idx_master_recv_dte  ON public.v_t_6mo_master (est_recv_dte);
--   CREATE INDEX IF NOT EXISTS idx_master_vndr_id   ON public.v_t_6mo_master (vr_vndr_id);
--   CREATE INDEX IF NOT EXISTS idx_master_dmg_dsc   ON public.v_t_6mo_master (dmg_dsc);
--   CREATE INDEX IF NOT EXISTS idx_master_state     ON public.v_t_6mo_master (licplte_st);
-- =============================================================================

CREATE OR REPLACE FUNCTION public.fn_dashboard_agg(
    p_start_date        DATE,
    p_end_date          DATE,
    p_vendor_start_date DATE,
    p_vendor_end_date   DATE,
    p_cost_min          NUMERIC,
    p_cost_max          NUMERIC,   -- pass 999999 to mean "no upper cap"
    p_labor_min         NUMERIC,
    p_labor_max         NUMERIC,   -- pass 9999   to mean "no upper cap"
    p_line_min          INTEGER,
    p_line_max          INTEGER,   -- pass 9999   to mean "no upper cap"
    p_acc_min           NUMERIC,   -- 0 = no filter (vendor first pass percentile)
    p_prior_min         INTEGER,   -- 0 = no filter (min vendor history)
    p_states            TEXT[],    -- NULL = all states
    p_dmg_types         TEXT[],    -- NULL = all damage types
    p_elec              TEXT,      -- 'any' | 'Y' | 'N'
    p_bulk              TEXT       -- 'any' | 'Y' | 'N'
)
RETURNS JSON
LANGUAGE plpgsql
STABLE
AS $func$
DECLARE
    v_result JSON;
BEGIN

WITH

-- ── 1. Vendor stats from vendor date window ─────────────────────────────────
vendor_stats AS (
    SELECT
        vr_vndr_id,
        COUNT(*)                                                            AS vc,
        AVG(CASE WHEN repr_auth_stat_typ_cde = 'A' THEN 1.0 ELSE 0.0 END) AS vr
    FROM public.v_t_6mo_master
    WHERE est_recv_dte::DATE BETWEEN p_vendor_start_date AND p_vendor_end_date
    GROUP BY vr_vndr_id
),

-- ── 2. Base = data date window only (used for "Total" bars in charts) ────────
base AS (
    SELECT
        m.est_id,
        COALESCE(m.est_tot_amt::NUMERIC,          0)  AS est_tot_amt,
        COALESCE(m.lbr_hr_qty::NUMERIC,           0)  AS lbr_hr_qty,
        COALESCE(m.line_item_count::INTEGER,       0)  AS line_item_count,
        COALESCE(m.time_to_approve_hours::NUMERIC, 0)  AS time_to_approve_hours,
        m.dmg_dsc::TEXT                               AS dmg_dsc,
        UPPER(TRIM(m.licplte_st::TEXT))               AS licplte_st,
        m.repr_auth_stat_typ_cde,
        m.rvsn_nbr::INTEGER                           AS rvsn_nbr,
        m.is_electronic_est_ind::TEXT                 AS is_electronic_est_ind,
        m.is_bulk_ind::TEXT                           AS is_bulk_ind,
        m.vr_vndr_id,
        COALESCE(vs.vc, 0)                            AS vendor_est_count,
        COALESCE(vs.vr, 0.0)                          AS vendor_approval_rate,
        (m.repr_auth_stat_typ_cde = 'A')              AS auto_approved
    FROM public.v_t_6mo_master m
    LEFT JOIN vendor_stats vs ON m.vr_vndr_id = vs.vr_vndr_id
    WHERE m.est_recv_dte::DATE BETWEEN p_start_date AND p_end_date
),

-- ── 3. Filtered = base + all sidebar filters ─────────────────────────────────
filtered AS (
    SELECT * FROM base
    WHERE
        est_tot_amt    >= p_cost_min
        AND est_tot_amt    <= p_cost_max
        AND lbr_hr_qty >= p_labor_min
        AND lbr_hr_qty <= p_labor_max
        AND line_item_count >= p_line_min
        AND line_item_count <= p_line_max
        AND (p_acc_min   = 0 OR vendor_approval_rate >= p_acc_min)
        AND (p_prior_min = 0 OR vendor_est_count     >= p_prior_min)
        AND (p_states    IS NULL
             OR array_length(p_states, 1) IS NULL
             OR licplte_st = ANY(p_states))
        AND (p_dmg_types IS NULL
             OR array_length(p_dmg_types, 1) IS NULL
             OR dmg_dsc = ANY(p_dmg_types))
        AND (p_elec = 'any' OR is_electronic_est_ind = p_elec)
        AND (p_bulk = 'any' OR is_bulk_ind = p_bulk)
),

-- ── 4. KPIs ──────────────────────────────────────────────────────────────────
kpis AS (
    SELECT
        (SELECT COUNT(*) FROM base)                                           AS n_date,
        COUNT(*)                                                              AS n,
        SUM(CASE WHEN rvsn_nbr = 1  THEN 1 ELSE 0 END)                       AS n_rev1,
        SUM(CASE WHEN auto_approved THEN 1 ELSE 0 END)                        AS n_appr,
        COALESCE(SUM(CASE WHEN auto_approved
                     THEN time_to_approve_hours ELSE 0 END), 0)               AS time_saved_hrs,
        AVG(CASE WHEN rvsn_nbr = 1  THEN est_tot_amt ELSE NULL END)           AS mean_correct_amt,
        AVG(CASE WHEN rvsn_nbr <> 1 THEN est_tot_amt ELSE NULL END)           AS mean_wrong_amt
    FROM filtered
),

-- ── 5a. Amount histogram ─────────────────────────────────────────────────────
amt_buckets AS (
    SELECT
        CASE
            WHEN est_tot_amt <   250 THEN 1
            WHEN est_tot_amt <   500 THEN 2
            WHEN est_tot_amt <   750 THEN 3
            WHEN est_tot_amt <  1000 THEN 4
            WHEN est_tot_amt <  1500 THEN 5
            WHEN est_tot_amt <  2500 THEN 6
            ELSE 7
        END                                                                   AS ord,
        CASE
            WHEN est_tot_amt <   250 THEN '$0-250'
            WHEN est_tot_amt <   500 THEN '$250-500'
            WHEN est_tot_amt <   750 THEN '$500-750'
            WHEN est_tot_amt <  1000 THEN '$750-1k'
            WHEN est_tot_amt <  1500 THEN '$1k-1.5k'
            WHEN est_tot_amt <  2500 THEN '$1.5k-2.5k'
            ELSE '$2.5k+'
        END                                                                   AS bucket,
        COUNT(*)                                                              AS total,
        0                                                                     AS filtered
    FROM base GROUP BY 1, 2
    UNION ALL
    SELECT
        CASE
            WHEN est_tot_amt <   250 THEN 1
            WHEN est_tot_amt <   500 THEN 2
            WHEN est_tot_amt <   750 THEN 3
            WHEN est_tot_amt <  1000 THEN 4
            WHEN est_tot_amt <  1500 THEN 5
            WHEN est_tot_amt <  2500 THEN 6
            ELSE 7
        END,
        CASE
            WHEN est_tot_amt <   250 THEN '$0-250'
            WHEN est_tot_amt <   500 THEN '$250-500'
            WHEN est_tot_amt <   750 THEN '$500-750'
            WHEN est_tot_amt <  1000 THEN '$750-1k'
            WHEN est_tot_amt <  1500 THEN '$1k-1.5k'
            WHEN est_tot_amt <  2500 THEN '$1.5k-2.5k'
            ELSE '$2.5k+'
        END,
        0,
        COUNT(*)
    FROM filtered GROUP BY 1, 2
),
hist_amt AS (
    SELECT ord, bucket,
           SUM(total)    AS total,
           SUM(filtered) AS filtered
    FROM amt_buckets GROUP BY ord, bucket
),

-- ── 5b. Labour hours histogram ───────────────────────────────────────────────
labor_buckets AS (
    SELECT
        CASE
            WHEN lbr_hr_qty <  2 THEN 1 WHEN lbr_hr_qty <  4 THEN 2
            WHEN lbr_hr_qty <  6 THEN 3 WHEN lbr_hr_qty <  8 THEN 4
            WHEN lbr_hr_qty < 12 THEN 5 WHEN lbr_hr_qty < 16 THEN 6
            WHEN lbr_hr_qty < 24 THEN 7 WHEN lbr_hr_qty < 48 THEN 8
            ELSE 9
        END ord,
        CASE
            WHEN lbr_hr_qty <  2 THEN '0-2'   WHEN lbr_hr_qty <  4 THEN '2-4'
            WHEN lbr_hr_qty <  6 THEN '4-6'   WHEN lbr_hr_qty <  8 THEN '6-8'
            WHEN lbr_hr_qty < 12 THEN '8-12'  WHEN lbr_hr_qty < 16 THEN '12-16'
            WHEN lbr_hr_qty < 24 THEN '16-24' WHEN lbr_hr_qty < 48 THEN '24-48'
            ELSE '48+'
        END bucket,
        COUNT(*) total, 0 filtered
    FROM base GROUP BY 1,2
    UNION ALL
    SELECT
        CASE
            WHEN lbr_hr_qty <  2 THEN 1 WHEN lbr_hr_qty <  4 THEN 2
            WHEN lbr_hr_qty <  6 THEN 3 WHEN lbr_hr_qty <  8 THEN 4
            WHEN lbr_hr_qty < 12 THEN 5 WHEN lbr_hr_qty < 16 THEN 6
            WHEN lbr_hr_qty < 24 THEN 7 WHEN lbr_hr_qty < 48 THEN 8
            ELSE 9
        END,
        CASE
            WHEN lbr_hr_qty <  2 THEN '0-2'   WHEN lbr_hr_qty <  4 THEN '2-4'
            WHEN lbr_hr_qty <  6 THEN '4-6'   WHEN lbr_hr_qty <  8 THEN '6-8'
            WHEN lbr_hr_qty < 12 THEN '8-12'  WHEN lbr_hr_qty < 16 THEN '12-16'
            WHEN lbr_hr_qty < 24 THEN '16-24' WHEN lbr_hr_qty < 48 THEN '24-48'
            ELSE '48+'
        END,
        0, COUNT(*)
    FROM filtered GROUP BY 1,2
),
hist_labor AS (
    SELECT ord, bucket, SUM(total) total, SUM(filtered) filtered
    FROM labor_buckets GROUP BY ord, bucket
),

-- ── 5c. Line items histogram ─────────────────────────────────────────────────
lines_buckets AS (
    SELECT
        CASE
            WHEN line_item_count <  4 THEN 1 WHEN line_item_count <  6 THEN 2
            WHEN line_item_count <  8 THEN 3 WHEN line_item_count < 12 THEN 4
            WHEN line_item_count < 16 THEN 5 WHEN line_item_count < 20 THEN 6
            WHEN line_item_count < 24 THEN 7 WHEN line_item_count < 30 THEN 8
            WHEN line_item_count < 40 THEN 9 ELSE 10
        END ord,
        CASE
            WHEN line_item_count <  4 THEN '0-4'   WHEN line_item_count <  6 THEN '4-6'
            WHEN line_item_count <  8 THEN '6-8'   WHEN line_item_count < 12 THEN '8-12'
            WHEN line_item_count < 16 THEN '12-16' WHEN line_item_count < 20 THEN '16-20'
            WHEN line_item_count < 24 THEN '20-24' WHEN line_item_count < 30 THEN '24-30'
            WHEN line_item_count < 40 THEN '30-40' ELSE '40+'
        END bucket,
        COUNT(*) total, 0 filtered
    FROM base GROUP BY 1,2
    UNION ALL
    SELECT
        CASE
            WHEN line_item_count <  4 THEN 1 WHEN line_item_count <  6 THEN 2
            WHEN line_item_count <  8 THEN 3 WHEN line_item_count < 12 THEN 4
            WHEN line_item_count < 16 THEN 5 WHEN line_item_count < 20 THEN 6
            WHEN line_item_count < 24 THEN 7 WHEN line_item_count < 30 THEN 8
            WHEN line_item_count < 40 THEN 9 ELSE 10
        END,
        CASE
            WHEN line_item_count <  4 THEN '0-4'   WHEN line_item_count <  6 THEN '4-6'
            WHEN line_item_count <  8 THEN '6-8'   WHEN line_item_count < 12 THEN '8-12'
            WHEN line_item_count < 16 THEN '12-16' WHEN line_item_count < 20 THEN '16-20'
            WHEN line_item_count < 24 THEN '20-24' WHEN line_item_count < 30 THEN '24-30'
            WHEN line_item_count < 40 THEN '30-40' ELSE '40+'
        END,
        0, COUNT(*)
    FROM filtered GROUP BY 1,2
),
hist_lines AS (
    SELECT ord, bucket, SUM(total) total, SUM(filtered) filtered
    FROM lines_buckets GROUP BY ord, bucket
),

-- ── 5d. Time to approve histogram ────────────────────────────────────────────
time_buckets AS (
    SELECT
        CASE
            WHEN time_to_approve_hours <  2 THEN 1 WHEN time_to_approve_hours <  4 THEN 2
            WHEN time_to_approve_hours <  8 THEN 3 WHEN time_to_approve_hours < 16 THEN 4
            WHEN time_to_approve_hours < 24 THEN 5 WHEN time_to_approve_hours < 48 THEN 6
            WHEN time_to_approve_hours < 72 THEN 7 ELSE 8
        END ord,
        CASE
            WHEN time_to_approve_hours <  2 THEN '0-2'   WHEN time_to_approve_hours <  4 THEN '2-4'
            WHEN time_to_approve_hours <  8 THEN '4-8'   WHEN time_to_approve_hours < 16 THEN '8-16'
            WHEN time_to_approve_hours < 24 THEN '16-24' WHEN time_to_approve_hours < 48 THEN '24-48'
            WHEN time_to_approve_hours < 72 THEN '48-72' ELSE '72+'
        END bucket,
        COUNT(*) total, 0 filtered
    FROM base GROUP BY 1,2
    UNION ALL
    SELECT
        CASE
            WHEN time_to_approve_hours <  2 THEN 1 WHEN time_to_approve_hours <  4 THEN 2
            WHEN time_to_approve_hours <  8 THEN 3 WHEN time_to_approve_hours < 16 THEN 4
            WHEN time_to_approve_hours < 24 THEN 5 WHEN time_to_approve_hours < 48 THEN 6
            WHEN time_to_approve_hours < 72 THEN 7 ELSE 8
        END,
        CASE
            WHEN time_to_approve_hours <  2 THEN '0-2'   WHEN time_to_approve_hours <  4 THEN '2-4'
            WHEN time_to_approve_hours <  8 THEN '4-8'   WHEN time_to_approve_hours < 16 THEN '8-16'
            WHEN time_to_approve_hours < 24 THEN '16-24' WHEN time_to_approve_hours < 48 THEN '24-48'
            WHEN time_to_approve_hours < 72 THEN '48-72' ELSE '72+'
        END,
        0, COUNT(*)
    FROM filtered GROUP BY 1,2
),
hist_time AS (
    SELECT ord, bucket, SUM(total) total, SUM(filtered) filtered
    FROM time_buckets GROUP BY ord, bucket
),

-- ── 6. Damage type counts ─────────────────────────────────────────────────────
dmg_counts AS (
    SELECT
        b.dmg_dsc,
        b.total,
        COALESCE(f.filtered, 0) AS filtered
    FROM (SELECT dmg_dsc, COUNT(*) total   FROM base     WHERE dmg_dsc IS NOT NULL GROUP BY dmg_dsc) b
    LEFT JOIN
         (SELECT dmg_dsc, COUNT(*) filtered FROM filtered WHERE dmg_dsc IS NOT NULL GROUP BY dmg_dsc) f
    ON b.dmg_dsc = f.dmg_dsc
),

-- ── 7. State counts (filtered only, for bubble map) ──────────────────────────
state_counts AS (
    SELECT
        licplte_st                             AS state,
        COUNT(*)                               AS cnt
    FROM filtered
    WHERE licplte_st IS NOT NULL
      AND licplte_st ~ '^[A-Z]{2}$'
    GROUP BY licplte_st
),

-- ── 8. Box plot stats by damage type ─────────────────────────────────────────
box_base AS (
    SELECT
        dmg_dsc,
        MIN(est_tot_amt)                                                      AS bmin,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY est_tot_amt)             AS q1,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY est_tot_amt)             AS median,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY est_tot_amt)             AS q3,
        MAX(est_tot_amt)                                                      AS bmax
    FROM base
    WHERE dmg_dsc IS NOT NULL
    GROUP BY dmg_dsc
),
box_filt AS (
    SELECT
        dmg_dsc,
        MIN(est_tot_amt)                                                      AS bmin,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY est_tot_amt)             AS q1,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY est_tot_amt)             AS median,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY est_tot_amt)             AS q3,
        MAX(est_tot_amt)                                                      AS bmax
    FROM filtered
    WHERE dmg_dsc IS NOT NULL
    GROUP BY dmg_dsc
)

-- ── Assemble all sections into a single JSON object ───────────────────────────
SELECT json_build_object(

    'kpis', (SELECT row_to_json(k) FROM kpis k),

    'hist_amt', (
        SELECT json_agg(row_to_json(r) ORDER BY r.ord)
        FROM hist_amt r
    ),
    'hist_labor', (
        SELECT json_agg(row_to_json(r) ORDER BY r.ord)
        FROM hist_labor r
    ),
    'hist_lines', (
        SELECT json_agg(row_to_json(r) ORDER BY r.ord)
        FROM hist_lines r
    ),
    'hist_time', (
        SELECT json_agg(row_to_json(r) ORDER BY r.ord)
        FROM hist_time r
    ),

    'dmg_counts', (
        SELECT json_agg(row_to_json(r) ORDER BY r.total DESC)
        FROM dmg_counts r
    ),

    'state_counts', (
        SELECT json_agg(row_to_json(r))
        FROM state_counts r
    ),

    'box_base', (
        SELECT json_agg(json_build_object(
            'dmg_dsc', b.dmg_dsc,
            'q1',      b.q1,
            'median',  b.median,
            'q3',      b.q3,
            'lf',      GREATEST(b.bmin, b.q1 - 1.5 * (b.q3 - b.q1)),
            'uf',      LEAST(b.bmax,   b.q3 + 1.5 * (b.q3 - b.q1))
        ))
        FROM box_base b
    ),

    'box_filt', (
        SELECT json_agg(json_build_object(
            'dmg_dsc', f.dmg_dsc,
            'q1',      f.q1,
            'median',  f.median,
            'q3',      f.q3,
            'lf',      GREATEST(f.bmin, f.q1 - 1.5 * (f.q3 - f.q1)),
            'uf',      LEAST(f.bmax,   f.q3 + 1.5 * (f.q3 - f.q1))
        ))
        FROM box_filt f
    )

) INTO v_result;

RETURN v_result;

END;
$func$;
