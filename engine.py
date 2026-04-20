"""
First Solar – RO Diagnostic Engine
Shared computation module used by the Streamlit dashboard and the notebook.
 
Implements (from RO Performance Calculations.docx + HZL production logic):
  • KPI calculation (NPF, NSP, ΔP, Feed Pressure, stage DPs)
  • Rolling smoothing + baseline-relative % change
  • 7-bucket trend classification (SHARP_UP / MODERATE_UP / SLIGHT_UP / STABLE / SLIGHT_DOWN / MODERATE_DOWN / SHARP_DOWN)
  • Latch (persistence) logic
  • 12-category fouling diagnosis decision tree
  • CIP severity classifier (Due / Cleaning Required / Critical) with latch
  • Membrane health score, OEE, recovery, days-to-CIP forecast
"""
 
from __future__ import annotations
import numpy as np
import pandas as pd
 
# ======================================================================
# CONFIG
# ======================================================================
SHEET                 = "Structured_Template"
B_RO                  = 0.021       # TCF exponent
T_REF                 = 25          # °C
ROLL_WIN              = 6           # 6 × 2-hourly samples ≈ 12 h smoothing
LATCH                 = 3           # samples required to confirm a trend
 
# CIP thresholds (from RO Performance Calculations.docx, Table 3)
CIP_THRESH = {
    "Due":               dict(npf=-5,  nsp=10, dp=10, feed=10),
    "Cleaning Required": dict(npf=-10, nsp=15, dp=15, feed=10),
    "Critical":          dict(npf=-15, nsp=25, dp=20, feed=20),
}
 
# Customer design baselines (from First Solar spec sheets)
# NSP = (design_perm_tds / design_feed_tds) * 100  — at reference temperature (TCF=1)
DESIGN_BASELINE = {
    "RO1": dict(npf=None, nsp=None, dp=None, feed_p=None),
    "RO2": dict(npf=None, nsp=None, dp=None, feed_p=None),
}
SEV_ORDER = ["", "Due", "Cleaning Required", "Critical"]
SEV_COLOR = {
    "":                  "#E0F2F1",
    "Due":               "#FFD54F",
    "Cleaning Required": "#FB8C00",
    "Critical":          "#C62828",
}
 
# 12-category diagnosis (HZL production ordering)
DIAGNOSIS_ORDER = [
    "Normal Operation",
    "Early Stage Fouling",
    "Early Scaling",
    "Particulate / Colloidal Fouling",
    "Inorganic Scaling",
    "Organic Fouling",
    "Biofouling",
    "Membrane Compaction",
    "Oxidation / Chlorine Attack",
    "O-Ring Leak / Internal Bypass",
    "Membrane Rupture",
    "Pretreatment Restriction",
]
DIAG_CODE = {d: i for i, d in enumerate(DIAGNOSIS_ORDER)}
DIAG_COLOR = {
    "Normal Operation":                 "#2E7D32",
    "Early Stage Fouling":              "#FDD835",
    "Early Scaling":                    "#FBC02D",
    "Particulate / Colloidal Fouling":  "#FB8C00",
    "Inorganic Scaling":                "#EF6C00",
    "Organic Fouling":                  "#E65100",
    "Biofouling":                       "#8D6E63",
    "Membrane Compaction":              "#6D4C41",
    "Oxidation / Chlorine Attack":      "#C62828",
    "O-Ring Leak / Internal Bypass":    "#AD1457",
    "Membrane Rupture":                 "#6A1B9A",
    "Pretreatment Restriction":         "#1565C0",
}
 
# Actual CIP events shared by First Solar (Erp-ro3 skid). A-skid = RO1, B-skid = RO2.
ACTUAL_CIP = {
    "RO1": [],  # No CIP performed on RO1 (A-skid dates belong to RO3, no RO3 data available)
    "RO2": ["2026-01-23", "2026-02-05", "2026-02-21", "2026-03-17", "2026-04-07"],
}
 
# Per-train column mapping (First Solar workbook)
TRAIN_MAP = {
    "RO1": dict(
        perm_flow="RO1 Permeate Flow",
        perm_tds ="RO1 Permeate TDS",
        feed_tds ="RO1 Feed parameters TDS",
        feed_p1  ="RO1 1st Feed Pressure",
        feed_p2  ="RO1 2st Feed Pressure",
        feed_p3  ="RO1 3rd Feed Pressure",
        reject_p ="RO1 Reject Pressure",
        dp       ="RO1 Differential Pressure",
        feed_flow="LBC (RO Feed) Flow",
        reject_f ="RO1 Reject Flow",
        stages   =3,
    ),
    "RO2": dict(
        perm_flow="RO2 Permeate Flow",
        perm_tds ="RO2 Permeate TDS",
        feed_tds ="RO2 Feed TDS",
        feed_p1  ="RO2 1st Feed Pressure",
        feed_p2  ="RO2 2st Feed Pressure",
        feed_p3  =None,
        reject_p ="RO2 Reject Pressure",
        dp       ="RO2 Differential Pressure",
        feed_flow="RO2 Feed Flow",
        reject_f ="RO2 Reject Flow",
        stages   =2,
    ),
}
 
 
# ======================================================================
# DATA LOAD
# ======================================================================
def _to_time_str(t):
    if pd.isna(t): return None
    if hasattr(t, "strftime"): return t.strftime("%H:%M")
    return str(t).strip()
 
 
def load_raw(xlsx_path: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=SHEET)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["TimeStr"] = df["Time"].apply(_to_time_str)
    df["Timestamp"] = pd.to_datetime(
        df["Date"].dt.strftime("%Y-%m-%d") + " " + df["TimeStr"].fillna("00:00"),
        errors="coerce")
    df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
    for c in df.columns:
        if c not in ("Date", "Time", "TimeStr", "Timestamp"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df
 
 
# ======================================================================
# KPI CALCULATION
# ======================================================================
def tcf(T):
    if T is None or pd.isna(T): return 1.0
    return float(np.exp(B_RO * (T - T_REF)))
 
 
def build_train(raw: pd.DataFrame, train: str, temp_c: float | None = None) -> pd.DataFrame:
    m = TRAIN_MAP[train]
    tcf_val = tcf(temp_c)
    t = pd.DataFrame({"Timestamp": raw["Timestamp"]})
    t["Train"]     = train
    t["PermFlow"]  = raw[m["perm_flow"]]
    t["PermTDS"]   = raw[m["perm_tds"]]
    t["FeedTDS"]   = raw[m["feed_tds"]]
    t["FeedFlow"]  = raw[m["feed_flow"]]
    t["RejectFlow"]= raw[m["reject_f"]]
    t["FeedPress"] = raw[m["feed_p1"]]
    t["RejectP"]   = raw[m["reject_p"]]
    t["DP"]        = raw[m["feed_p1"]] - raw[m["reject_p"]]
 
    # Stage DPs
    if m["stages"] == 3:
        t["DP_Stage_1"] = raw[m["feed_p1"]] - raw[m["feed_p2"]]
        t["DP_Stage_2"] = raw[m["feed_p2"]] - raw[m["feed_p3"]]
        t["DP_Stage_3"] = raw[m["feed_p3"]] - raw[m["reject_p"]]
    else:
        t["DP_Stage_1"] = raw[m["feed_p1"]] - raw[m["feed_p2"]]
        t["DP_Stage_2"] = raw[m["feed_p2"]] - raw[m["reject_p"]]
        t["DP_Stage_3"] = np.nan
 
    # Derived KPIs (docx formulas)
    t["NPF"]      = t["PermFlow"] * (1.0 / tcf_val)
    t["SP"]       = (t["PermTDS"] / t["FeedTDS"]) * 100.0
    t["NSP"]      = t["SP"] * (1.0 / tcf_val)
    t["Recovery"] = (t["PermFlow"] / t["FeedFlow"]) * 100.0       # %
    t["SaltRej"]  = 100.0 - t["SP"]                                # %
 
    return t
 
 
# ======================================================================
# SMOOTHING + BASELINE
# ======================================================================
_SMOOTH_COLS = ["NPF", "NSP", "DP", "FeedPress",
                "DP_Stage_1", "DP_Stage_2", "DP_Stage_3",
                "Recovery", "SaltRej"]
 
 
def add_smoothed(g: pd.DataFrame, win: int = ROLL_WIN) -> pd.DataFrame:
    g = g.sort_values("Timestamp").copy()
    for c in _SMOOTH_COLS:
        if c in g.columns:
            g[c + "_sm"] = g[c].rolling(win, min_periods=2).mean()
 
    train  = g["Train"].iloc[0] if "Train" in g.columns else None
    design = DESIGN_BASELINE.get(train, {})
 
    # First-day fallback (used only for KPIs without a design value, and for stage DPs)
    baseline_day = g["Timestamp"].dt.date.min()
    base_mask    = g["Timestamp"].dt.date == baseline_day
 
    for c, design_key in [("NPF", "npf"), ("NSP", "nsp"), ("DP", "dp"), ("FeedPress", "feed_p")]:
        b = design.get(design_key)
        if b is None or pd.isna(b):
            b = g.loc[base_mask, c + "_sm"].mean()
        g[c + "_pct"] = (g[c + "_sm"] - b) / b * 100.0 if b and not pd.isna(b) else np.nan
 
    # Stage DPs — no design spec provided, use first-day average
    for c in ["DP_Stage_1", "DP_Stage_2", "DP_Stage_3"]:
        b = g.loc[base_mask, c + "_sm"].mean()
        g[c + "_pct"] = (g[c + "_sm"] - b) / b * 100.0 if b and not pd.isna(b) else np.nan
 
    return g
 
 
# ======================================================================
# TREND LABELS + LATCH (HZL-style, 7 buckets)
# ======================================================================
def pct_trend_labels(series: pd.Series, window: int,
                     slight: float, moderate: float, sharp: float) -> pd.Series:
    pct = (series - series.shift(window)) / series.shift(window)
    pct = pct.replace([np.inf, -np.inf], np.nan)
 
    def cls(x):
        if pd.isna(x):            return "STABLE"
        if x >=  sharp:           return "SHARP_UP"
        if x >=  moderate:        return "MODERATE_UP"
        if x >=  slight:          return "SLIGHT_UP"
        if x <= -sharp:           return "SHARP_DOWN"
        if x <= -moderate:        return "MODERATE_DOWN"
        if x <= -slight:          return "SLIGHT_DOWN"
        return "STABLE"
    return pct.apply(cls)
 
 
def latch_bool(series: pd.Series, count: int = LATCH) -> pd.Series:
    return (series.groupby((series != series.shift()).cumsum())
                  .transform("count") >= count)
 
 
def add_trends(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy()
    # thresholds tuned for 12-h rolling on 2-hourly data
    g["Flow_trend"] = pct_trend_labels(g["NPF_sm"],      ROLL_WIN, 0.01, 0.03, 0.07)
    g["NSP_trend"]  = pct_trend_labels(g["NSP_sm"],      ROLL_WIN, 0.02, 0.05, 0.10)
    g["DP_trend"]   = pct_trend_labels(g["DP_sm"],       ROLL_WIN, 0.01, 0.03, 0.07)
    g["FP_trend"]   = pct_trend_labels(g["FeedPress_sm"],ROLL_WIN, 0.01, 0.03, 0.07)
    g["DP1_trend"]  = pct_trend_labels(g["DP_Stage_1_sm"],ROLL_WIN, 0.02, 0.05, 0.10)
    g["DP2_trend"]  = pct_trend_labels(g["DP_Stage_2_sm"],ROLL_WIN, 0.02, 0.05, 0.10)
    g["DP3_trend"]  = pct_trend_labels(g["DP_Stage_3_sm"],ROLL_WIN, 0.02, 0.05, 0.10)
 
    for c in ["Flow_trend", "NSP_trend", "DP_trend", "FP_trend",
              "DP1_trend", "DP2_trend", "DP3_trend"]:
        g[c + "_latch"] = latch_bool(g[c])
    return g
 
 
# ======================================================================
# 12-CATEGORY DIAGNOSIS (HZL production decision tree)
# ======================================================================
def diagnose_row(row: pd.Series) -> str:
    latches = [row.get("NSP_trend_latch", False),
               row.get("Flow_trend_latch", False),
               row.get("DP_trend_latch",  False),
               row.get("FP_trend_latch",  False)]
    if sum(bool(x) for x in latches) < 2:
        return "Normal Operation"
 
    n   = row.get("NSP_trend",  "STABLE")
    f   = row.get("Flow_trend", "STABLE")
    d   = row.get("DP_trend",   "STABLE")
    p   = row.get("FP_trend",   "STABLE")
    dp1 = row.get("DP1_trend",  "STABLE")
    dp2 = row.get("DP2_trend",  "STABLE")
    dp3 = row.get("DP3_trend",  "STABLE")
    n_stages = TRAIN_MAP.get(row.get("Train", ""), {}).get("stages", 3)
    last_dp  = dp3 if n_stages == 3 else dp2
 
    DOWN    = {"SLIGHT_DOWN", "MODERATE_DOWN", "SHARP_DOWN"}
    UP      = {"SLIGHT_UP", "MODERATE_UP", "SHARP_UP"}
    UP_MOD  = {"MODERATE_UP", "SHARP_UP"}
    FLAT    = {"STABLE", "SLIGHT_UP", "SLIGHT_DOWN"}   # "–" in doc = no significant change
    FLAT_UP = {"STABLE", "SLIGHT_UP", "MODERATE_UP"}
 
    # Membrane Rupture: sudden sharp NSP + sudden flow change, ΔP and feed stable
    if n == "SHARP_UP" and f in ("SHARP_UP", "SHARP_DOWN") and d in FLAT and p in FLAT:
        return "Membrane Rupture"
 
    # Oxidation / Chlorine Attack: sharp NSP rise only, no ΔP or feed change
    if n == "SHARP_UP" and f in FLAT and d in FLAT and p in FLAT:
        return "Oxidation / Chlorine Attack"
 
    # O-Ring Leak / Internal Bypass: flow UP + NSP UP, ΔP and feed stable
    if f in UP and n in UP and d in FLAT and p in FLAT:
        return "O-Ring Leak / Internal Bypass"
 
    # Pretreatment Restriction: flow↓, feed-P sharp up, ΔP stable, NSP stable
    if f in DOWN and p == "SHARP_UP" and d in FLAT and n in FLAT:
        return "Pretreatment Restriction"
 
    # Early Scaling: flow↓, NSP↑, tail-stage ΔP↑ moderate/sharp (dp3 for RO1, dp2 for RO2), feed↑
    if f in DOWN and n in UP and last_dp in UP_MOD and p in FLAT_UP:
        return "Early Scaling"
 
    # Early Stage Fouling: flow↓, NSP stable, lead-stage ΔP↑ moderate/sharp, feed↑
    if f in DOWN and n in FLAT and dp1 in UP_MOD and p in FLAT_UP:
        return "Early Stage Fouling"
 
    # Inorganic Scaling: flow↓, NSP↑ (moderate/sharp), overall ΔP↑, feed↑ (slight ok)
    if f in DOWN and n in UP_MOD and d in UP and p in FLAT_UP:
        return "Inorganic Scaling"
 
    # Organic Fouling: flow↓, NSP↑ slight only, ΔP↑, feed↑
    if f in DOWN and n == "SLIGHT_UP" and d in UP and p in UP:
        return "Organic Fouling"
 
    # Biofouling: flow↓, NSP flat/stable, ΔP↑ progressive (moderate/sharp), feed↑
    if f in DOWN and n in FLAT and d in UP_MOD and p in UP:
        return "Biofouling"
 
    # Particulate / Colloidal Fouling: flow↓, NSP stable, any ΔP↑, feed↑
    if f in DOWN and n in FLAT and d in UP and p in UP:
        return "Particulate / Colloidal Fouling"
 
    # Membrane Compaction: flow↓, NSP stable, ΔP stable or slight↑, feed↑
    if f in DOWN and n in FLAT and d in FLAT_UP and p in UP:
        return "Membrane Compaction"
 
    # Fallback: overall ΔP rising significantly but flow not yet declining
    if d in UP_MOD and f not in DOWN:
        if last_dp in UP_MOD:
            return "Early Scaling"
        return "Particulate / Colloidal Fouling"
 
    return "Normal Operation"
 
 
# ======================================================================
# CIP SEVERITY
# ======================================================================
def classify_cip(npf, nsp, dp, feed) -> str:
    # NSP excluded: feed TDS varies too much at this site to be a reliable CIP trigger.
    if any(pd.isna(x) for x in (npf, dp, feed)): return ""
    for sev in ("Critical", "Cleaning Required", "Due"):
        th = CIP_THRESH[sev]
        if (npf <= th["npf"]) or (dp >= th["dp"]) or (feed >= th["feed"]):
            return sev
    return ""
 
 
def latch_sev(values, n: int = LATCH):
    out, run, last = [], 0, ""
    for v in values:
        if v == last and v:
            run += 1
        else:
            run, last = (1 if v else 0), v
        out.append(v if run >= n else "")
    return out
 
 
# ======================================================================
# BUSINESS METRICS
# ======================================================================
def health_score(row: pd.Series) -> float:
    """0–100. Starts at 100 and subtracts for deviations vs baseline."""
    pen = 0.0
    pen += max(0, -row.get("NPF_pct", 0) or 0)       * 2.0
    pen += max(0,  row.get("NSP_pct", 0) or 0)       * 1.5
    pen += max(0,  row.get("DP_pct",  0) or 0)       * 1.2
    pen += max(0,  row.get("FeedPress_pct", 0) or 0) * 1.0
    return float(max(0, min(100, 100 - pen)))
 
 
def oee(train_df: pd.DataFrame) -> dict:
    """
    OEE = Availability × Performance × Quality
      • Availability: fraction of rows with non-null and > 0 permeate flow
      • Performance : mean(NPF_sm) / baseline NPF (capped at 1)
      • Quality     : fraction of rows where Permeate TDS < 500 mg/L (typical RO spec)
    """
    flow = train_df["PermFlow"]
    avail = float((flow.notna() & (flow > 0)).mean())
    baseline_day = train_df["Timestamp"].dt.date.min()
    base_npf = train_df.loc[train_df["Timestamp"].dt.date == baseline_day, "NPF_sm"].mean()
    cur_npf  = train_df["NPF_sm"].mean()
    perf = float(min(1.0, cur_npf / base_npf)) if base_npf and not pd.isna(base_npf) else np.nan
    qual = float((train_df["PermTDS"] < 500).mean()) if train_df["PermTDS"].notna().any() else np.nan
    overall = (avail * perf * qual) if all(pd.notna(x) for x in (avail, perf, qual)) else np.nan
    return dict(availability=avail, performance=perf, quality=qual, oee=overall,
                base_npf=base_npf, current_npf=cur_npf)
 
 
def _days_to_severity(sub: pd.DataFrame, severity: str) -> dict:
    th = CIP_THRESH[severity]
    t0 = sub["Timestamp"].iloc[0]
    x = (sub["Timestamp"] - t0).dt.total_seconds() / 86400.0
    current, slopes, days = {}, {}, {}
    for kpi, col, target, sign in [
        ("NPF",  "NPF_pct",       th["npf"],  "down"),
        ("NSP",  "NSP_pct",       th["nsp"],  "up"),
        ("DP",   "DP_pct",        th["dp"],   "up"),
        ("Feed", "FeedPress_pct", th["feed"], "up"),
    ]:
        y = sub[col].values
        if np.all(np.isnan(y)) or len(y) < 6: continue
        m, b = np.polyfit(x, y, 1)
        current[kpi] = float(y[-1])
        slopes[kpi]  = float(m)
        last_x = float(x.iloc[-1])
        if sign == "down":
            if m < 0 and y[-1] > target:
                days[kpi] = (target - b) / m - last_x
            elif y[-1] <= target:
                days[kpi] = 0.0
            else:
                days[kpi] = np.inf
        else:
            if m > 0 and y[-1] < target:
                days[kpi] = (target - b) / m - last_x
            elif y[-1] >= target:
                days[kpi] = 0.0
            else:
                days[kpi] = np.inf
        days[kpi] = max(0.0, days[kpi])
    return dict(current=current, slopes=slopes, days=days)
 
 
def forecast_days_to_cip(train_df: pd.DataFrame, severity: str = "Cleaning Required") -> dict:
    """
    Linear-regression forecast of days until each KPI breaches the target severity.
    If the requested severity is already breached (days=0), escalates to the next
    severity level so the card always shows a meaningful forward-looking number.
    """
    sub = train_df.dropna(subset=["NPF_pct", "NSP_pct", "DP_pct", "FeedPress_pct"])
    if len(sub) < 6:
        return dict(days_to_cip=np.nan, limiting_kpi=None, current={}, slopes={},
                    severity=severity, already_breached=False)
 
    result = _days_to_severity(sub, severity)
    days = result["days"]
    if not days:
        return dict(days_to_cip=np.nan, limiting_kpi=None,
                    current=result["current"], slopes=result["slopes"],
                    severity=severity, already_breached=False)
 
    lim = min(days, key=days.get)
    already_breached = days[lim] == 0.0
 
    # If this severity is already breached, escalate to next level
    if already_breached:
        next_sev_idx = SEV_ORDER.index(severity) + 1
        if next_sev_idx < len(SEV_ORDER) and SEV_ORDER[next_sev_idx]:
            escalated = _days_to_severity(sub, SEV_ORDER[next_sev_idx])
            e_days = escalated["days"]
            if e_days:
                e_lim = min(e_days, key=e_days.get)
                return dict(days_to_cip=e_days[e_lim], limiting_kpi=e_lim,
                            current=escalated["current"], slopes=escalated["slopes"],
                            severity=SEV_ORDER[next_sev_idx], already_breached=True,
                            all_days=e_days)
 
    return dict(days_to_cip=days[lim], limiting_kpi=lim,
                current=result["current"], slopes=result["slopes"],
                severity=severity, already_breached=already_breached, all_days=days)
 
 
# ======================================================================
# END-TO-END CONVENIENCE
# ======================================================================
def build_all(xlsx_path: str, temp_c: float | None = None,
              roll_win: int = ROLL_WIN) -> pd.DataFrame:
    raw = load_raw(xlsx_path)
    frames = []
    for train in TRAIN_MAP:
        g = build_train(raw, train, temp_c)
        g = add_smoothed(g, roll_win)
        g = add_trends(g)
        g["Diagnosis"]      = g.apply(diagnose_row, axis=1)
        g["Diagnosis_code"] = g["Diagnosis"].map(DIAG_CODE)
        g["Health"]         = g.apply(health_score, axis=1)
        g["CIP_raw"]        = [classify_cip(a, b, c, d) for a, b, c, d in
                               zip(g["NPF_pct"], g["NSP_pct"], g["DP_pct"], g["FeedPress_pct"])]
        g["CIP"]            = latch_sev(g["CIP_raw"])
        # If CIP threshold is breached but diagnosis tree still says Normal, override
        mismatch = (g["CIP"] != "") & (g["Diagnosis"] == "Normal Operation")
        g.loc[mismatch, "Diagnosis"] = "Early Stage Fouling"
        frames.append(g)
    return pd.concat(frames, ignore_index=True)
