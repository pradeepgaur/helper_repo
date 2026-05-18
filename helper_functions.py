CREATE INDEX IF NOT EXISTS idx_est_hist_est_id 
ON ice.t_6mo_est_hist (est_id);

CREATE INDEX IF NOT EXISTS idx_est_hist_est_id_rvsn_ts 
ON ice.t_6mo_est_hist (est_id, rvsn_nbr, last_updtd_tmstp DESC);
