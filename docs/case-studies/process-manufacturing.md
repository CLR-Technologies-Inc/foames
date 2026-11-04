# Case study: yield, cycle time and specific energy on a process unit

| | |
| --- | --- |
| Status | Scaffold |
| Data | Illustrative (replace with measured data) |
| Segment | Process (batch or continuous) |
| Plant | Plant A (anonymised) |

## 1. Summary

TODO after results.

## 2. Context

TODO: product, batch size or throughput, quality specification, and the constraint (yield loss, long cleaning, energy cost, regulated release).

Process units rarely have a part cycle. Their counters are flow or energy totalisers: feed, product, steam, kWh. FoaMES stores the delta against the previous reading of the same counter, so a reset or an out-of-order reading yields zero and never invents production ([machine-data.md](../machine-data.md)).

## 3. The improvement

Pick one:

- Batch cycle time: shorter charge, heat, hold or clean phases.
- Yield: first-pass yield and rework from tighter control of a critical parameter.
- Specific energy: energy per unit of product, including idle consumption.
- Cleaning in place (CIP) scheduling as measured Setup or Cleaning time.

## 4. Measurement design

| Metric | FoaMES source | Definition |
| --- | --- | --- |
| Yield | product and feed counters | Product delta divided by feed delta over the window, state any density or unit conversion |
| Specific energy | energy and product counters | Energy delta divided by product delta; consumption with no product is reported, not hidden |
| Batch cycle time | state events, Process Event Log | Time from batch start to end; process mining shows where batches wait ([process-mining.md](../process-mining.md)) |
| Capability of a critical parameter | SPC Control Chart ([spc.md](../spc.md)) | I-MR chart of a Measurement event, with run-rule signals |
| OEE | OEE Period | Only where a planned production time is defined |

TODO: Counter Rollover for each totaliser, sampling interval of the measurement, and which ERP batch or work order references are attached.

If the plant is regulated (pharma, food), say which records are the system of record. FoaMES is not the batch record; the MES profile for the plant's system ([mes-adapters.md](../mes-adapters.md)) holds that.

## 5. Data connection

TODO: historian or SCADA to FoaMES path, and how loss of the signal is shown (Unknown, which counts as loss).

## 6. Results

TODO.

## 7. What else changed

TODO: raw material quality, ambient temperature and campaign length move yield and energy; record them.

## 8. Gaps

TODO: for example, no native recipe or genealogy model in FoaMES; note what was taken from the ERP or MES instead.

## 9. Lessons and next steps

TODO.
