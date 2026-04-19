"""
First Solar – RO Executive Intelligence Dashboard
Ion Exchange (India) Ltd.

Run:
    streamlit run app.py
"""
from __future__ import annotations
import os
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

import engine as eng
import importlib; importlib.reload(eng)  # ensure latest engine is used on Streamlit hot-reload

# Clean Plotly template — white background, soft gridlines, navy accent
import plotly.io as pio
pio.templates["ion"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Inter, Segoe UI, Arial", size=13, color="#111827"),
        colorway=["#0B2545", "#EF6C00", "#13315C", "#6A1B9A", "#2E7D32", "#C62828"],
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showgrid=False, showline=True, linecolor="#E4E9F2", ticks="outside",
                   tickcolor="#E4E9F2"),
        yaxis=dict(showgrid=True, gridcolor="#F1F3F5", showline=True, linecolor="#E4E9F2"),
        margin=dict(l=10, r=10, t=40, b=10), legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
)
pio.templates.default = "ion"

# ======================================================================
# PAGE CONFIG & STYLING
# ======================================================================
st.set_page_config(
    page_title="First Solar – RO Performance Report",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1380px;}
h1 {color: #0B2545; font-weight: 600; letter-spacing: -0.5px;}
h2, h3 {color: #13315C; font-weight: 600;}
.metric-card {
    background: #ffffff;
    padding: 14px 18px; border-radius: 4px;
    border: 1px solid #E4E9F2; border-left: 3px solid #0B2545;
}
.metric-card .label {font-size:0.78rem; color:#6B7280; text-transform:uppercase; letter-spacing:0.5px;}
.metric-card .value {font-size:1.7rem; font-weight:600; color:#0B2545; margin-top:4px;}
.metric-card .sub   {font-size:0.78rem; color:#6B7280;}
.badge {padding: 3px 10px; border-radius: 3px; color:white; font-weight:500; font-size:0.78rem; letter-spacing:0.3px;}
.brand {font-size:0.8rem; color:#6B7280; letter-spacing:1px; text-transform:uppercase;}
.footer {margin-top: 2rem; color:#9CA3AF; font-size:0.75rem; text-align:center; border-top:1px solid #E4E9F2; padding-top:1rem;}
hr {margin: 0.8rem 0; border-color:#E4E9F2;}
[data-testid="stSidebar"] {background: #F7F9FC;}
</style>
""", unsafe_allow_html=True)


# ======================================================================
# DATA CACHE
# ======================================================================
@st.cache_data(show_spinner=True)
def load_data(xlsx_path: str, temp_c, roll_win: int) -> pd.DataFrame:
    return eng.build_all(xlsx_path, temp_c, roll_win)


# ======================================================================
# SIDEBAR
# ======================================================================
st.sidebar.markdown(
    "<div style='padding:8px 0 12px 0;'>"
    "<div style='font-size:1.15rem; font-weight:600; color:#0B2545;'>Ion Exchange (India) Ltd.</div>"
    "<div style='font-size:0.8rem; color:#6B7280;'>RO Performance Diagnostic Report</div>"
    "<div style='font-size:0.8rem; color:#6B7280;'>Client: First Solar</div>"
    "</div>", unsafe_allow_html=True)
st.sidebar.markdown("---")

xlsx_path = st.sidebar.text_input("Data file", value="ro_log_workbook1.xlsx")
if not os.path.exists(xlsx_path):
    st.error(f"Data file not found: `{xlsx_path}`. Place the workbook next to app.py.")
    st.stop()

temp_in = st.sidebar.number_input("Feed water temperature (°C) — optional",
                                  min_value=0.0, max_value=60.0, value=0.0, step=1.0,
                                  help="Leave 0 to use TCF = 1 (no temperature correction).")
temp_c = None if temp_in == 0.0 else temp_in

roll_win = st.sidebar.slider("Smoothing window (samples)", 3, 24, 6,
                             help="Each sample ≈ 2 hours.")

df = load_data(xlsx_path, temp_c, roll_win)
trains_all = sorted(df["Train"].unique())

# Date range filter
min_d, max_d = df["Timestamp"].min().date(), df["Timestamp"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_d, max_d),
                                   min_value=min_d, max_value=max_d)
if isinstance(date_range, tuple) and len(date_range) == 2:
    d0, d1 = date_range
    mask = (df["Timestamp"].dt.date >= d0) & (df["Timestamp"].dt.date <= d1)
    df = df[mask].copy()

train_pick = st.sidebar.multiselect("RO trains", trains_all, default=trains_all)
df = df[df["Train"].isin(train_pick)].copy()

st.sidebar.markdown("---")
st.sidebar.markdown("#### Business assumptions")
water_price  = st.sidebar.number_input("Water value (₹ / m³)", 0.0, 500.0, 50.0, 5.0)
cip_cost     = st.sidebar.number_input("Unplanned CIP cost (₹ lakh)", 0.0, 50.0, 3.5, 0.5)
downtime_hrs = st.sidebar.number_input("Unplanned CIP downtime (hrs)", 0.0, 72.0, 8.0, 1.0)


# ======================================================================
# HEADER
# ======================================================================
col_a, col_b = st.columns([4, 1])
with col_a:
    st.markdown("<div class='brand'>Ion Exchange (India) Ltd. &nbsp;·&nbsp; Prepared for First Solar</div>",
                unsafe_allow_html=True)
    st.title("RO Performance Diagnostic Report")
    st.caption("Physics-based KPI monitoring, fouling diagnosis and CIP decision support.")
with col_b:
    st.markdown(
        f"<div style='text-align:right; padding-top:12px;'>"
        f"<div style='font-size:0.75rem; color:#6B7280; text-transform:uppercase; letter-spacing:0.5px;'>Reporting Window</div>"
        f"<div style='font-weight:600; color:#0B2545;'>{df['Timestamp'].min():%d %b %Y} — {df['Timestamp'].max():%d %b %Y}</div>"
        f"</div>", unsafe_allow_html=True)
st.markdown("---")


# ======================================================================
# HELPERS
# ======================================================================
def kpi_card(col, label, value, sub=""):
    col.markdown(
        f"<div class='metric-card'><div class='label'>{label}</div>"
        f"<div class='value'>{value}</div><div class='sub'>{sub}</div></div>",
        unsafe_allow_html=True)


def sev_badge(sev: str) -> str:
    col = eng.SEV_COLOR.get(sev, "#888")
    text = sev if sev else "Healthy"
    return f"<span class='badge' style='background:{col}'>{text}</span>"


# ======================================================================
# SYSTEM HEALTH SNAPSHOT
# ======================================================================
st.subheader("System Health Snapshot")

k1, k2, k3, k4, k5, k6 = st.columns(6)

total_prod_m3  = (df["PermFlow"].fillna(0) * 2).sum() / 1000.0   # 2-h cadence → m³ (flow in m³/h)
avg_recovery   = df["Recovery"].mean()
avg_salt_rej   = df["SaltRej"].mean()
avg_health     = df["Health"].mean()

# worst CIP severity right now
last_per_train = df.sort_values("Timestamp").groupby("Train").tail(1)
worst_sev = ""
for s in last_per_train["CIP"]:
    if eng.SEV_ORDER.index(s or "") > eng.SEV_ORDER.index(worst_sev):
        worst_sev = s

# Fouling acceleration days: days where any train had non-Normal diagnosis confirmed
non_normal = df[df["Diagnosis"] != "Normal Operation"].copy()
non_normal["Date"] = non_normal["Timestamp"].dt.date
fouling_days = non_normal.groupby("Train")["Date"].nunique().max() if len(non_normal) else 0

# Days to next CIP (min across trains)
days_list = []
for train in train_pick:
    g = df[df["Train"] == train]
    f = eng.forecast_days_to_cip(g)
    if pd.notna(f.get("days_to_cip", np.nan)) and np.isfinite(f["days_to_cip"]):
        days_list.append((train, f["days_to_cip"], f["limiting_kpi"]))
days_to_cip_val = min([d[1] for d in days_list]) if days_list else None

kpi_card(k1, "Total Permeate Produced",  f"{total_prod_m3:,.0f} m³", "Across selected window")
kpi_card(k2, "Avg Recovery",             f"{avg_recovery:.1f} %",   "Permeate / Feed")
kpi_card(k3, "Avg Salt Rejection",       f"{avg_salt_rej:.2f} %",   "1 − Permeate/Feed TDS")
kpi_card(k4, "Avg Health Score",         f"{avg_health:.0f} / 100", "Composite index")
kpi_card(k5, "Fouling Acc. Days",        f"{fouling_days}",         "Days with abnormal diagnosis")
kpi_card(k6, "Days to next CIP",
         f"{days_to_cip_val:.1f}" if days_to_cip_val is not None else "—",
         "Linear forecast")

st.markdown("")
current_status_cols = st.columns(len(train_pick) if train_pick else 1)
for i, train in enumerate(train_pick):
    row = last_per_train[last_per_train["Train"] == train]
    if row.empty: continue
    row = row.iloc[0]
    current_status_cols[i].markdown(
        f"### {train}\n"
        f"- **CIP status:** {sev_badge(row['CIP'])}\n"
        f"- **Diagnosis:** <span style='color:{eng.DIAG_COLOR.get(row['Diagnosis'], '#333')}'>"
        f"<b>{row['Diagnosis']}</b></span>\n"
        f"- Health: **{row['Health']:.0f}/100**  ·  NPF Δ **{row['NPF_pct']:+.1f}%**  ·  "
        f"NSP Δ **{row['NSP_pct']:+.1f}%**  ·  ΔP Δ **{row['DP_pct']:+.1f}%**",
        unsafe_allow_html=True)

st.markdown("---")


# ======================================================================
# TABS
# ======================================================================
tab_overview, tab_fouling, tab_stage, tab_diag, tab_cip, tab_forecast, tab_exec = st.tabs([
    "Overview", "Fouling Indicators", "Stage Analysis",
    "Diagnosis", "CIP Decision", "Forecast & OEE", "Executive Summary"
])


# -----------------------------------------------------------------
# OVERVIEW TAB
# -----------------------------------------------------------------
with tab_overview:
    st.markdown("### Health score trend (daily mean)")
    daily = (df.assign(Date=df["Timestamp"].dt.date)
               .groupby(["Train", "Date"])
               .agg(Health=("Health", "mean"),
                    NPF_pct=("NPF_pct", "mean"),
                    NSP_pct=("NSP_pct", "mean"),
                    DP_pct=("DP_pct", "mean"),
                    Feed_pct=("FeedPress_pct", "mean"),
                    CIP=("CIP", lambda s: max((v for v in s if v in eng.SEV_ORDER), key=lambda v: eng.SEV_ORDER.index(v)) if any(v for v in s) else ""),
                    Diagnosis=("Diagnosis", lambda s: (pd.Series([x for x in s if x != "Normal Operation"]).mode().iloc[0]
                                                      if any(x != "Normal Operation" for x in s) else "Normal Operation")))
               .reset_index())

    fig = px.line(daily, x="Date", y="Health", color="Train",
                  markers=True, line_shape="spline",
                  color_discrete_map={"RO1": "#0B3D91", "RO2": "#EF6C00"})
    fig.add_hrect(y0=80, y1=100, fillcolor="#2E7D32", opacity=0.08, line_width=0,
                  annotation_text="Healthy", annotation_position="top left")
    fig.add_hrect(y0=60, y1=80,  fillcolor="#FFB300", opacity=0.08, line_width=0,
                  annotation_text="Watch",   annotation_position="top left")
    fig.add_hrect(y0=0,  y1=60,  fillcolor="#C62828", opacity=0.08, line_width=0,
                  annotation_text="Risk",    annotation_position="top left")
    fig.update_layout(height=360, yaxis_title="Health score", yaxis_range=[0, 105],
                      margin=dict(l=10, r=10, t=20, b=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    cL, cR = st.columns(2)
    with cL:
        st.markdown("### Recovery (%) — train comparison")
        fig = px.line(df, x="Timestamp", y="Recovery_sm", color="Train",
                      color_discrete_map={"RO1": "#0B3D91", "RO2": "#EF6C00"})
        fig.update_layout(height=320, yaxis_title="Recovery (%)",
                          margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with cR:
        st.markdown("### Salt rejection (%) — train comparison")
        fig = px.line(df, x="Timestamp", y="SaltRej_sm", color="Train",
                      color_discrete_map={"RO1": "#0B3D91", "RO2": "#EF6C00"})
        fig.update_layout(height=320, yaxis_title="Salt rejection (%)",
                          margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------
# FOULING INTELLIGENCE TAB
# -----------------------------------------------------------------
with tab_fouling:
    st.markdown("### Core KPIs — % change vs baseline (smoothed)")
    kpi_cols = [("NPF_pct", "NPF (↓ = flux loss)", "#0B3D91"),
                ("NSP_pct", "NSP (↑ = rejection loss)", "#6A1B9A"),
                ("DP_pct",  "ΔP (↑ = fouling / scaling)", "#2E7D32"),
                ("FeedPress_pct", "Feed Pressure (↑ = pretreatment strain)", "#EF6C00")]

    for train in train_pick:
        g = df[df["Train"] == train].sort_values("Timestamp")
        fig = make_subplots(rows=2, cols=2,
                            subplot_titles=[t[1] for t in kpi_cols],
                            shared_xaxes=True, vertical_spacing=0.12, horizontal_spacing=0.08)
        for i, (col, _, color) in enumerate(kpi_cols):
            r, c = divmod(i, 2); r += 1; c += 1
            fig.add_trace(go.Scatter(x=g["Timestamp"], y=g[col], mode="lines",
                                     line=dict(color=color, width=2),
                                     name=col, showlegend=False), row=r, col=c)
            fig.add_hline(y=0, line=dict(color="black", width=0.6, dash="dot"), row=r, col=c)
            # threshold lines
            if col == "NPF_pct":
                fig.add_hline(y=-5,  line=dict(color="#FFB300", dash="dash"), row=r, col=c)
                fig.add_hline(y=-10, line=dict(color="#FB8C00", dash="dash"), row=r, col=c)
                fig.add_hline(y=-15, line=dict(color="#C62828", dash="dash"), row=r, col=c)
            elif col == "NSP_pct":
                fig.add_hline(y=10,  line=dict(color="#FFB300", dash="dash"), row=r, col=c)
                fig.add_hline(y=15,  line=dict(color="#FB8C00", dash="dash"), row=r, col=c)
                fig.add_hline(y=25,  line=dict(color="#C62828", dash="dash"), row=r, col=c)
            else:
                fig.add_hline(y=10,  line=dict(color="#FFB300", dash="dash"), row=r, col=c)
                fig.add_hline(y=20,  line=dict(color="#C62828", dash="dash"), row=r, col=c)
        fig.update_layout(height=520, title=f"{train} — Physics KPIs",
                          margin=dict(l=20, r=10, t=60, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.info("Dashed lines mark the CIP-action thresholds from the Ion Exchange RO "
            "performance calculations: amber = **Due**, orange = **Cleaning Required**, red = **Critical**.")


# -----------------------------------------------------------------
# STAGE ANALYSIS TAB
# -----------------------------------------------------------------
with tab_stage:
    st.markdown("### Stage-wise ΔP — localises where fouling / scaling starts")
    st.caption("RO1 has three stages (3 → 2 → 1 pressure vessels typically). RO2 has two. "
               "A lead-stage ΔP rise points to **particulate or biofouling**; a tail-stage rise points to **scaling**.")

    for train in train_pick:
        g = df[df["Train"] == train].sort_values("Timestamp")
        cols = ["DP_Stage_1_sm", "DP_Stage_2_sm", "DP_Stage_3_sm"]
        labels = ["Stage 1", "Stage 2", "Stage 3"]
        colors = ["#0B3D91", "#EF6C00", "#2E7D32"]
        fig = go.Figure()
        for c, lab, clr in zip(cols, labels, colors):
            if g[c].notna().any():
                fig.add_trace(go.Scatter(x=g["Timestamp"], y=g[c], mode="lines",
                                         line=dict(color=clr, width=2), name=lab))
        fig.update_layout(height=330, title=f"{train} — Stage ΔP (smoothed, bar)",
                          yaxis_title="ΔP (bar)", legend_title="",
                          margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Stage ΔP — % change from baseline")
    for train in train_pick:
        g = df[df["Train"] == train].sort_values("Timestamp")
        rows = []
        for c, lab in zip(["DP_Stage_1_pct", "DP_Stage_2_pct", "DP_Stage_3_pct"],
                          ["Stage 1", "Stage 2", "Stage 3"]):
            if c in g.columns and g[c].notna().any():
                rows.append(dict(train=train, stage=lab,
                                 cur=g[c].dropna().iloc[-1],
                                 mean=g[c].mean()))
        if rows:
            sdf = pd.DataFrame(rows)
            fig = px.bar(sdf, x="stage", y="cur", text="cur",
                         color="stage",
                         color_discrete_map={"Stage 1":"#0B3D91","Stage 2":"#EF6C00","Stage 3":"#2E7D32"},
                         labels={"cur":"% change vs baseline"})
            fig.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
            fig.update_layout(height=280, title=f"{train} — current stage ΔP deviation",
                              showlegend=False, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------
# DIAGNOSIS TAB
# -----------------------------------------------------------------
with tab_diag:
    st.markdown("### Fouling diagnosis timeline")
    st.caption("Each confirmed (latched) abnormal pattern is labelled per the 12-category decision tree "
               "from the Ion Exchange RO performance standard.")

    for train in train_pick:
        g = df[df["Train"] == train].copy()
        g["Diagnosis_code"] = g["Diagnosis"].map(eng.DIAG_CODE)
        fig = px.scatter(g, x="Timestamp", y="Diagnosis",
                         color="Diagnosis",
                         color_discrete_map=eng.DIAG_COLOR,
                         height=340)
        fig.update_traces(marker=dict(size=7))
        fig.update_layout(title=f"{train} — diagnosis over time",
                          margin=dict(l=10, r=10, t=40, b=10), showlegend=False,
                          yaxis=dict(categoryorder="array",
                                     categoryarray=eng.DIAGNOSIS_ORDER))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Diagnosis mix (non-normal only)")
    ab = df[df["Diagnosis"] != "Normal Operation"]
    if ab.empty:
        st.success("No abnormal patterns detected in the selected window — all diagnoses = Normal Operation.")
    else:
        mix = ab.groupby(["Train", "Diagnosis"]).size().reset_index(name="Samples")
        fig = px.bar(mix, x="Samples", y="Diagnosis", color="Train", orientation="h",
                     color_discrete_map={"RO1":"#0B3D91","RO2":"#EF6C00"},
                     barmode="group")
        fig.update_layout(height=380, yaxis=dict(categoryorder="total ascending"),
                          margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------
# CIP DECISION TAB
# -----------------------------------------------------------------
with tab_cip:
    st.markdown("### CIP severity — calendar view")
    daily_cip = (df.assign(Date=df["Timestamp"].dt.date)
                   .groupby(["Train","Date"])["CIP"]
                   .agg(lambda s: max([x for x in s if x in eng.SEV_ORDER], key=lambda v: eng.SEV_ORDER.index(v)) if any(s) else "")
                   .reset_index())
    pv = daily_cip.pivot(index="Date", columns="Train", values="CIP").fillna("")
    sev_to_num = {"":0, "Due":1, "Cleaning Required":2, "Critical":3}
    z = pv.replace(sev_to_num).values
    fig = go.Figure(data=go.Heatmap(
        z=z, x=list(pv.columns), y=[str(d) for d in pv.index],
        colorscale=[[0, "#E0F2F1"], [0.33, "#FFD54F"], [0.66, "#FB8C00"], [1, "#C62828"]],
        zmin=0, zmax=3, showscale=False,
        text=pv.values, hovertemplate="%{y} | %{x}<br>Severity: %{text}<extra></extra>",
    ))
    fig.update_layout(height=max(380, 20*len(pv)), margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Recommended CIP actions")
    recs = daily_cip[daily_cip["CIP"] != ""].merge(
        daily.drop(columns=["CIP"], errors="ignore"), on=["Train","Date"], how="left")
    if recs.empty:
        st.success("No CIP action flagged in the selected window.")
    else:
        recs["Date"] = pd.to_datetime(recs["Date"]).dt.strftime("%d %b %Y")
        st.dataframe(
            recs[["Date","Train","CIP","Diagnosis",
                  "NPF_pct","NSP_pct","DP_pct","Feed_pct","Health"]]
                .rename(columns={"NPF_pct":"ΔNPF %","NSP_pct":"ΔNSP %",
                                 "DP_pct":"ΔΔP %","Feed_pct":"ΔFeed %",
                                 "Health":"Health"})
                .style.format({"ΔNPF %":"{:+.1f}","ΔNSP %":"{:+.1f}",
                               "ΔΔP %":"{:+.1f}","ΔFeed %":"{:+.1f}","Health":"{:.0f}"}),
            use_container_width=True, height=340)

    st.markdown("---")
    st.markdown("### Recommended vs Actual CIP")
    st.caption("Blue markers are CIP events actually performed by the First Solar site team. "
               "Orange shading marks the days our engine recommended cleaning.")

    # Parse actual CIP dates per train
    actual_cip = {t: pd.to_datetime(eng.ACTUAL_CIP.get(t, [])) for t in train_pick}

    for train in train_pick:
        g = df[df["Train"] == train].sort_values("Timestamp")
        if g.empty: continue
        rec_dates = daily_cip[(daily_cip["Train"]==train) & (daily_cip["CIP"]!="")]
        rec_dates = pd.to_datetime(rec_dates["Date"])

        fig = go.Figure()
        # NPF trace
        fig.add_trace(go.Scatter(
            x=g["Timestamp"], y=g["NPF_pct"], mode="lines",
            line=dict(color="#0B2545", width=1.8), name="NPF % change"))
        # Recommended CIP shading
        for d in rec_dates:
            fig.add_vrect(x0=d, x1=d + pd.Timedelta(hours=20),
                          fillcolor="#FB8C00", opacity=0.22, line_width=0,
                          layer="below")
        # Actual CIP markers (blue vertical lines with annotation)
        for d in actual_cip.get(train, []):
            fig.add_vline(x=d, line=dict(color="#1565C0", width=2, dash="solid"))
            fig.add_annotation(x=d, y=1.02, yref="paper", showarrow=False,
                               text="Actual CIP", font=dict(size=10, color="#1565C0"),
                               bgcolor="#E3F2FD", borderpad=2)

        fig.add_hline(y=-5,  line=dict(color="#9CA3AF", dash="dot", width=1))
        fig.add_hline(y=-10, line=dict(color="#FB8C00", dash="dot", width=1))
        fig.add_hline(y=-15, line=dict(color="#C62828", dash="dot", width=1))
        fig.update_layout(height=340, title=f"{train} — NPF deterioration with CIP events",
                          yaxis_title="NPF % change vs baseline",
                          margin=dict(l=10, r=10, t=60, b=10),
                          plot_bgcolor="white", paper_bgcolor="white",
                          showlegend=False)
        fig.update_xaxes(showgrid=False, showline=True, linecolor="#E4E9F2")
        fig.update_yaxes(showgrid=True, gridcolor="#F1F3F5", showline=True, linecolor="#E4E9F2")
        st.plotly_chart(fig, use_container_width=True)

    # Lead / lag table: for each actual CIP, find nearest recommended day
    rows = []
    for train in train_pick:
        rec_dates = daily_cip[(daily_cip["Train"]==train) & (daily_cip["CIP"]!="")]
        rec_dates = pd.to_datetime(rec_dates["Date"])
        for d in actual_cip.get(train, []):
            if rec_dates.empty:
                rows.append(dict(Train=train, **{"Actual CIP": d.strftime("%d %b %Y"),
                                                 "Nearest Recommendation": "—",
                                                 "Days (rec → act)": "—",
                                                 "Assessment": "No recommendation in window"}))
                continue
            deltas = (d - rec_dates).dt.days
            # Recommendation ahead of the actual (positive = we warned earlier, negative = after the fact)
            ahead = deltas[deltas >= 0]
            if not ahead.empty:
                idx = ahead.idxmin()
                lag = int(ahead.min())
                assess = ("On-time" if lag <= 1 else
                          "Site cleaned within 3 days of recommendation" if lag <= 3 else
                          f"Site cleaned {lag} days after recommendation")
            else:
                idx = deltas.abs().idxmin()
                lag = int(deltas[idx])
                assess = f"Recommendation came {abs(lag)} days after actual clean"
            rows.append(dict(Train=train,
                             **{"Actual CIP": d.strftime("%d %b %Y"),
                                "Nearest Recommendation": rec_dates.loc[idx].strftime("%d %b %Y"),
                                "Days (rec → act)": lag,
                                "Assessment": assess}))

    if rows:
        st.markdown("#### Alignment between our recommendation and site execution")
        align_df = pd.DataFrame(rows)
        st.dataframe(align_df, use_container_width=True, hide_index=True)
        st.caption("Positive *Days (rec → act)* means our engine flagged the need to clean that many days "
                   "before the site actually performed it — the larger the number, the greater the avoidable "
                   "flux loss. Negative values indicate the recommendation was not available in time.")


# -----------------------------------------------------------------
# FORECAST & OEE TAB
# -----------------------------------------------------------------
with tab_forecast:
    st.markdown("### Time-to-CIP forecast")
    st.caption("Each KPI is linearly extrapolated forward; the limiting KPI sets the day the "
               "**Cleaning Required** threshold is expected to be crossed.")

    for train in train_pick:
        g = df[df["Train"] == train].sort_values("Timestamp")
        f = eng.forecast_days_to_cip(g, "Cleaning Required")
        c1, c2, c3, c4 = st.columns(4)
        if pd.isna(f["days_to_cip"]):
            c1.metric(f"{train} – days to CIP", "—")
        else:
            days = f["days_to_cip"]
            c1.metric(f"{train} – days to CIP",
                      f"{days:.1f} d" if np.isfinite(days) else "Stable",
                      help=f"Limiting KPI: {f['limiting_kpi']}")
        if f.get("current"):
            c2.metric("ΔNPF now", f"{f['current'].get('NPF', float('nan')):+.1f}%")
            c3.metric("ΔNSP now", f"{f['current'].get('NSP', float('nan')):+.1f}%")
            c4.metric("ΔΔP now",  f"{f['current'].get('DP',  float('nan')):+.1f}%")

        # Forecast plot
        sub = g.dropna(subset=["NPF_pct","NSP_pct","DP_pct","FeedPress_pct"])
        if len(sub) >= 6:
            fig = make_subplots(rows=1, cols=4, subplot_titles=["NPF","NSP","ΔP","Feed-P"],
                                shared_yaxes=False)
            for i, (col, target) in enumerate([("NPF_pct",-10), ("NSP_pct",15),
                                                ("DP_pct",15), ("FeedPress_pct",10)]):
                x = sub["Timestamp"]
                y = sub[col].values
                fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=col,
                                         line=dict(color="#0B3D91"), showlegend=False),
                              row=1, col=i+1)
                # linear fit
                xd = (x - x.iloc[0]).dt.total_seconds()/86400
                m, b = np.polyfit(xd, y, 1)
                future = pd.date_range(x.iloc[-1], x.iloc[-1]+timedelta(days=7), freq="12h")
                xf = (future - x.iloc[0]).total_seconds()/86400
                yf = m*xf + b
                fig.add_trace(go.Scatter(x=future, y=yf, mode="lines",
                                         line=dict(color="#EF6C00", dash="dot"),
                                         name="Forecast", showlegend=(i==0)),
                              row=1, col=i+1)
                fig.add_hline(y=target, line=dict(color="#C62828", dash="dash"), row=1, col=i+1)
            fig.update_layout(height=280, title=f"{train} — 7-day projection",
                              margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### Overall Equipment Effectiveness (OEE)")
    st.caption("OEE = Availability × Performance × Quality. Industry-standard composite of uptime, flux retention, and permeate-quality conformance.")
    ocols = st.columns(len(train_pick) if train_pick else 1)
    for i, train in enumerate(train_pick):
        o = eng.oee(df[df["Train"] == train])
        ocols[i].markdown(f"#### {train}")
        ocols[i].metric("OEE",
                        f"{o['oee']*100:.1f} %" if pd.notna(o['oee']) else "—",
                        help="Composite")
        sub = ocols[i].container()
        sub.markdown(
            f"- Availability: **{o['availability']*100:.1f}%**\n"
            f"- Performance: **{(o['performance'] or 0)*100:.1f}%**\n"
            f"- Quality: **{(o['quality'] or 0)*100:.1f}%**")


# -----------------------------------------------------------------
# EXECUTIVE SUMMARY TAB
# -----------------------------------------------------------------
with tab_exec:
    st.markdown("## Executive Interpretation")
    bullets_assess, bullets_biz, bullets_reco = [], [], []

    # Business value computed from user assumptions
    # Flow loss potentially recovered by timely CIP
    flow_loss_pct = -df.groupby("Train")["NPF_pct"].last().min()  # most negative
    flow_loss_pct = 0 if (flow_loss_pct is None or pd.isna(flow_loss_pct) or flow_loss_pct < 0) else flow_loss_pct
    mean_flow = df["PermFlow"].mean() or 0
    monthly_loss_m3 = mean_flow * 24 * 30 * (flow_loss_pct/100)     # rough
    monthly_loss_inr = monthly_loss_m3 * water_price / 100000        # ₹ lakh

    # CIPs avoided
    predicted_cips = (daily_cip["CIP"] != "").sum() if 'daily_cip' in dir() else 0
    saved_cip_inr = 0.5 * predicted_cips * cip_cost                 # assume half convert to avoided unplanned

    # System assessment bullets
    worst_diag = (df[df["Diagnosis"]!="Normal Operation"]
                     .groupby(["Train","Diagnosis"]).size().reset_index(name="n")
                     .sort_values("n", ascending=False))
    if worst_diag.empty:
        bullets_assess.append("All trains tracking **baseline** — no confirmed fouling pattern during the reporting window.")
    else:
        for _, r in worst_diag.head(3).iterrows():
            bullets_assess.append(f"**{r['Train']}** shows a dominant pattern of **{r['Diagnosis']}** ({r['n']} confirmed samples).")

    # Days to CIP
    if days_list:
        t, d, k = min(days_list, key=lambda x: x[1])
        bullets_assess.append(f"Projected **CIP window**: **{t}** in **{d:.1f} days**, limited by **{k}**.")
    else:
        bullets_assess.append("No KPI is presently trending toward the CIP threshold — system in **steady state**.")

    # Business impact
    bullets_biz.append(f"Early fouling detection at current decline rate preserves ~**{monthly_loss_m3:,.0f} m³/month** of permeate "
                       f"(≈ **₹{monthly_loss_inr:.1f} lakh/month** at ₹{water_price:.0f}/m³).")
    if predicted_cips:
        bullets_biz.append(f"Predictive CIP scheduling is expected to avoid at least **~{predicted_cips//2} unplanned CIPs** "
                           f"(≈ **₹{saved_cip_inr:.1f} lakh** avoided and **~{(predicted_cips//2)*downtime_hrs:.0f} hrs** of downtime retained).")
    bullets_biz.append("Stage-wise ΔP localisation shortens root-cause diagnosis from days to hours — "
                       "reducing CIP chemistry wastage and operator load.")

    # Strategic recommendations
    bullets_reco.append("Continue the **12-hour rolling** KPI review cadence — trend-latched triggers eliminate false alarms from sensor noise.")
    if not worst_diag.empty:
        top = worst_diag.iloc[0]["Diagnosis"]
        if "Scaling" in top:
            bullets_reco.append("Increase **antiscalant dosing** and verify dose pump calibration; review LSI on raw feed.")
        elif "Organic" in top or "Biofouling" in top:
            bullets_reco.append("Review **chlorine residual/UV dose** upstream; schedule alkaline CIP before biofilm matures.")
        elif "Particulate" in top or "Colloidal" in top:
            bullets_reco.append("Audit **cartridge filters and upstream media filter backwash** — particulate break-through in progress.")
        elif "Oxidation" in top or "Chlorine" in top:
            bullets_reco.append("Immediately verify **SMBS dosing and free chlorine** at RO inlet — risk of irreversible membrane oxidation.")
        elif "Compaction" in top:
            bullets_reco.append("Review operating pressure envelope; sustained over-pressure causes irreversible compaction.")
    bullets_reco.append("Commission SDI, free-chlorine and feed-temperature tags to the historian — unlocks the full decision tree and true temperature-corrected TCF.")
    bullets_reco.append("Adopt a **predictive CIP schedule** driven by this dashboard to move from reactive to planned maintenance.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### System Assessment")
        for b in bullets_assess:
            st.markdown(f"- {b}")
    with c2:
        st.markdown("### Business Impact")
        for b in bullets_biz:
            st.markdown(f"- {b}")
    with c3:
        st.markdown("### Strategic Recommendation")
        for b in bullets_reco:
            st.markdown(f"- {b}")

    st.markdown("---")
    st.markdown("### Export")
    exp = df[["Timestamp","Train","NPF","NSP","DP","FeedPress","Recovery","SaltRej",
              "NPF_pct","NSP_pct","DP_pct","FeedPress_pct",
              "Diagnosis","CIP","Health"]].copy()
    csv = exp.to_csv(index=False).encode("utf-8")
    st.download_button("Download full KPI CSV", csv,
                       file_name="first_solar_ro_kpi_export.csv",
                       mime="text/csv")

st.markdown(
    "<div class='footer'>© Ion Exchange (India) Ltd. · Prepared for First Solar · "
    "Methodology: RO Performance Calculations v1 · Dashboard v1.0</div>",
    unsafe_allow_html=True)
