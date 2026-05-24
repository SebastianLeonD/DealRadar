from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web_ui.components import (
    ACTION_CATALOG,
    build_clv_dataframe,
    clv_daily_summary,
    edges_to_csv,
    format_bet_clipboard,
    format_status_label,
    load_edges_dataframe,
    prizepicks_search_url,
    render_clv_table_html,
    render_edges_table_html,
    render_metric_strip,
    render_status_html,
    run_full_pipeline,
    run_script,
    pp_raw_file_exists,
)
from web_ui.styles import DESK_CSS
from storage.db_manager import DB_PATH, ingest_staging

PAGES = ['Execution', 'Active Opportunities', 'CLV Performance']


def inject_styles() -> None:
    st.markdown(DESK_CSS, unsafe_allow_html=True)


@st.dialog('Action Help', width='large')
def show_action_help(action_key: str) -> None:
    action = ACTION_CATALOG[action_key]
    st.markdown(f"### {action['title']}")
    st.code(action['command'], language='bash')
    st.markdown(action['description'])
    st.markdown(f"**API cost:** {action['api_calls']}")
    st.markdown(f"**Writes to:** `{action['writes_to']}`")


def action_button_row(action_key: str, label: str, primary: bool = False) -> bool:
    button_col, help_col = st.columns([5, 1])
    with button_col:
        clicked = st.button(
            label,
            type='primary' if primary else 'secondary',
            use_container_width=True,
            key=f'btn_{action_key}',
        )
    with help_col:
        if st.button('?', key=f'help_{action_key}', help='What does this button do?'):
            show_action_help(action_key)
    return clicked


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown('### Desk Navigation')
        page = st.radio('Section', PAGES, label_visibility='collapsed')
        st.markdown('---')
        st.markdown(
            '<div class="cell-sub">PrizePicks vs DraftKings<br>player_points · SQLite desk</div>',
            unsafe_allow_html=True,
        )
        if DB_PATH.exists():
            st.success('Database online')
        else:
            st.warning('Database not initialized')
    return page


def render_header() -> None:
    st.markdown('<div class="desk-title">Arbitrage Control Center</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="desk-subtitle">High-density line shopping · edge detection · CLV tracking</div>',
        unsafe_allow_html=True,
    )


def render_execution_page() -> None:
    dk_status, dk_detail = format_status_label('DK')
    pp_status, pp_detail = format_status_label('PP')
    st.markdown(
        render_status_html(dk_status, pp_status, DB_PATH.exists(), dk_detail, pp_detail),
        unsafe_allow_html=True,
    )

    st.caption('Edit `data/raw/prizepicks_raw.json` in your IDE, then parse from here.')

    fetch_sharp = action_button_row('fetch_sharp', 'Fetch Sharp Lines')
    parse_pp = action_button_row('parse_pp', 'Parse PrizePicks')
    run_matcher = action_button_row('run_matcher', 'Run Edge Detection')
    run_all = action_button_row('run_full', 'Run Full Pipeline', primary=True)

    log_box = st.empty()

    if fetch_sharp:
        with st.spinner('Fetching DraftKings sharp lines...'):
            success, output = run_script('scrapers/draftkings_api.py')
            if success:
                ingest_staging()
            log_box.code(output or 'DraftKings scrape complete.')
            st.success('Sharp lines updated.') if success else st.error('DraftKings scrape failed.')

    if parse_pp:
        if not pp_raw_file_exists():
            st.error('Missing data/raw/prizepicks_raw.json — save your PP dump in the editor first.')
        else:
            with st.spinner('Parsing PrizePicks board...'):
                success, output = run_script('scrapers/prizepicks_api.py')
                if success:
                    ingest_staging()
                log_box.code(output or 'PrizePicks parse complete.')
                st.success('PrizePicks board parsed.') if success else st.error('PrizePicks parse failed.')

    if run_matcher:
        with st.spinner('Running edge detection...'):
            from engine.matcher import find_edges

            ingest_staging()
            flagged = find_edges(sync_staging=False)
            log_box.code(f'Found {len(flagged)} advantageous play(s).')
            st.success(f'Logged {len(flagged)} edge(s).')

    if run_all:
        with st.spinner('Running full pipeline...'):
            success, output = run_full_pipeline()
            log_box.code(output)
            st.success('Full pipeline complete.') if success else st.error('Pipeline failed.')


def render_opportunities_page() -> None:
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        stat_filter = st.selectbox('Stat', ['All', 'player_points'], index=1)
    with filter_col2:
        edge_filter = st.selectbox(
            'Edge Type',
            ['All', 'Line Discrepancy', '+EV Odds Juice'],
        )

    edges = load_edges_dataframe(stat_filter, edge_filter)

    legend_html = """
    <div class="data-table-header">
        <div class="data-table-title">Active Opportunities</div>
        <div class="legend">
            <span class="legend-item legend-cyan">Line Discrepancy</span>
            <span class="legend-item legend-purple">+EV Odds Juice</span>
        </div>
    </div>
    """
    st.markdown(legend_html, unsafe_allow_html=True)

    if edges.empty:
        st.markdown(render_edges_table_html(edges), unsafe_allow_html=True)
        return

    line_count = int((edges['edge_type'] == 'Line Discrepancy').sum())
    ev_count = int((edges['edge_type'] == '+EV Odds Juice').sum())

    st.markdown(
        render_metric_strip([
            ('Unique Signals', str(len(edges))),
            ('Line Discrepancy', str(line_count)),
            ('+EV Juice', str(ev_count)),
        ]),
        unsafe_allow_html=True,
    )
    st.markdown(render_edges_table_html(edges), unsafe_allow_html=True)

    st.download_button(
        'Download Edges CSV',
        data=edges_to_csv(edges),
        file_name='edges.csv',
        mime='text/csv',
    )

    selected_player = st.selectbox('Quick copy / search', edges['player'].tolist())
    if selected_player:
        row = edges.loc[edges['player'] == selected_player].iloc[0]
        st.code(format_bet_clipboard(row), language=None)
        st.link_button('Search PrizePicks', prizepicks_search_url(selected_player))


def render_clv_page() -> None:
    st.markdown(
        """
        <div class="data-table-header">
            <div class="data-table-title">CLV Performance</div>
            <div class="legend">
                <span class="legend-item legend-cyan">Line Discrepancy</span>
                <span class="legend-item legend-purple">+EV Odds Juice</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    refresh = action_button_row('refresh_clv', 'Refresh CLV')
    clv_frame = build_clv_dataframe(sync_staging=refresh)

    if clv_frame.empty:
        st.markdown(render_clv_table_html(clv_frame), unsafe_allow_html=True)
        return

    positive = int((clv_frame['clv'] > 0).sum())
    avg_clv = round(clv_frame['clv'].mean(), 2)

    st.markdown(
        render_metric_strip([
            ('Unique Edges', str(len(clv_frame))),
            ('Positive CLV', f'{positive}/{len(clv_frame)}'),
            ('Average CLV', str(avg_clv)),
        ]),
        unsafe_allow_html=True,
    )

    daily = clv_daily_summary(clv_frame)
    if not daily.empty:
        st.markdown('#### Average CLV (Last 7 Days)')
        st.bar_chart(daily.set_index('date')['avg_clv'])

    st.markdown(render_clv_table_html(clv_frame), unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title='Arbitrage Control Center',
        page_icon='📊',
        layout='wide',
        initial_sidebar_state='expanded',
    )
    inject_styles()
    active_page = render_sidebar()
    render_header()

    if active_page == 'Execution':
        render_execution_page()
    elif active_page == 'Active Opportunities':
        render_opportunities_page()
    else:
        render_clv_page()


if __name__ == '__main__':
    main()
