"""
db.py — Database layer for the Repair Estimate Rule Simulator.

Manages the SSH tunnel, connection pool, metadata load, and the single
dashboard query.  Import this module from dashboard.py.

Usage:
    import db
    meta = db.load_metadata()      # called once at startup
    data = db.query_dashboard(p)   # called on each callback
"""

import json
import psycopg2
import psycopg2.pool
from sshtunnel import SSHTunnelForwarder

# ── Connection configuration ──────────────────────────────────────────────────
SSH_HOST = "10.117.111.4"
SSH_PORT = 22
SSH_USER = "e64d24"
SSH_KEY  = r"C:\Users\E64D24\.ssh\id_ed25519"

DB_HOST  = "vodev-db.postgres.database.azure.com"
DB_PORT  = 5432
DB_NAME  = "postgres"
DB_USER  = "voadmin"
DB_PASS  = "This-password-is-not-secure"

# ── Open SSH tunnel (kept alive for the lifetime of the process) ──────────────
print("Opening SSH tunnel…")
_tunnel = SSHTunnelForwarder(
    (SSH_HOST, SSH_PORT),
    ssh_username=SSH_USER,
    ssh_pkey=SSH_KEY,
    remote_bind_address=(DB_HOST, DB_PORT),
)
_tunnel.start()
print(f"  SSH tunnel open — localhost:{_tunnel.local_bind_port} → {DB_HOST}:{DB_PORT}")

# Send a keepalive packet every 60 s so the SSH server never drops the idle tunnel.
# This is the #1 cause of "Broken pipe" errors after a few minutes of inactivity.
_tunnel._transport.set_keepalive(60)

# ── Connection pool (thread-safe; Dash can run callbacks concurrently) ─────────
_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=10,             # increased — Dash debug mode uses multiple threads
    host="localhost",
    port=_tunnel.local_bind_port,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASS,
    connect_timeout=15,
    # TCP-level keepalives — keeps the DB connection alive through
    # firewalls/NAT even when no queries are running.
    keepalives=1,
    keepalives_idle=60,      # start probing after 60 s of inactivity
    keepalives_interval=10,  # retry probe every 10 s
    keepalives_count=5,      # drop connection after 5 missed probes
)
print("  Connection pool ready.")


def _get():
    """Borrow a connection from the pool.
    If the connection is broken (e.g. tunnel was idle), discard it properly
    and get a fresh one."""
    conn = _pool.getconn()
    try:
        if conn.closed:
            raise psycopg2.OperationalError("closed")
        # Ping — use a proper cursor, close it, and rollback so the
        # connection is returned in a clean state (no open transaction)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.rollback()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        # close=True tells the pool to discard this slot entirely
        # instead of putting a dead connection back as valid
        _pool.putconn(conn, close=True)
        conn = _pool.getconn()        # fresh connection
    return conn


def _put(conn):
    """Return a connection to the pool."""
    _pool.putconn(conn)


# ── Metadata — loaded once at startup ─────────────────────────────────────────
def load_metadata() -> dict:
    """
    Returns:
        all_dmg        : sorted list of distinct damage type strings
        all_states     : sorted list of distinct 2-letter state codes
        data_min_date  : earliest est_recv_dte (date object)
        data_max_date  : latest  est_recv_dte (date object)
        total_records  : total row count
        vendor_hist_max: highest per-vendor estimate count (for slider max)
    """
    conn = _get()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                /* distinct damage categories (max 6 buckets) */
                ARRAY(
                    SELECT DISTINCT public.dmg_category(dmg_dsc::TEXT)
                    FROM   public.v_t_6mo_master
                    WHERE  dmg_dsc IS NOT NULL
                    ORDER  BY 1
                )                                       AS all_dmg,

                /* distinct 2-letter state codes */
                ARRAY(
                    SELECT DISTINCT UPPER(TRIM(licplte_st::TEXT))
                    FROM   public.v_t_6mo_master
                    WHERE  licplte_st IS NOT NULL
                      AND  UPPER(TRIM(licplte_st::TEXT)) ~ '^[A-Z]{2}$'
                    ORDER  BY 1
                )                                       AS all_states,

                MIN(est_recv_dte)::DATE                 AS data_min_date,
                MAX(est_recv_dte)::DATE                 AS data_max_date,
                COUNT(*)                                AS total_records,

                /* max per-vendor estimate count — for Prior History slider */
                (
                    SELECT MAX(vc) FROM (
                        SELECT COUNT(*) AS vc
                        FROM   public.v_t_6mo_master
                        GROUP  BY vr_vndr_id
                    ) t
                )                                       AS vendor_hist_max

            FROM public.v_t_6mo_master
        """)
        row = cur.fetchone()
        cur.close()
        return {
            "all_dmg":         row[0] or [],
            "all_states":      row[1] or [],
            "data_min_date":   row[2],
            "data_max_date":   row[3],
            "total_records":   int(row[4]),
            "vendor_hist_max": int(row[5] or 100),
        }
    finally:
        _put(conn)


# ── Dashboard query — called on every callback ─────────────────────────────────
_QUERY = """
    SELECT public.fn_dashboard_agg(
        %(p_start_date)s,
        %(p_end_date)s,
        %(p_vendor_start_date)s,
        %(p_vendor_end_date)s,
        %(p_cost_min)s,
        %(p_cost_max)s,
        %(p_labor_min)s,
        %(p_labor_max)s,
        %(p_line_min)s,
        %(p_line_max)s,
        %(p_acc_min)s,
        %(p_prior_min)s,
        %(p_states)s,
        %(p_dmg_types)s,
        %(p_elec)s,
        %(p_bulk)s
    )
"""


def query_dashboard(params: dict) -> dict:
    """
    Call fn_dashboard_agg with the filter parameters dict.
    Returns a plain Python dict parsed from the returned JSON.

    Expected keys in params:
        p_start_date, p_end_date, p_vendor_start_date, p_vendor_end_date,
        p_cost_min, p_cost_max, p_labor_min, p_labor_max,
        p_line_min, p_line_max, p_acc_min, p_prior_min,
        p_states (list[str] | None), p_dmg_types (list[str] | None),
        p_elec ('any'|'Y'|'N'), p_bulk ('any'|'Y'|'N')
    """
    conn = _get()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY, params)
        result = cur.fetchone()[0]
        cur.close()
        # psycopg2 may return a dict (if using RealDictCursor) or a string
        if isinstance(result, str):
            return json.loads(result)
        return result or {}
    except Exception as exc:
        # Roll back so the connection is reusable
        conn.rollback()
        raise exc
    finally:
        _put(conn)
