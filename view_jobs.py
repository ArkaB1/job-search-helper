import os
import sqlite3
import webbrowser
import html
import hashlib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "jobs.db")
HTML_PATH = os.path.join(SCRIPT_DIR, "job_tracker.html")


def fetch_jobs():
    """Retrieves approved and rejected jobs from SQLite DB."""
    if not os.path.exists(DB_PATH):
        print(f"⚠️ Database not found at {DB_PATH}")
        return [], []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, company, location, stipend, experience, match_score AS score,
               verdict, reasoning, responsibilities,
               COALESCE(link, url) AS link, raw_text, created_at AS evaluated_at,
               contact_email, contact_phone, apply_form_link
        FROM evaluated_jobs
        WHERE lower(verdict) = 'apply' OR match_score >= 65
        ORDER BY match_score DESC, created_at DESC
    """)
    approved = cursor.fetchall()

    cursor.execute("""
        SELECT title, company, location, match_score AS score, verdict, reasoning,
               COALESCE(link, url) AS link, raw_text, created_at AS evaluated_at
        FROM evaluated_jobs
        WHERE lower(verdict) != 'apply' AND (match_score < 65 OR match_score IS NULL)
        ORDER BY created_at DESC
    """)
    rejected = cursor.fetchall()

    conn.close()
    return approved, rejected


def _job_id(row):
    """Stable id for a job so the 'applied' state survives regeneration."""
    basis = (row["link"] or "") + "|" + (row["title"] or "")
    return hashlib.md5(basis.encode("utf-8")).hexdigest()[:12]


def _esc(value):
    return html.escape(str(value)) if value else ""


def render_approved_row(row):
    jid = _job_id(row)
    score = row["score"] if row["score"] is not None else 0
    title = _esc(row["title"] or "Untitled Role")
    company = _esc(row["company"] or "Unknown Company")
    location = _esc(row["location"] or "Unspecified Location")
    link = row["link"] or ""

    stipend = row["stipend"] if "stipend" in row.keys() else None

    # 🎯 REAL RUPEE SYMBOL REPLACEMENT 🎯
    stipend_tag = f'<span class="tag tag-purple"><strong style="font-size:12px; margin-right:3px;">₹</strong>{_esc(stipend)}</span>' if stipend and stipend != "N/A" else ""

    experience = row["experience"] if "experience" in row.keys() else None
    exp_tag = f'<span class="tag tag-blue"><i class="ti ti-briefcase"></i> {_esc(experience)}</span>' if experience and experience != "N/A" else ""

    loc_tag = f'<span class="tag tag-rose"><i class="ti ti-map-pin"></i> {location}</span>'

    email = row["contact_email"] if "contact_email" in row.keys() else None
    phone = row["contact_phone"] if "contact_phone" in row.keys() else None
    form = row["apply_form_link"] if "apply_form_link" in row.keys() else None
    responsibilities = row["responsibilities"] if "responsibilities" in row.keys() else None
    raw_text = row["raw_text"] or ""

    contact_bits = []
    if email and email != "N/A":
        contact_bits.append(f'<span class="tag tag-teal"><i class="ti ti-mail"></i> {_esc(email)}</span>')
    if phone and phone != "N/A":
        contact_bits.append(f'<span class="tag tag-indigo"><i class="ti ti-phone"></i> {_esc(phone)}</span>')
    if form and form != "N/A":
        contact_bits.append(
            f'<span class="tag tag-amber"><i class="ti ti-link"></i> <a href="{_esc(form)}" target="_blank" style="color:inherit;text-decoration:none;">Apply Form</a></span>')

    contact_html = "".join(
        contact_bits) if contact_bits else '<span class="text-muted" style="font-size:11px;">No contacts extracted</span>'

    return f"""
    <div class="job-card" id="row-{jid}">
        <div class="card-inner">
            <div class="header-line">
                <span class="score-badge {'high' if score >= 80 else 'mid'}">{score}</span>
                <div class="title-wrap">
                    <h3 class="job-title">{title}</h3>
                    <div class="company-name">{company}</div>
                </div>
                <div class="controls-wrap">
                    <button class="maroon-dot inline-dot" onclick="toggleSuperCollapse('{jid}')" title="Hide Completely"></button>
                    <label class="switch" title="Show / hide details">
                        <input type="checkbox" class="vis-toggle" checked onchange="toggleVisible('{jid}')">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>

            <div class="expanded-content">
                <div class="tag-row">
                    <div class="tag-group">{loc_tag}{exp_tag}{stipend_tag}</div>
                    <div class="tag-group" style="border-left: 1px solid #e2e8f0; padding-left: 12px;">{contact_html}</div>
                </div>

                {"<div class='responsibilities'>" + _esc(responsibilities) + "</div>" if responsibilities and responsibilities != "N/A" else ""}

                <details class="raw-text-dropdown">
                    <summary><i class="ti ti-file-text"></i> View Original Post Text</summary>
                    <div class="raw-content">{_esc(raw_text)}</div>
                </details>

                <div class="card-actions">
                    <a href="{_esc(link)}" target="_blank" class="btn btn-post"><i class="ti ti-external-link"></i> View Post</a>
                </div>
            </div>
        </div>
        <button class="maroon-dot-restore" onclick="toggleSuperCollapse('{jid}')" title="Restore Job"></button>
    </div>
    """


def render_rejected_row(row):
    score = row["score"] if row["score"] is not None else 0
    link = row["link"] or ""
    raw_text = _esc(row['raw_text'] or "No text available.")

    # Hover Tooltip Implementation
    hover_html = f"""
    <div class="hover-wrapper">
        <span class="hover-trigger"><i class="ti ti-eye"></i> Read Post</span>
        <div class="hover-popover">
            <div class="popover-header">
                Original Post Snippet
                <a href="{_esc(link)}" target="_blank" class="popover-link">Open Link ↗</a>
            </div>
            <div class="popover-body">{raw_text}</div>
        </div>
    </div>
    """

    return f"""
    <tr>
      <td><span class="score-badge low">{score}</span></td>
      <td class="td-title">{_esc(row['title'] or 'Untitled role')}</td>
      <td class="td-company">{_esc(row['company'] or 'Unknown')}</td>
      <td class="text-muted" style="font-size:12px;">{_esc(row['reasoning'] or '')}</td>
      <td style="text-align:right;">{hover_html}</td>
    </tr>
    """


def generate_html():
    approved_jobs, rejected_jobs = fetch_jobs()

    approved_html = "".join(render_approved_row(j) for j in approved_jobs) if approved_jobs else \
        "<div class='empty-state'>No matching opportunities found yet.</div>"

    rejected_html = "".join(render_rejected_row(j) for j in rejected_jobs) if rejected_jobs else \
        "<tr><td colspan='5' class='empty-state'>No skipped posts recorded.</td></tr>"

    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Job Intelligence Dashboard</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/2.44.0/iconfont/tabler-icons.min.css">
<style>
    :root {{
        --bg: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --border-hover: #cbd5e1;

        --text-main: #0f172a;
        --text-secondary: #475569;
        --text-muted: #94a3b8;

        --primary: #2563eb;
        --primary-hover: #1d4ed8;

        /* Multi-Color Palette */
        --c-green-bg: #dcfce7; --c-green-txt: #166534;
        --c-amber-bg: #fef3c7; --c-amber-txt: #92400e;
        --c-red-bg: #fee2e2;   --c-red-txt: #991b1b;
        --c-purple-bg: #f3e8ff; --c-purple-txt: #6b21a8;
        --c-blue-bg: #dbeafe;  --c-blue-txt: #1e40af;
        --c-rose-bg: #ffe4e6;  --c-rose-txt: #9f1239;
        --c-teal-bg: #ccfbf1;  --c-teal-txt: #115e59;
        --c-indigo-bg: #e0e7ff; --c-indigo-txt: #3730a3;
    }}

    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text-main); margin: 0; padding: 20px 40px; -webkit-font-smoothing: antialiased; }}
    .wrap {{ max-width: 1300px; margin: 0 auto; }}

    /* Header */
    .topbar {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 24px; border-bottom: 2px solid var(--border); padding-bottom: 16px; }}
    .topbar h1 {{ margin: 0; font-size: 22px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 8px; letter-spacing: -0.5px; }}
    .topbar h1 i {{ color: var(--primary); font-size: 24px; }}
    .topbar .timestamp {{ font-size: 12px; color: var(--text-muted); font-family: monospace; }}

    .section-title {{ font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin: 30px 0 12px 0; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }}
    .section-title .count {{ background: var(--border); padding: 2px 8px; border-radius: 12px; font-size: 11px; color: var(--text-main); }}

    /* COMPACT JOB CARDS */
    .job-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); transition: border-color 0.2s; position: relative; overflow: hidden; }}
    .job-card:hover {{ border-color: var(--border-hover); box-shadow: 0 4px 6px rgba(0,0,0,0.04); }}

    /* ALIGN TOGGLE TO TOP RIGHT */
    .header-line {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }}
    .title-wrap {{ flex: 1; min-width: 0; margin-top: -2px; }}
    .controls-wrap {{ display: flex; align-items: center; gap: 14px; margin-top: 2px; }}

    .job-card.collapsed {{ padding: 8px 16px; }}
    .job-card.collapsed .header-line {{ margin-bottom: 0; align-items: center; }}
    .job-card.collapsed .title-wrap {{ margin-top: 0; }}
    .job-card.collapsed .score-badge, .job-card.collapsed .company-name, .job-card.collapsed .expanded-content {{ display: none; }}
    .job-card.collapsed .job-title {{ font-size: 12.5px; font-weight: 500; color: var(--text-muted); margin: 0; text-decoration: line-through; opacity: 0.7; }}

    /* MAROON DOT BUTTONS */
    .inline-dot {{
        display: none;
        width: 14px; height: 14px; border-radius: 50%;
        background-color: #991b1b; /* Solid Maroon */
        border: none; cursor: pointer; padding: 0;
        transition: transform 0.2s ease, background-color 0.2s;
    }}
    .inline-dot:hover {{ background-color: #7f1d1d; transform: scale(1.15); }}

    /* Only show inline dot when card is collapsed */
    .job-card.collapsed .inline-dot {{ display: block; }}

    .maroon-dot-restore {{
        display: none;
        width: 14px; height: 14px; border-radius: 50%;
        background-color: rgba(153, 27, 27, 0.25); /* Translucent Maroon */
        border: none; cursor: pointer; padding: 0;
        transition: all 0.2s ease;
    }}
    .maroon-dot-restore:hover {{ background-color: rgba(153, 27, 27, 0.6); transform: scale(1.15); }}

    /* SUPER COLLAPSED STATE */
    .job-card.super-collapsed {{
        padding: 6px 8px; /* Absolute minimum size */
        margin-bottom: 4px;
        border: none;
        background: transparent;
        box-shadow: none;
        width: fit-content;
    }}
    .job-card.super-collapsed .card-inner {{ display: none; }}
    .job-card.super-collapsed .maroon-dot-restore {{ display: block; }}

    /* iOS-style toggle switch */
    .switch {{ position: relative; display: inline-block; width: 38px; height: 21px; flex-shrink: 0; cursor: pointer; }}
    .switch input {{ opacity: 0; width: 0; height: 0; }}
    .switch .slider {{ position: absolute; inset: 0; background: #d1d5db; border-radius: 999px; transition: background 0.2s; }}
    .switch .slider::before {{ content: ""; position: absolute; width: 15px; height: 15px; left: 3px; top: 3px; background: #ffffff; border-radius: 50%; box-shadow: 0 1px 2px rgba(0,0,0,0.25); transition: transform 0.2s; }}
    .switch input:checked + .slider {{ background: #34c759; }}
    .switch input:checked + .slider::before {{ transform: translateX(17px); }}

    .score-badge {{ padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; font-family: monospace; text-align: center; border: 1px solid transparent; }}
    .score-badge.high {{ background: var(--c-green-bg); color: var(--c-green-txt); border-color: rgba(22, 101, 52, 0.2); }}
    .score-badge.mid {{ background: var(--c-amber-bg); color: var(--c-amber-txt); border-color: rgba(146, 64, 14, 0.2); }}
    .score-badge.low {{ background: var(--c-red-bg); color: var(--c-red-txt); border-color: rgba(153, 27, 27, 0.2); }}

    .job-title {{ font-size: 15px; font-weight: 600; margin: 0 0 4px 0; color: var(--text-main); line-height: 1.2; }}
    .company-name {{ font-size: 13px; font-weight: 500; color: var(--text-secondary); }}

    /* Multi-Colored Tags */
    .tag-row {{ display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
    .tag-group {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
    .tag {{ display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 5px; font-size: 11px; font-weight: 600; border: 1px solid transparent; }}
    .tag i {{ font-size: 13px; opacity: 0.8; }}

    .tag-purple {{ background: var(--c-purple-bg); color: var(--c-purple-txt); border-color: rgba(107, 33, 168, 0.15); }}
    .tag-blue {{ background: var(--c-blue-bg); color: var(--c-blue-txt); border-color: rgba(30, 64, 175, 0.15); }}
    .tag-rose {{ background: var(--c-rose-bg); color: var(--c-rose-txt); border-color: rgba(159, 18, 57, 0.15); }}
    .tag-teal {{ background: var(--c-teal-bg); color: var(--c-teal-txt); border-color: rgba(17, 94, 89, 0.15); }}
    .tag-indigo {{ background: var(--c-indigo-bg); color: var(--c-indigo-txt); border-color: rgba(55, 48, 163, 0.15); }}
    .tag-amber {{ background: var(--c-amber-bg); color: var(--c-amber-txt); border-color: rgba(146, 64, 14, 0.15); }}

    .responsibilities {{ font-size: 13px; color: var(--text-secondary); line-height: 1.5; background: #f8fafc; padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border); margin-bottom: 10px; white-space: pre-line; }}

    /* Buttons */
    .card-actions {{ display: flex; gap: 8px; margin-top: 10px; }}
    .btn {{ font-family: inherit; display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; text-decoration: none; transition: 0.2s; border: 1px solid transparent; }}
    .btn-apply {{ background: var(--surface); border-color: var(--border); color: var(--text-secondary); }}
    .btn-apply:hover {{ border-color: var(--c-green-txt); color: var(--c-green-txt); background: var(--c-green-bg); }}
    .btn-post {{ background: var(--primary); color: white; }}
    .btn-post:hover {{ background: var(--primary-hover); }}

    /* Raw Text Accordion */
    .raw-text-dropdown summary {{ font-size: 12px; font-weight: 600; color: var(--text-muted); cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: 4px; transition: color 0.2s; }}
    .raw-text-dropdown summary:hover {{ color: var(--primary); }}
    .raw-content {{ margin-top: 8px; font-size: 11.5px; color: var(--text-secondary); background: #f1f5f9; padding: 12px; border-radius: 6px; white-space: pre-wrap; font-family: 'SFMono-Regular', Consolas, monospace; max-height: 200px; overflow-y: auto; border: 1px solid var(--border); line-height: 1.4; }}

    /* Skipped Table */
    table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; font-size: 13px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
    th, td {{ padding: 10px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
    th {{ background: #f8fafc; color: var(--text-muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f8fafc; }}
    .td-title {{ font-weight: 600; color: var(--text-main); max-width: 250px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .td-company {{ color: var(--text-secondary); font-weight: 500; max-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .text-muted {{ color: var(--text-muted); }}

    /* 🏎️ HOVER-TO-READ MAGIC */
    .hover-wrapper {{ position: relative; display: inline-flex; justify-content: flex-end; width: 100%; }}
    .hover-trigger {{ font-size: 12px; font-weight: 600; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 4px; }}
    .hover-trigger:hover {{ background: #eff6ff; }}

    .hover-popover {{ 
        visibility: hidden; opacity: 0; position: absolute; right: 0; bottom: calc(100% + 5px); 
        width: 450px; background: var(--surface); border: 1px solid var(--border); 
        border-radius: 8px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1); 
        z-index: 100; transition: all 0.2s ease; transform: translateY(5px); text-align: left;
    }}
    .hover-popover::after {{ content: ''; position: absolute; top: 100%; right: 0; width: 100px; height: 15px; background: transparent; }}
    .hover-wrapper:hover .hover-popover, .hover-popover:hover {{ visibility: visible; opacity: 1; transform: translateY(0); }}

    .popover-header {{ padding: 10px 15px; border-bottom: 1px solid var(--border); background: #f8fafc; border-radius: 8px 8px 0 0; font-size: 12px; font-weight: 600; color: var(--text-secondary); display: flex; justify-content: space-between; align-items: center; }}
    .popover-link {{ color: var(--primary); text-decoration: none; background: #eff6ff; padding: 3px 8px; border-radius: 4px; }}
    .popover-link:hover {{ background: #dbeafe; }}
    .popover-body {{ padding: 15px; max-height: 250px; overflow-y: auto; color: var(--text-secondary); font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11.5px; line-height: 1.5; white-space: pre-wrap; }}

    /* Scrollbars */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1><i class="ti ti-briefcase"></i> Job Intelligence Dashboard</h1>
    <span class="timestamp">SYNCED: {updated}</span>
  </div>

  <div class="section-title"><i class="ti ti-target" style="color:var(--c-green-txt);"></i> Highly Relevant Opportunities <span class="count">{len(approved_jobs)}</span></div>
  <div class="rows">
    {approved_html}
  </div>

  <div class="section-title" style="margin-top: 40px;"><i class="ti ti-filter-off" style="color:var(--c-red-txt);"></i> Filtered / Skipped Posts <span class="count">{len(rejected_jobs)}</span></div>
  <table>
    <thead><tr><th>Score</th><th>Role Title</th><th>Company</th><th>Reason Filtered</th><th style="text-align:right;">Raw Data</th></tr></thead>
    <tbody>{rejected_html}</tbody>
  </table>
</div>
<script>
function toggleVisible(id) {{
  var card = document.getElementById('row-' + id);
  var checked = card.querySelector('.vis-toggle').checked;
  card.classList.toggle('collapsed', !checked);

  var hidden = JSON.parse(localStorage.getItem('hidden_jobs') || '{{}}');
  if (!checked) {{ hidden[id] = true; }} else {{ delete hidden[id]; }}
  localStorage.setItem('hidden_jobs', JSON.stringify(hidden));
}}

function toggleSuperCollapse(id) {{
  var card = document.getElementById('row-' + id);
  card.classList.toggle('super-collapsed');

  var superHidden = JSON.parse(localStorage.getItem('super_hidden_jobs') || '{{}}');
  if (card.classList.contains('super-collapsed')) {{
    superHidden[id] = true;
  }} else {{
    delete superHidden[id];
  }}
  localStorage.setItem('super_hidden_jobs', JSON.stringify(superHidden));
}}

(function restoreHidden() {{
  var hidden = JSON.parse(localStorage.getItem('hidden_jobs') || '{{}}');
  var superHidden = JSON.parse(localStorage.getItem('super_hidden_jobs') || '{{}}');

  // Restore Collapsed
  Object.keys(hidden).forEach(function(id) {{
    var card = document.getElementById('row-' + id);
    if (card) {{
      card.classList.add('collapsed');
      var chk = card.querySelector('.vis-toggle');
      if (chk) chk.checked = false;
    }}
  }});

  // Restore Super Collapsed
  Object.keys(superHidden).forEach(function(id) {{
    var card = document.getElementById('row-' + id);
    if (card) {{
      card.classList.add('super-collapsed');
      card.classList.add('collapsed'); // Ensures toggle remains off behind the scenes
      var chk = card.querySelector('.vis-toggle');
      if (chk) chk.checked = false;
    }}
  }});
}})();
</script>
</body>
</html>
"""

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✅ Generated Compact Multi-Color tracker at: {HTML_PATH}")
    webbrowser.open(f"file://{HTML_PATH}")


if __name__ == "__main__":
    generate_html()