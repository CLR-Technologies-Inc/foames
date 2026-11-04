# Case study: <short title>

| | |
| --- | --- |
| Status | Scaffold / Draft / Measured / Published |
| Data | Illustrative / Measured on site |
| Segment | Discrete / Process / Operational and logistics |
| Plant | Plant A (anonymised) |
| Period | Baseline: YYYY-MM-DD to YYYY-MM-DD. After: YYYY-MM-DD to YYYY-MM-DD |
| FoaMES version, Frappe version | |
| Authors, reviewed by | |

## 1. Summary

Three sentences: the problem, the change, the measured effect. Leave blank until section 6 is filled.

## 2. Context

- What the site makes or moves, and the volume.
- The constraint the change addresses (capacity, cost, emissions, safety, labour).
- Systems already in place (ERP, SCADA, telematics, fleet management), and which FoaMES adapter or gateway connects them.

## 3. The improvement

- What changed, when, and who owned it.
- What was deliberately not changed.
- Cost and effort, with the source of each figure.

## 4. Measurement design

| Metric | FoaMES source | Definition | Baseline window | After window |
| --- | --- | --- | --- | --- |
| | OEE Period, `get_oee`, Downtime Pareto, MTBF and MTTR, SPC Control Chart, Process Throughput, Andon Response | | | |

- Machines in scope and their Source IDs.
- Shift Pattern and planned time rules.
- Downtime Reasons used, and any change to them between windows.
- Counter Rollover and the unit of each counter.
- How Unknown time was handled (it stays loss).

## 5. Data connection

How events reached FoaMES: signed webhook, MQTT, OPC UA, Sparkplug B or an adapter. Event rate, known gaps in the data, and how long a silent machine counted as running (**Mark Machine Unknown After**).

## 6. Results

| Metric | Baseline | After | Change | Evidence (record or query) |
| --- | --- | --- | --- | --- |
| | | | | |

Include the downtime Pareto before and after, and any Agent Suggestions that were raised and what people did with them.

## 7. What else changed

Product mix, staffing, season, equipment age, a new shift pattern. State each as a possible confounder and which way it could bias the result.

## 8. Gaps

What FoaMES could not record or compute for this study. Each item should become an issue, an adapter change or a note in docs.

## 9. Lessons and next steps

What to repeat, what to avoid, and what to measure next.

## Sources

Cite every external figure. Mark vendor claims as claims.
