Section 1 — CSS
1A. Modify existing .fb-btn rule
Add flex-shrink: 0 to the existing rule:
-----------------------
.fb-btn { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 500; color: var(--text-3); background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 4px 9px; cursor: pointer; transition: all 0.15s; white-space: nowrap; font-family: var(--font); flex-shrink: 0; }
1B. Add new block before the /* ─── RESPONSIVE ─── */ comment
--------------------
/* ─── HAMBURGER / SIDEBAR DRAWER ─── */
.hamburger-btn { display: none; background: none; border: none; cursor: pointer; padding: 6px 8px; flex-direction: column; gap: 5px; align-items: center; justify-content: center; flex-shrink: 0; border-radius: 6px; }
.hamburger-btn:hover { background: var(--surface-2); }
.hamburger-btn span { display: block; width: 20px; height: 2px; background: var(--text-2); border-radius: 2px; transition: background 0.15s; }
.hamburger-btn:hover span { background: var(--text-1); }
.sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 149; cursor: pointer; }
.app.sidebar-open .sidebar-overlay { display: block; }
.app.sidebar-open .sidebar { transform: translateX(0) !important; box-shadow: 4px 0 24px rgba(0,0,0,0.22); }
1C. Replace the entire /* ─── RESPONSIVE ─── */ block
/* ─── RESPONSIVE ─── */

/* Compact laptop / landscape tablet  ≤ 1200px */
@media (max-width: 1200px) {
  .four-col             { grid-template-columns: repeat(2, 1fr); }
  .content              { padding: 18px 22px; gap: 16px; }
  .topbar               { padding: 0 22px; }
  /* Feedback button: icon-only on narrower cards */
  .fb-btn               { padding: 5px; width: 28px; height: 28px; justify-content: center; gap: 0; }
  .fb-btn-text          { display: none; }
  /* Card heads: let feedback button wrap below title instead of being clipped */
  .card-head            { flex-wrap: wrap; gap: 4px; height: auto; min-height: 48px; padding: 10px 16px; }
  .breakdown-card-head  { flex-wrap: wrap; gap: 4px; height: auto; min-height: 44px; padding: 8px 14px; }
  /* Breakdown rows: label shrinks freely; pill wraps if needed */
  .bi                   { flex-wrap: wrap; row-gap: 3px; }
  .bi-label             { flex: 1 1 auto; min-width: 60px; margin-right: 6px; }
  .bi-pill              { margin-left: auto; }
}

/* Tablet  ≤ 960px */
@media (max-width: 960px) {
  :root { --sidebar-w: 210px; --panel-w: 300px; }
  .two-col              { grid-template-columns: 1fr; }
  .photo-grid           { grid-template-columns: repeat(2, 1fr); }
  .photo-grid-body      { max-height: 340px; }
  .content              { padding: 14px 16px; gap: 14px; }
  .topbar               { padding: 0 16px; }
  .topbar-left          { gap: 12px; }
  .incident-num         { font-size: 20px; }
  .topbar-vehicle       { font-size: 13px; }
  .topbar-pills         { flex-wrap: wrap; gap: 4px; }
  .total-bar-val        { font-size: 24px; }
  .breakdown-total-val  { font-size: 16px; }
}

/* Large phone / small tablet  ≤ 680px */
@media (max-width: 680px) {
  /* Show hamburger button */
  .hamburger-btn            { display: flex; }
  /* Sidebar becomes a fixed off-canvas drawer, hidden off-screen by default */
  .sidebar                  { position: fixed; left: 0; top: 0; bottom: 0; z-index: 150;
                               width: 260px; transform: translateX(-100%);
                               transition: transform 0.25s ease; }
  /* Topbar */
  .topbar                   { height: auto; min-height: 64px; padding: 10px 14px;
                               flex-wrap: wrap; gap: 8px; }
  .topbar-left              { flex-wrap: wrap; gap: 8px; }
  .topbar-divider           { display: none; }
  .incident-num             { font-size: 18px; }
  .topbar-vehicle           { font-size: 12.5px; }
  /* Progress tabs: wrap instead of horizontal scroll */
  .progress-tabs            { overflow-x: visible; flex-wrap: wrap; padding: 4px 12px; gap: 2px; }
  .ptab                     { white-space: normal; flex-shrink: 1; height: auto;
                               padding: 8px 10px; font-size: 11.5px; line-height: 1.3; }
  .content                  { padding: 12px; gap: 12px; }
  .total-bar                { flex-direction: column; align-items: flex-start; gap: 10px; }
  .total-bar-val            { font-size: 22px; }
  .fb-popover               { width: calc(100vw - 24px); max-width: 320px; }
  .rates-fab                { padding: 14px 8px; }
}

/* Phone  ≤ 480px */
@media (max-width: 480px) {
  .four-col             { grid-template-columns: 1fr; }
  .photo-grid           { grid-template-columns: repeat(2, 1fr); }
  .photo-grid-body      { max-height: 260px; }
  .content              { padding: 10px; gap: 10px; }
  .topbar               { padding: 8px 12px; }
  .incident-num         { font-size: 16px; }
  .topbar-vehicle       { font-size: 12px; }
  .topbar-right         { width: 100%; justify-content: flex-start; }
  .total-bar            { padding: 14px 16px; }
  .total-bar-val        { font-size: 20px; }
  .card-head            { flex-wrap: wrap; gap: 6px; padding: 10px 14px; }
  .breakdown-card-head  { flex-wrap: wrap; gap: 4px; height: auto; padding: 8px 12px; min-height: 48px; }
  .table-wrap           { -webkit-overflow-scrolling: touch; }
  .rates-fab            { display: none; }
  .progress-tabs        { overflow-x: visible; flex-wrap: wrap; padding: 4px 8px; }
  .ptab                 { white-space: normal; flex-shrink: 1; height: auto;
                           padding: 6px 8px; font-size: 11px; }
}
--------------------------
Section 2 — HTML
--------------------------
2A. Right after <div class="app">, add:
<div class="sidebar-overlay" onclick="toggleSidebar()"></div>
2B. As the first child inside <div class="topbar-left">, add:
<button class="hamburger-btn" onclick="toggleSidebar()" title="Open repair list" aria-label="Toggle sidebar">
  <span></span><span></span><span></span>
</button>
2C. Update all 6 feedback buttons — replace the old SVG + text with:
<svg viewBox="0 0 14 14" fill="none"><path d="M12 1H2a1 1 0 00-1 1v7a1 1 0 001 1h2v2.5l3-2.5h5a1 1 0 001-1V2a1 1 0 00-1-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg><span class="fb-btn-text">Feedback</span>
Also add title="Feedback" to each <button class="fb-btn">.

Section 3 — JavaScript
3A. Add new function (near openPanel / closePanel):
function toggleSidebar() {
  document.querySelector('.app').classList.toggle('sidebar-open');
}
3B. Add one line at the very top of the existing selectIncident() function:
document.querySelector('.app').classList.remove('sidebar-open');
That's the complete diff — 3 CSS blocks, 3 HTML spots, 2 JS additions.
