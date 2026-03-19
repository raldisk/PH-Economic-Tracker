"""
Philippine Economic Dashboard — Streamlit app.

Reads directly from PostgreSQL mart tables:
  marts.economic_dashboard — annual summary (metric cards)
  marts.gdp_trend          — GDP trend chart
  marts.cpi_trend          — CPI / inflation chart
  marts.remittance_trend   — OFW remittance trend chart

Run locally:
  streamlit run dashboard/app.py

Run via Docker:
  docker compose up streamlit
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Philippine Economic Dashboard",
    page_icon="🇵🇭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── DB connection ─────────────────────────────────────────────────────────────

DSN = os.environ.get(
    "PH_TRACKER_POSTGRES_DSN",
    "postgresql://tracker:tracker@localhost:5432/ph_economic",
)

COLORS = {
    "gdp":        "#185FA5",
    "gdp_growth": "#1D9E75",
    "cpi":        "#BA7517",
    "inflation":  "#E24B4A",
    "remittance": "#533AB7",
    "remit_pct":  "#0F6E56",
    "neutral":    "#888780",
}


@st.cache_data(ttl=300)
def _query(sql: str) -> pd.DataFrame:
    """Execute a SQL query and return a pandas DataFrame. Cached for 5 min."""
    try:
        conn = psycopg2.connect(DSN)
        df = pd.read_sql(sql, conn)
        conn.close()
        return df
    except Exception as exc:
        st.error(f"Database connection failed: {exc}")
        return pd.DataFrame()


def _format_bn(val: float | None) -> str:
    if val is None:
        return "—"
    return f"${val:,.1f}B"


def _format_pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


def _delta_color(val: float | None) -> str:
    if val is None:
        return "off"
    return "normal" if val >= 0 else "inverse"


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/9/99/Flag_of_the_Philippines.svg", width=80)
    st.title("🇵🇭 PH Economic Tracker")
    st.caption("Data: PSA · World Bank · BSP")
    st.divider()

    year_min = st.slider("Start year", min_value=2000, max_value=2023, value=2005)
    year_max = st.slider("End year",   min_value=2001, max_value=2024, value=2024)

    if year_min >= year_max:
        st.warning("Start year must be before end year.")

    st.divider()
    refresh = st.button("🔄 Refresh data", use_container_width=True)
    if refresh:
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Showing {year_min}–{year_max}")

# ── Load data ─────────────────────────────────────────────────────────────────

dashboard_df = _query(f"""
    SELECT * FROM marts.economic_dashboard
    WHERE period_year BETWEEN {year_min} AND {year_max}
    ORDER BY period_year
""")

gdp_df = _query(f"""
    SELECT * FROM marts.gdp_trend
    WHERE period_year BETWEEN {year_min} AND {year_max}
    ORDER BY period_year
""")

cpi_df = _query(f"""
    SELECT * FROM marts.cpi_trend
    WHERE period_year BETWEEN {year_min} AND {year_max}
    ORDER BY period_date
""")

remit_df = _query(f"""
    SELECT * FROM marts.remittance_trend
    WHERE period_year BETWEEN {year_min} AND {year_max}
    ORDER BY period_year
""")

if dashboard_df.empty:
    st.warning(
        "No data found. Run the pipeline first: `ph-tracker ingest`",
        icon="⚠️",
    )
    st.stop()

latest = dashboard_df.iloc[-1]
prev   = dashboard_df.iloc[-2] if len(dashboard_df) >= 2 else None

# ── Header ────────────────────────────────────────────────────────────────────

st.title("Philippine Economic Dashboard")
st.caption(
    f"Annual indicators · {year_min}–{year_max} · "
    f"Latest: {int(latest['period_year'])}"
)
st.divider()

# ── Metric cards ──────────────────────────────────────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    gdp_delta = (
        float(latest["gdp_growth_pct"])
        if pd.notna(latest.get("gdp_growth_pct"))
        else None
    )
    st.metric(
        "GDP (current USD)",
        _format_bn(float(latest["gdp_usd_bn"])) if pd.notna(latest.get("gdp_usd_bn")) else "—",
        delta=_format_pct(gdp_delta),
        delta_color=_delta_color(gdp_delta),
        help="World Bank — GDP at current prices (USD billions)",
    )

with col2:
    st.metric(
        "GDP per capita",
        f"${float(latest['gdp_per_capita_usd']):,.0f}" if pd.notna(latest.get("gdp_per_capita_usd")) else "—",
        help="World Bank — GDP per capita (current USD)",
    )

with col3:
    inf_val = float(latest["avg_inflation_pct"]) if pd.notna(latest.get("avg_inflation_pct")) else None
    st.metric(
        "Inflation (avg)",
        _format_pct(inf_val),
        delta=None,
        delta_color="inverse" if (inf_val or 0) > 4 else "normal",
        help="PSA — CPI year-on-year change, annual average",
    )

with col4:
    remit_val = float(latest["remittance_usd_bn"]) if pd.notna(latest.get("remittance_usd_bn")) else None
    remit_delta = float(latest["remittance_yoy_pct"]) if pd.notna(latest.get("remittance_yoy_pct")) else None
    st.metric(
        "OFW Remittances",
        _format_bn(remit_val),
        delta=_format_pct(remit_delta),
        delta_color=_delta_color(remit_delta),
        help="World Bank — personal remittances received (USD billions)",
    )

with col5:
    remit_pct = float(latest["remittance_pct_gdp"]) if pd.notna(latest.get("remittance_pct_gdp")) else None
    st.metric(
        "Remittances / GDP",
        _format_pct(remit_pct),
        help="World Bank — personal remittances as % of GDP",
    )

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────

tab_gdp, tab_cpi, tab_remit, tab_overview = st.tabs([
    "📈 GDP", "📊 CPI & Inflation", "💸 OFW Remittances", "🗂 Overview"
])

# ── GDP tab ───────────────────────────────────────────────────────────────────

with tab_gdp:
    if gdp_df.empty:
        st.info("No GDP data in range.")
    else:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("GDP at current prices (USD billions)")
            fig = px.bar(
                gdp_df,
                x="period_year",
                y="gdp_usd_bn",
                color_discrete_sequence=[COLORS["gdp"]],
                labels={"period_year": "Year", "gdp_usd_bn": "GDP (USD B)"},
            )
            fig.update_layout(
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.subheader("GDP growth rate (%)")
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=gdp_df["period_year"],
                y=gdp_df["gdp_growth_pct"],
                mode="lines+markers",
                line=dict(color=COLORS["gdp_growth"], width=2),
                marker=dict(size=6),
                name="GDP growth %",
            ))
            fig2.add_hline(y=0, line_dash="dot", line_color=COLORS["neutral"])
            fig2.update_layout(
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis_ticksuffix="%",
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("GDP per capita (USD)")
        fig3 = px.area(
            gdp_df,
            x="period_year",
            y="gdp_per_capita_usd",
            color_discrete_sequence=[COLORS["gdp"]],
            labels={"period_year": "Year", "gdp_per_capita_usd": "USD"},
        )
        fig3.update_layout(
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig3, use_container_width=True)

        with st.expander("📥 Download GDP data"):
            csv = gdp_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download GDP CSV",
                data=csv,
                file_name=f"ph_gdp_{year_min}_{year_max}.csv",
                mime="text/csv",
            )

# ── CPI tab ───────────────────────────────────────────────────────────────────

with tab_cpi:
    if cpi_df.empty:
        st.info("No CPI data in range.")
    else:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("CPI Index (2018=100) — monthly")
            fig = px.line(
                cpi_df.dropna(subset=["cpi_index"]),
                x="period_date",
                y="cpi_index",
                color_discrete_sequence=[COLORS["cpi"]],
                labels={"period_date": "Date", "cpi_index": "CPI (2018=100)"},
            )
            fig.add_hline(y=100, line_dash="dot", line_color=COLORS["neutral"])
            fig.update_layout(
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.subheader("Inflation rate (% YoY) — monthly")
            inf_data = cpi_df.dropna(subset=["inflation_pct"])
            if not inf_data.empty:
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    x=inf_data["period_date"],
                    y=inf_data["inflation_pct"],
                    marker_color=[
                        COLORS["inflation"] if v > 4 else COLORS["gdp_growth"]
                        for v in inf_data["inflation_pct"]
                    ],
                    name="Inflation %",
                ))
                fig2.add_hline(y=4, line_dash="dash", line_color=COLORS["cpi"],
                               annotation_text="BSP target 4%")
                fig2.add_hline(y=2, line_dash="dot", line_color=COLORS["neutral"],
                               annotation_text="BSP target 2%")
                fig2.update_layout(
                    showlegend=False,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_ticksuffix="%",
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No inflation rate data available.")

        with st.expander("📥 Download CPI data"):
            csv = cpi_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CPI CSV",
                data=csv,
                file_name=f"ph_cpi_{year_min}_{year_max}.csv",
                mime="text/csv",
            )

# ── OFW Remittances tab ───────────────────────────────────────────────────────

with tab_remit:
    if remit_df.empty:
        st.info("No remittance data in range.")
    else:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("OFW remittances (USD billions)")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=remit_df["period_year"],
                y=remit_df["remittance_usd_bn"],
                marker_color=COLORS["remittance"],
                name="Remittances",
            ))
            fig.add_trace(go.Scatter(
                x=remit_df["period_year"],
                y=remit_df["remittance_3yr_avg_bn"],
                mode="lines",
                line=dict(color=COLORS["neutral"], width=2, dash="dot"),
                name="3-yr avg",
            ))
            fig.update_layout(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.subheader("Remittances as % of GDP")
            fig2 = px.area(
                remit_df.dropna(subset=["remittance_pct_gdp"]),
                x="period_year",
                y="remittance_pct_gdp",
                color_discrete_sequence=[COLORS["remit_pct"]],
                labels={"period_year": "Year", "remittance_pct_gdp": "% of GDP"},
            )
            fig2.update_layout(
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis_ticksuffix="%",
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("YoY growth rate (%)")
        yoy_data = remit_df.dropna(subset=["remittance_yoy_pct"])
        if not yoy_data.empty:
            fig3 = go.Figure(go.Bar(
                x=yoy_data["period_year"],
                y=yoy_data["remittance_yoy_pct"],
                marker_color=[
                    COLORS["gdp_growth"] if v >= 0 else COLORS["inflation"]
                    for v in yoy_data["remittance_yoy_pct"]
                ],
            ))
            fig3.add_hline(y=0, line_color=COLORS["neutral"])
            fig3.update_layout(
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis_ticksuffix="%",
            )
            st.plotly_chart(fig3, use_container_width=True)

        with st.expander("📥 Download remittance data"):
            csv = remit_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Remittances CSV",
                data=csv,
                file_name=f"ph_remittances_{year_min}_{year_max}.csv",
                mime="text/csv",
            )

# ── Overview tab ──────────────────────────────────────────────────────────────

with tab_overview:
    st.subheader("Annual economic overview")

    if not dashboard_df.empty:
        display_cols = {
            "period_year":       "Year",
            "gdp_usd_bn":        "GDP (USD B)",
            "gdp_growth_pct":    "GDP Growth %",
            "gdp_per_capita_usd":"GDP per capita",
            "avg_inflation_pct": "Avg Inflation %",
            "remittance_usd_bn": "Remittances (USD B)",
            "remittance_pct_gdp":"Remit / GDP %",
            "remittance_yoy_pct":"Remit YoY %",
        }
        display_df = dashboard_df[
            [c for c in display_cols if c in dashboard_df.columns]
        ].rename(columns=display_cols)

        st.dataframe(
            display_df.sort_values("Year", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("📥 Download full dashboard data"):
            csv = dashboard_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download dashboard CSV",
                data=csv,
                file_name=f"ph_economic_dashboard_{year_min}_{year_max}.csv",
                mime="text/csv",
            )

    st.divider()
    st.caption(
        "**Data sources:** "
        "Philippine Statistics Authority (PSA) OpenSTAT · "
        "World Bank World Development Indicators · "
        "Bangko Sentral ng Pilipinas (BSP) · "
        "Built with Streamlit + dbt + PostgreSQL"
    )
