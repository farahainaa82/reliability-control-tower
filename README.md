# Reliability Control Tower

**Industrial AI portfolio prototype · Farah Ainaa Baharudin**

A maintenance decision-support demo for a fictional industrial fleet. The agent combines equipment criticality, sensor readings and maintenance history to assess current condition, project sensor limit crossings and compare response options. An urgent recommendation automatically opens an inspection draft for planner approval.

## Start in CodeBuddy

1. Extract the ZIP and open the `Reliability_Control_Tower` folder in CodeBuddy. Use Python 3.12.
2. Run these two commands in the integrated terminal. The first run downloads the Python packages.

   ```bash
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```

3. Open the local URL shown in the terminal. If you prefer using CodeBuddy's agent, give it this single prompt.

   > Open this existing project and run the Streamlit demo. From the project root, use Python 3.12 to install requirements.txt and run `python -m streamlit run app.py`. Give me the local URL. Change source files only if needed to fix a confirmed launch error, and keep any fix minimal. Stop when the app is running.

Using the terminal directly avoids an AI-agent request. After installation, the app runs locally without API keys, an LLM, a database or a live plant connection.

## Filter by site

Use the **Site** slicer to choose one or more of the three fictional sites. The fleet KPIs, priority queue, asset selectors and work orders follow the selection. Clear the selection to see the whole fleet. Agent scans and the decision log cover all sites.

## 60-second walkthrough

| Action | What to show |
| --- | --- |
| Open **Fleet overview** | Five assets across three sites. Select **North Processing Plant** to focus on cooling-water pump PMP-104 and instrument-air compressor CMP-201. The pump is on **Watch** and the compressor is **Stable** on the baseline sensor readings. |
| Select **Load early-warning data**, then **Run agent scan** | Three new hourly readings per asset are queued. CMP-201 is **Watch** (50/100) based on observed evidence. Both of its sensor readings are still below their demo limits. |
| Open **Decision Layer** | Vibration is **4.3 mm/s RMS** against a **4.5** limit. The projection reaches the limit at **07:24 site time**, about **24 minutes** ahead. The agent compares four responses and recommends an inspection within **15 minutes**. |
| Open **Work orders** | **WO-1001** includes the forecast, recommended response, suggested team and inspection scope. Planner approval moves it into the simulated queue. |
| Optional. Load simulated fault data and run another scan | At 10:00 site time, CMP-201 is **Critical**. The latest vibration and temperature readings exceed their limits. The agent recommends escalation and updates the same pending order. If already approved, the order remains as approved and the app flags the new recommendation for review. |
| Open **Decision log** | Review scan results, work-order changes and approval. Use **Reset demo** to start over. |

## Portfolio description

> This prototype connects condition monitoring to maintenance execution. When sensor readings trend toward an operating limit, the agent estimates how much time the team has, compares responses and drafts an inspection if action is urgent. The planner reviews the evidence before approving the order. A pilot could track alert-to-inspection time, unplanned downtime and the proportion of inspections that confirm a fault.

## Demo scope

The 0–100 risk index reflects current condition. The forecast extrapolates the slope of three consistently rising readings for up to six hours. It estimates when a sensor may reach its demo limit, conditional on the current trend. Response times, thresholds, readings and site details are simulated. Orders and the audit log last for the browser session and are cleared by a reload or **Reset demo**.

`app.py` renders the interface. `decision.py` projects crossings and compares responses. `reliability.py` scores observed evidence and drafts orders. The four CSVs in `data/` supply assets, maintenance history and telemetry. The baseline has 24 hourly readings per asset. The early warning uses the first three replay readings and the full replay uses all six.
