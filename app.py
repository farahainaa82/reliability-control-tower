"""Streamlit entry point for the Reliability Control Tower demo."""

from html import escape
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from decision import HORIZON_HOURS
from reliability import SIGNALS, scan

st.set_page_config(page_title="Reliability Control Tower", page_icon="⚙️", layout="wide")
st.html(Path(__file__).with_name("style.css"))
state = st.session_state
SCENARIOS = {"baseline": "BASELINE", "early": "EARLY WARNING", "fault": "FAULT REPLAY"}


def log(message):
    timestamp = state.results[0]["latest"]["timestamp"].strftime("%d %b · %H:%M")
    state.audit.append((timestamp, message))


def run_scan(manual=True):
    scenario = state.pending_scenario
    previous = {
        item["asset"]["asset_id"]: (item["priority"], item["score"])
        for item in state.get("results", [])
    }
    orders = state.orders.copy()
    results, created, updated = scan(scenario, orders)
    if scenario != state.scenario:
        state.selected_asset = results[0]["asset"]["asset_id"]
        state.decision_asset = max(results, key=lambda item: item["decision"]["rank"])["asset"]["asset_id"]
        state.pop("sensor", None)
        state.pop("forecast_sensor", None)
    state.results = results
    state.orders = orders
    state.scenario = scenario

    critical = sum(item["priority"] == "Critical" for item in results)
    watch = sum(item["priority"] == "Watch" for item in results)
    projected = sum(item["decision"]["earliest"] is not None for item in results)
    actions = []
    if created:
        actions.append(f"Drafted {', '.join(created)} for planner review.")
    if updated:
        actions.append(f"Updated {', '.join(updated)} for planner review.")
    detail = " ".join(actions) or "No new or updated drafts."
    finding = (f"Scanned {len(results)} assets across all sites. {critical} critical, {watch} on watch. "
               f"{projected} with a projected limit crossing. {detail}")
    log(finding)
    changed_orders = set(created + updated)
    for order in orders.values():
        if order["id"] in changed_orders:
            log(f"{order['id']} · {order['action']}. {order['decision_reason']}")

    if manual:
        state.manual_scans = state.get("manual_scans", 0) + 1
        changes = []
        for item in results:
            asset_id = item["asset"]["asset_id"]
            current = (item["priority"], item["score"])
            if asset_id not in previous:
                changes.append(f"{asset_id} added at {item['priority']} ({item['score']}/100).")
            elif previous[asset_id] != current:
                old_priority, old_score = previous[asset_id]
                changes.append(f"{asset_id} moved from {old_priority} ({old_score}/100) "
                               f"to {item['priority']} ({item['score']}/100).")
        current_ids = {item["asset"]["asset_id"] for item in results}
        changes.extend(
            f"{asset_id} was removed from the fleet."
            for asset_id in sorted(previous.keys() - current_ids)
        )
        readings = sum(len(item["readings"]) for item in results)
        history = sum(len(item["history"]) for item in results)
        change_summary = " ".join(changes) or "Priorities and risk scores are unchanged."
        state.scan_notice = (
            f"**Scan {state.manual_scans} complete.** {finding}  \n"
            f"Reviewed {readings} sensor records and {history} maintenance records. {change_summary}"
        )


def reset():
    state.scenario = "baseline"
    state.pending_scenario = "baseline"
    state.orders = {}
    state.audit = []
    state.manual_scans = 0
    state.scan_notice = ""
    state.pop("selected_asset", None)
    state.pop("sensor", None)
    state.pop("decision_asset", None)
    state.pop("forecast_sensor", None)
    run_scan(manual=False)


def load_scenario(scenario):
    state.pending_scenario = scenario


def approve(asset_id):
    order = state.orders[asset_id]
    if order["status"] == "Awaiting approval":
        order["status"] = "Approved · queued"
        log(f"Planner approved {order['id']} for {asset_id}. Inspection entered the demo queue.")


if "scenario" not in state or "site" not in state.results[0]["asset"]:
    reset()


def kpi(label, value, note, accent):
    st.html(f"""
    <div class="kpi" style="--accent:{accent}">
        <div class="kpi-label">{escape(label)}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-note">{escape(note)}</div>
    </div>
    """)


def priority_tag(priority):
    return f'<span class="priority {priority.lower()}">{priority}</span>'


def fleet_table(results):
    rows = []
    for item in results:
        asset = item["asset"]
        row_class = "critical-row" if item["priority"] == "Critical" else ""
        rows.append(f"""
        <tr class="{row_class}">
            <td><strong>{escape(asset['name'])}</strong><small>{escape(asset['asset_id'])}</small></td>
            <td>{escape(asset['site'])}</td>
            <td>{escape(asset['area'])}</td>
            <td>{priority_tag(item['priority'])}</td>
            <td class="score">{item['score']} <small>/ 100</small></td>
            <td>{escape(item['decision']['action'])}</td>
        </tr>""")
    st.html(f"""
    <div class="fleet"><table aria-label="Ranked asset priorities">
        <thead><tr><th>Asset</th><th>Site</th><th>Area</th><th>Current priority</th><th>Risk index</th><th>Recommended action</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table></div>
    """)


def trend_chart(result, signal, *, forecast=False):
    field, limit_field, label, unit, _, _ = signal
    readings = result["readings"][-6:] if forecast else result["readings"]
    limit = float(result["asset"][limit_field])
    times = [row["timestamp"].isoformat() for row in readings]
    values = [row[field] for row in readings]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=values, name=label, mode="lines+markers", fill="tozeroy",
        fillcolor="rgba(84,225,197,.10)", line={"color": "#54e1c5", "width": 2.5},
        marker={"size": 5, "color": ["#ff9995" if value > limit else "#54e1c5" for value in values]},
        hovertemplate=f"%{{x|%d %b %H:%M}} site time<br>%{{y:.1f}} {unit}<extra></extra>",
    ))
    fig.add_hline(y=limit, line={"color": "#ffc977", "width": 1.3, "dash": "dot"})
    if forecast:
        projection = result["decision"]["projections"][field]
        if projection["crossing"]:
            fig.add_trace(go.Scatter(
                x=[times[-1], projection["crossing"].isoformat()], y=[values[-1], limit],
                name="Projected", mode="lines+markers",
                line={"color": "#9fb7ff", "width": 3, "dash": "dash"},
                marker={"size": [0, 9], "symbol": "diamond"},
                hovertemplate=f"Projected<br>%{{x|%H:%M}} site time · %{{y:.1f}} {unit}<extra></extra>",
            ))
    elif state.scenario != "baseline" and len(times) > 24:
        fig.add_vrect(x0=times[24], x1=times[-1], fillcolor="#679ee8", opacity=.13, line_width=0, layer="below")
    low, high = min(values + [limit]), max(values + [limit])
    pad = max((high - low) * .16, .25)
    fig.update_layout(
        height=252, margin={"l": 10, "r": 14, "t": 7, "b": 10}, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#b7ccdd", "size": 11}, hoverlabel={"bgcolor": "#14283d"},
        xaxis={"type": "date", "nticks": 6, "tickformat": "%d %b\n%H:%M", "showgrid": False},
        yaxis={"range": [low - pad, high + pad], "gridcolor": "#23374b", "zeroline": False},
    )
    chart_key = "forecast_chart" if forecast else "telemetry_chart"
    st.plotly_chart(fig, theme=None, config={"displayModeBar": False}, width="stretch", key=chart_key)
    footnote = ""
    if forecast:
        footnote = " · Blue dashes show the projection when a crossing is forecast"
    elif state.scenario != "baseline":
        footnote = " · Shaded area shows the new batch"
    st.html(f'<div class="sensor-meta">Dotted amber line shows the demo limit · Simulated site time{footnote}</div>')


def assessment_panel(result):
    evidence = "".join(
        f'<li><span>{escape(label)}<small>{escape(detail)}</small></span><span class="points">+{points}</span></li>'
        for label, detail, points in result["evidence"]
    )
    st.html(f"""
    <div class="panel">
      <div class="section-code">AGENT ASSESSMENT</div>
      <h3>{priority_tag(result['priority'])} &nbsp; {result['score']} / 100</h3>
      <p class="action">{escape(result['action'])}</p>
      <p>{escape(result['asset']['impact'])}</p>
      <hr>
      <ul class="evidence">{evidence or '<li>No risk drivers flagged in this sample.</li>'}</ul>
    </div>
    """)


def history_panel(result):
    with st.expander("Maintenance history and service due date"):
        st.caption(f"Last preventive service {result['last_service']} · Scheduled service due {result['due_date']}")
        for row in sorted(result["history"], key=lambda record: record["date"], reverse=True):
            st.markdown(f"**{row['date']} · {row['event_type']}**  \n{row['note']}")


def decision_panel(result):
    decision = result["decision"]
    asset = result["asset"]
    st.html(f"""
    <div class="panel">
      <div class="section-code">PRESCRIPTIVE · RECOMMENDED ACTION</div>
      <h3>{escape(decision['action'])}</h3>
      <p class="action">{escape(decision['window'])}</p>
      <p>{escape(decision['reason'])}</p>
      <hr>
      <p><strong>Operational impact</strong> · {escape(asset['impact'])}</p>
    </div>
    """)
    order = state.orders.get(asset["asset_id"])
    if order and order["action"] != decision["action"]:
        st.warning(f"{order['id']} was approved for an earlier recommendation. Review it against the current action.")
    elif order:
        st.caption(f"{order['id']} · {order['status']} · See the Work orders tab.")


def compare_options(options):
    rows = []
    for action, timing, effort, verdict in options:
        style = ' class="recommended-row"' if verdict == "Recommended" else ""
        rows.append(f"""<tr{style}>
            <td><strong>{escape(action)}</strong><small>{escape(effort)}</small></td>
            <td>{escape(timing)}</td>
            <td>{escape(verdict)}</td>
        </tr>""")
    st.html(f"""
    <div class="fleet"><table aria-label="Maintenance options">
        <thead><tr><th>Option</th><th>Simulated response time</th><th>Agent assessment</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table></div>
    """)


st.html("""
<div class="hero">
  <svg viewBox="0 0 560 240" fill="none" aria-hidden="true" preserveAspectRatio="xMaxYMax slice">
    <defs><pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
      <path d="M30 0H0V30" stroke="#5598a8" stroke-opacity=".24"/></pattern>
      <linearGradient id="wave" x1="0" x2="1"><stop stop-color="#65e9d0" stop-opacity="0"/><stop offset="1" stop-color="#65e9d0"/></linearGradient>
    </defs>
    <rect width="560" height="240" fill="url(#grid)"/>
    <path d="M5 154H205L233 138L258 168L286 117L316 190L357 79L385 153L417 126L443 154H560" stroke="url(#wave)" stroke-width="2"/>
    <path d="M83 189H476M143 103H506" stroke="#6be6d2" stroke-opacity=".20" stroke-dasharray="5 7"/>
    <circle cx="357" cy="79" r="5" fill="#78f4da"/><circle cx="357" cy="79" r="14" stroke="#78f4da" stroke-opacity=".44"/>
    <path d="M483 53H527V97M483 217H527V173" stroke="#69dbc9" stroke-opacity=".44"/>
  </svg>
  <div class="eyebrow">INDUSTRIAL AI &nbsp;/&nbsp; PREDICTIVE MAINTENANCE</div>
  <h1>Reliability Control Tower</h1>
  <p>Detect deterioration, project sensor limit crossings, and recommend an action for planner review.</p>
  <span class="demo-tag">SIMULATED INDUSTRIAL FLEET</span>
</div>
""")

site_names = sorted({item["asset"]["site"] for item in state.results})
site_control, site_scope = st.columns([1.5, 1], vertical_alignment="bottom")
with site_control:
    selected_sites = st.multiselect("Site", site_names, placeholder="All sites", key="site_filter")
with site_scope:
    st.caption("Choose one or more sites to filter the dashboard. Agent scans cover all sites.")

visible_results = [
    item for item in state.results
    if not selected_sites or item["asset"]["site"] in selected_sites
]
assets_by_id = {item["asset"]["asset_id"]: item for item in visible_results}
visible_orders = {
    asset_id: order for asset_id, order in state.orders.items()
    if asset_id in assets_by_id
}
if state.get("selected_asset") not in assets_by_id:
    state.selected_asset = next(iter(assets_by_id))
if state.get("decision_asset") not in assets_by_id:
    state.decision_asset = max(visible_results, key=lambda item: item["decision"]["rank"])["asset"]["asset_id"]

scan_control, early_control, fault_control, restore, timestamp = st.columns(
    [1.15, 1.35, 1.55, .85, 1.65], vertical_alignment="center"
)
with scan_control:
    st.button("Run agent scan", type="primary", on_click=run_scan, width="stretch")
with early_control:
    st.button("Load early-warning data", on_click=load_scenario, args=("early",),
              disabled=state.pending_scenario != "baseline", width="stretch")
with fault_control:
    st.button("Load simulated fault data", on_click=load_scenario, args=("fault",),
              disabled=state.pending_scenario == "fault", width="stretch")
with restore:
    st.button("Reset demo", on_click=reset, width="stretch")
with timestamp:
    phase = SCENARIOS[state.scenario]
    data_time = max(item["latest"]["timestamp"] for item in visible_results).strftime("%d %b %Y · %H:%M")
    st.html(f'<div class="sensor-meta"><strong>{phase}</strong> &nbsp;·&nbsp; {data_time}<br>Simulated site time</div>')

if state.pending_scenario != state.scenario:
    st.info(f"{SCENARIOS[state.pending_scenario].capitalize()} data is ready. Select **Run agent scan** to assess the new readings.")
elif state.get("scan_notice"):
    st.success(state.scan_notice)

critical = sum(item["priority"] == "Critical" for item in visible_results)
watch = sum(item["priority"] == "Watch" for item in visible_results)
pending = sum(order["status"] == "Awaiting approval" for order in visible_orders.values())
site_note = f"Showing {len(selected_sites)} of {len(site_names)} sites" if selected_sites else "Showing all sites"
for column, stats in zip(st.columns(4), (
    ("Assets monitored", len(visible_results), site_note, "#8ed5ff"),
    ("Critical priority", critical, "Based on observed data", "#ffa5a1"),
    ("Watch list", watch, "Verify at next round", "#ffdc9b"),
    ("Awaiting approval", pending, "Planner sign-off", "#7debd5"),
)):
    with column:
        kpi(*stats)

st.html("""
<div class="chain"><strong>AGENT LOOP</strong> Read telemetry &amp; history
 <span class="arrow">→</span> Assess condition <span class="arrow">→</span> Project limits
 <span class="arrow">→</span> Compare actions <span class="arrow">→</span> Draft inspection
 <span class="arrow">→</span> Planner approval</div>
""")

fleet_tab, decision_tab, orders_tab, audit_tab = st.tabs(
    ["Fleet overview", "Decision Layer", "Work orders", "Decision log"]
)
with fleet_tab:
    st.subheader("Maintenance priority queue")
    fleet_table(visible_results)
    st.caption("The current risk index uses observed data. The recommended action also considers the sensor forecast.")
    st.subheader("Asset diagnostics")
    st.selectbox("Asset to investigate", options=list(assets_by_id),
                 format_func=lambda key: f"{key} · {assets_by_id[key]['asset']['name']}", key="selected_asset")
    selected = assets_by_id[state.selected_asset]
    sensor_column, assessment_column = st.columns([1.6, 1], gap="large")
    with sensor_column:
        sensor_label = st.radio("Sensor trend", [signal[2] for signal in SIGNALS], horizontal=True, key="sensor")
        signal = next(signal for signal in SIGNALS if signal[2] == sensor_label)
        field, limit_field, _, unit, _, _ = signal
        limit = float(selected["asset"][limit_field])
        st.html(f'<div class="sensor-meta">Latest <strong>{selected["latest"][field]:.1f} {unit}</strong> · Demo limit {limit:g} {unit}</div>')
        trend_chart(selected, signal)
    with assessment_column:
        assessment_panel(selected)
    history_panel(selected)

with decision_tab:
    st.subheader("Decision Layer")
    st.selectbox("Asset to assess", options=list(assets_by_id),
                 format_func=lambda key: f"{key} · {assets_by_id[key]['asset']['name']}", key="decision_asset")
    selected = assets_by_id[state.decision_asset]
    forecast_column, recommendation_column = st.columns([1.55, 1], gap="large")
    with forecast_column:
        st.markdown("**Predictive · Sensor limit forecast**")
        sensor_label = st.radio("Forecast sensor", [signal[2] for signal in SIGNALS],
                                horizontal=True, key="forecast_sensor")
        signal = next(signal for signal in SIGNALS if signal[2] == sensor_label)
        projection = selected["decision"]["projections"][signal[0]]
        st.caption(f"Latest {projection['value']:g} {signal[3]} · Demo limit {projection['limit']:g} {signal[3]}")
        if projection["crossing"]:
            minutes = round(projection["hours"] * 60)
            st.warning(f"**Projected limit crossing in about {minutes} min** "
                       f"({projection['crossing']:%H:%M} site time) if the recent trend continues.")
        elif projection["exceeded"]:
            st.warning("Latest reading is already at or above the demo limit.")
        else:
            st.info(f"No qualifying crossing projected within {HORIZON_HOURS} hours.")
        trend_chart(selected, signal, forecast=True)
    with recommendation_column:
        decision_panel(selected)
    st.markdown("**Compare response options**")
    compare_options(selected["decision"]["options"])
    with st.expander("How the forecast and recommendation are made"):
        st.markdown(f"""
The forecast uses the slope of the last three observed readings. It requires a
consistent rise of at least 0.2 mm/s RMS per hour or 1 °C per hour, depending on
the sensor. It projects from the latest reading up to {HORIZON_HOURS} hours ahead
and assumes the same rate of change. This is a simulated sensor-limit estimate.

The decision policy compares response times against the earliest qualifying
crossing. It recommends escalation for a current critical condition or when a
priority inspection would arrive too late. Simulated response times start at
the latest reading. Urgent recommendations create an inspection draft for planner approval.
""")

with orders_tab:
    st.subheader("Inspection work orders")
    st.caption("Priority inspections and escalations create a draft automatically. Planner approval moves it into the simulated queue.")
    if not visible_orders:
        st.info("No inspection work orders for the sites shown.")
    for asset_id, order in visible_orders.items():
        st.html(f"""
        <div class="panel">
          <div class="section-code">{escape(order['id'])} &nbsp;·&nbsp; {escape(asset_id)} &nbsp;·&nbsp; P1 INSPECTION</div>
          <h3>{escape(order['asset_name'])}</h3>
          <p>{escape(assets_by_id[asset_id]['asset']['site'])}</p>
          <p class="action">{escape(order['status'])}</p>
          <p><strong>{escape(order['action'])}</strong></p>
          <p>{escape(order['owner'])} · {escape(order['window'])}</p>
          <hr>
          <p><strong>Inspection scope</strong> · {escape(order['scope'])}</p>
          <p><strong>Decision basis</strong> · {escape(order['decision_reason'])}</p>
          <p><strong>Agent evidence</strong> · {escape(order['reason'])} · Index {order['score']}/100</p>
        </div>
        """)
        if order["status"] == "Awaiting approval":
            st.button("Approve & queue inspection", key=f"approve_{asset_id}", type="primary",
                      on_click=approve, args=(asset_id,))
        else:
            st.success(f"{order['id']} is in the simulated maintenance queue.")
            latest_decision = assets_by_id.get(asset_id, {}).get("decision")
            if latest_decision and latest_decision["action"] != order["action"]:
                st.warning(f"Current recommendation: {latest_decision['action']}. Review this approved order.")

with audit_tab:
    st.subheader("Agent and planner activity")
    st.caption("Fleet-wide activity across all sites. Latest events first, in simulated site time.")
    events = "".join(f'<div class="event"><time>{escape(time)}</time>{escape(message)}</div>'
                     for time, message in reversed(state.audit))
    st.html(f'<div class="panel">{events}</div>')
    with st.expander("Scoring policy"):
        st.markdown("""
- **+30** vibration and **+20** temperature, each when at least two of the last three hourly readings exceed its asset limit.
- **+20** if either sensor rises sharply. Compare the latest three-hour mean with the previous three-hour mean. The demo thresholds are 0.8 mm/s RMS and 6 °C.
- **+15** for overdue preventive service. Add **+15** for high asset criticality when a sensor limit or rapid-rise rule triggers.
- **0–34** Stable, **35–69** Watch, **70–100** Critical. The Decision Layer separately uses projections and current conditions to recommend a response.
""")

st.caption("Synthetic data · Rule-based agent · Simulated work-order queue")
