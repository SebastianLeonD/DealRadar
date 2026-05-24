DESK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: radial-gradient(circle at top, #121722 0%, #090b10 45%, #07080c 100%);
    color: #e5e7eb;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1480px;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f131b 0%, #0a0d13 100%);
    border-right: 1px solid rgba(255,255,255,0.06);
}

[data-testid="stSidebar"] .stRadio > label {
    color: #cbd5e1;
}

h1, h2, h3, .desk-title {
    color: #f8fafc !important;
    letter-spacing: -0.02em;
}

.desk-subtitle {
    color: #94a3b8;
    margin-top: -0.5rem;
    margin-bottom: 1.25rem;
    font-size: 0.95rem;
}

.panel-card {
    background: rgba(18, 23, 34, 0.92);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    margin-bottom: 1rem;
    box-shadow: 0 10px 30px rgba(0,0,0,0.25);
}

.status-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 1rem;
}

.status-tile {
    background: #121722;
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 0.85rem 1rem;
}

.status-label {
    color: #94a3b8;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.status-value {
    font-size: 1.15rem;
    font-weight: 600;
    margin-top: 0.25rem;
}

.data-table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 0.5rem 0 1rem 0;
}

.data-table-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #f8fafc;
}

.legend {
    display: flex;
    gap: 1rem;
    align-items: center;
}

.legend-item {
    font-size: 0.82rem;
    font-weight: 600;
    padding: 0.35rem 0.7rem;
    border-radius: 999px;
    border: 1px solid transparent;
}

.legend-cyan {
    color: #22d3ee;
    background: rgba(34, 211, 238, 0.08);
    border-color: rgba(34, 211, 238, 0.25);
    box-shadow: 0 0 18px rgba(34, 211, 238, 0.12);
}

.legend-purple {
    color: #c084fc;
    background: rgba(192, 132, 252, 0.08);
    border-color: rgba(192, 132, 252, 0.25);
    box-shadow: 0 0 18px rgba(192, 132, 252, 0.12);
}

.edge-table {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
}

.edge-row {
    display: grid;
    grid-template-columns: 1.4fr 1fr 0.7fr 0.7fr 0.7fr 1fr 1.2fr;
    gap: 0.75rem;
    align-items: center;
    padding: 0.85rem 1rem;
    border-radius: 12px;
    background: rgba(17, 22, 32, 0.95);
    border: 1px solid rgba(255,255,255,0.05);
}

.edge-row.line-discrepancy {
    border-color: rgba(34, 211, 238, 0.45);
    box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.08), 0 0 24px rgba(34, 211, 238, 0.08);
}

.edge-row.ev-juice {
    border-color: rgba(192, 132, 252, 0.45);
    box-shadow: inset 0 0 0 1px rgba(192, 132, 252, 0.08), 0 0 24px rgba(192, 132, 252, 0.08);
}

.edge-head {
    display: grid;
    grid-template-columns: 1.4fr 1fr 0.7fr 0.7fr 0.7fr 1fr 1.2fr;
    gap: 0.75rem;
    padding: 0 1rem 0.35rem 1rem;
    color: #64748b;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
}

.cell-title {
    font-weight: 600;
    color: #f8fafc;
    font-size: 0.95rem;
}

.cell-sub {
    color: #64748b;
    font-size: 0.78rem;
    margin-top: 0.15rem;
}

.edge-pill {
    display: inline-block;
    padding: 0.28rem 0.55rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
}

.pill-cyan {
    color: #22d3ee;
    background: rgba(34, 211, 238, 0.12);
}

.pill-purple {
    color: #c084fc;
    background: rgba(192, 132, 252, 0.12);
}

.pill-orange {
    color: #fbbf24;
    background: rgba(251, 191, 36, 0.12);
}

.pill-play-over {
    color: #34d399;
    background: rgba(52, 211, 153, 0.12);
}

.pill-play-under {
    color: #fb7185;
    background: rgba(251, 113, 133, 0.12);
}

.metric-strip {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin: 1rem 0;
}

.metric-box {
    background: #111722;
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 0.9rem 1rem;
}

.metric-box .label {
    color: #64748b;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.metric-box .value {
    font-size: 1.4rem;
    font-weight: 700;
    margin-top: 0.2rem;
    color: #f8fafc;
}

.empty-state {
    border: 1px dashed rgba(148, 163, 184, 0.25);
    border-radius: 14px;
    padding: 2rem;
    text-align: center;
    color: #94a3b8;
    background: rgba(15, 19, 27, 0.7);
}

textarea {
    background: #0f141d !important;
    color: #e2e8f0 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
}

div[data-testid="stCodeBlock"] {
    background: #0f141d !important;
}

.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #0891b2, #06b6d4) !important;
    border: none !important;
    color: #041016 !important;
}
</style>
"""
