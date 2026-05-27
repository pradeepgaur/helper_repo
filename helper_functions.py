
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CDR Assistant — UI Integration Changes</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; color: #1a1a2e; background: #fff; padding: 40px; max-width: 900px; margin: 0 auto; }

  h1 { font-size: 22px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
  .subtitle { font-size: 13px; color: #64748b; margin-bottom: 36px; }

  h2 { font-size: 15px; font-weight: 700; color: #0f172a; margin: 32px 0 12px; padding: 8px 14px; background: #f1f5f9; border-left: 4px solid #3b82f6; border-radius: 0 6px 6px 0; }
  h3 { font-size: 13px; font-weight: 600; color: #334155; margin: 20px 0 8px; }

  p { color: #475569; line-height: 1.6; margin-bottom: 10px; }

  pre { background: #0f172a; color: #e2e8f0; font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size: 12px; line-height: 1.6; padding: 16px 18px; border-radius: 8px; overflow-x: auto; margin: 8px 0 16px; white-space: pre-wrap; word-break: break-word; }

  .tag { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 20px; margin-right: 6px; vertical-align: middle; }
  .tag.css  { background: #dbeafe; color: #1d4ed8; }
  .tag.html { background: #dcfce7; color: #15803d; }
  .tag.js   { background: #fef9c3; color: #a16207; }

  .note { background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 10px 14px; font-size: 12.5px; color: #92400e; margin-bottom: 16px; }
  .note strong { color: #78350f; }

  .section-block { border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px 24px; margin-bottom: 24px; }

  .divider { border: none; border-top: 1px solid #e2e8f0; margin: 28px 0; }

  table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin: 10px 0 16px; }
  th { background: #f8fafc; font-weight: 600; text-align: left; padding: 8px 12px; border: 1px solid #e2e8f0; color: #334155; }
  td { padding: 8px 12px; border: 1px solid #e2e8f0; color: #475569; vertical-align: top; }

  @media print {
    body { padding: 20px; }
    pre { font-size: 11px; }
    h2 { break-before: auto; }
    .section-block { break-inside: avoid; }
  }
</style>
</head>
<body>

<h1>CDR Assistant — UI Integration Changes</h1>
<p class="subtitle">Responsive layout, hamburger sidebar, feedback button redesign &amp; breakdown row fixes &nbsp;·&nbsp; Generated 2026-05-14</p>

<!-- SUMMARY TABLE -->
<table>
  <thead>
    <tr><th>Area</th><th>What changed</th><th>Type</th></tr>
  </thead>
  <tbody>
    <tr><td>Sidebar (mobile)</td><td>Hidden behind a hamburger icon; slides in as a drawer overlay</td><td><span class="tag css">CSS</span><span class="tag html">HTML</span><span class="tag js">JS</span></td></tr>
    <tr><td>Progress tabs</td><td>Wrap to multiple lines on small screens instead of scrolling</td><td><span class="tag css">CSS</span></td></tr>
    <tr><td>Breakdown rows</td><td>AI Flagged / AI Validated pills no longer clipped by card overflow</td><td><span class="tag css">CSS</span></td></tr>
    <tr><td>Feedback button</td><td>Icon + text on desktop; icon-only (28 px square) on ≤ 1200 px</td><td><span class="tag css">CSS</span><span class="tag html">HTML</span></td></tr>
  </tbody>
</table>

<hr class="divider">

<!-- ═══ SECTION 1: CSS ═══ -->
<h2><span class="tag css">CSS</span> Section 1 — Stylesheet changes</h2>

<div class="section-block">
  <h3>1A &nbsp;·&nbsp; Modify existing <code>.fb-btn</code> rule</h3>
  <p>Add <code>flex-shrink: 0</code> to the existing rule so the button is never squeezed on narrow layouts.</p>
  <pre>.fb-btn { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 500;
  color: var(--text-3); background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 8px; padding: 4px 9px; cursor: pointer; transition: all 0.15s;
  white-space: nowrap; font-family: var(--font); flex-shrink: 0; }</pre>
</div>

<div class="section-block">
  <h3>1B &nbsp;·&nbsp; Add new block — paste immediately before <code>/* ─── RESPONSIVE ─── */</code></h3>
  <pre>/* ─── HAMBURGER / SIDEBAR DRAWER ─── */
.hamburger-btn { display: none; background: none; border: none; cursor: pointer;
  padding: 6px 8px; flex-direction: column; gap: 5px; align-items: center;
  justify-content: center; flex-shrink: 0; border-radius: 6px; }
.hamburger-btn:hover { background: var(--surface-2); }
.hamburger-btn span { display: block; width: 20px; height: 2px; background: var(--text-2);
  border-radius: 2px; transition: background 0.15s; }
.hamburger-btn:hover span { background: var(--text-1); }
.sidebar-overlay { display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.45); z-index: 149; cursor: pointer; }
.app.sidebar-open .sidebar-overlay { display: block; }
.app.sidebar-open .sidebar { transform: translateX(0) !important;
  box-shadow: 4px 0 24px rgba(0,0,0,0.22); }</pre>
</div>

<div class="section-block">
  <h3>1C &nbsp;·&nbsp; Replace the entire <code>/* ─── RESPONSIVE ─── */</code> block with the following</h3>
  <pre>/* ─── RESPONSIVE ─── */

/* Compact laptop / landscape tablet  ≤ 1200px */
@media (max-width: 1200px) {
  .four-col             { grid-template-columns: repeat(2, 1fr); }
  .content              { padding: 18px 22px; gap: 16px; }
  .topbar               { padding: 0 22px; }
  /* Feedback button: icon-only on narrower cards */
  .fb-btn               { padding: 5px; width: 28px; height: 28px;
                           justify-content: center; gap: 0; }
  .fb-btn-text          { display: none; }
  /* Card heads: let feedback button wrap below title if too wide */
  .card-head            { flex-wrap: wrap; gap: 4px; height: auto;
                           min-height: 48px; padding: 10px 16px; }
  .breakdown-card-head  { flex-wrap: wrap; gap: 4px; height: auto;
                           min-height: 44px; padding: 8px 14px; }
  /* Breakdown rows: pill wraps to next line rather than being clipped */
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
  /* Sidebar: fixed off-canvas drawer, hidden off-screen by default */
  .sidebar                  { position: fixed; left: 0; top: 0; bottom: 0;
                               z-index: 150; width: 260px;
                               transform: translateX(-100%);
                               transition: transform 0.25s ease; }
  /* Topbar */
  .topbar                   { height: auto; min-height: 64px; padding: 10px 14px;
                               flex-wrap: wrap; gap: 8px; }
  .topbar-left              { flex-wrap: wrap; gap: 8px; }
  .topbar-divider           { display: none; }
  .incident-num             { font-size: 18px; }
  .topbar-vehicle           { font-size: 12.5px; }
  /* Progress tabs: wrap to multiple lines */
  .progress-tabs            { overflow-x: visible; flex-wrap: wrap;
                               padding: 4px 12px; gap: 2px; }
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
  .breakdown-card-head  { flex-wrap: wrap; gap: 4px; height: auto;
                           padding: 8px 12px; min-height: 48px; }
  .table-wrap           { -webkit-overflow-scrolling: touch; }
  .rates-fab            { display: none; }
  .progress-tabs        { overflow-x: visible; flex-wrap: wrap; padding: 4px 8px; }
  .ptab                 { white-space: normal; flex-shrink: 1; height: auto;
                           padding: 6px 8px; font-size: 11px; }
}</pre>
</div>

<hr class="divider">

<!-- ═══ SECTION 2: HTML ═══ -->
<h2><span class="tag html">HTML</span> Section 2 — HTML changes</h2>

<div class="section-block">
  <h3>2A &nbsp;·&nbsp; Sidebar backdrop overlay — add immediately after <code>&lt;div class="app"&gt;</code></h3>
  <pre>&lt;div class="sidebar-overlay" onclick="toggleSidebar()"&gt;&lt;/div&gt;</pre>
</div>

<div class="section-block">
  <h3>2B &nbsp;·&nbsp; Hamburger button — add as the <strong>first child</strong> inside <code>&lt;div class="topbar-left"&gt;</code></h3>
  <pre>&lt;button class="hamburger-btn" onclick="toggleSidebar()"
        title="Open repair list" aria-label="Toggle sidebar"&gt;
  &lt;span&gt;&lt;/span&gt;&lt;span&gt;&lt;/span&gt;&lt;span&gt;&lt;/span&gt;
&lt;/button&gt;</pre>
</div>

<div class="section-block">
  <h3>2C &nbsp;·&nbsp; Feedback buttons (all 6 instances) — replace the contents of every <code>&lt;button class="fb-btn"&gt;</code></h3>
  <p>Also add <code>title="Feedback"</code> to each button's opening tag.</p>
  <p><strong>New inner content for every fb-btn:</strong></p>
  <pre>&lt;svg viewBox="0 0 14 14" fill="none"&gt;
  &lt;path d="M12 1H2a1 1 0 00-1 1v7a1 1 0 001 1h2v2.5l3-2.5h5a1 1 0 001-1V2a1 1 0 00-1-1z"
        stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/&gt;
&lt;/svg&gt;
&lt;span class="fb-btn-text"&gt;Feedback&lt;/span&gt;</pre>

  <p>Opening tag becomes:</p>
  <pre>&lt;button class="fb-btn" title="Feedback" onclick="openFeedback(event, '...')"&gt;</pre>
</div>

<hr class="divider">

<!-- ═══ SECTION 3: JS ═══ -->
<h2><span class="tag js">JS</span> Section 3 — JavaScript changes</h2>

<div class="section-block">
  <h3>3A &nbsp;·&nbsp; New function — add near <code>openPanel()</code> / <code>closePanel()</code></h3>
  <pre>// ─── Sidebar drawer (mobile) ──────────────────────────────────────────────────
function toggleSidebar() {
  document.querySelector('.app').classList.toggle('sidebar-open');
}</pre>
</div>

<div class="section-block">
  <h3>3B &nbsp;·&nbsp; Auto-close drawer on selection — add as the <strong>first line</strong> inside <code>selectIncident()</code></h3>
  <pre>document.querySelector('.app').classList.remove('sidebar-open');</pre>
</div>

<hr class="divider">
<p style="font-size:12px;color:#94a3b8;text-align:center;">CDR Assistant · UI handoff document · pradeepsingh.gaur@wwt.com</p>

</body>
</html>
