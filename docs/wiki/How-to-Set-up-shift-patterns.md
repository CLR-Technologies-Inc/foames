**Goal:** compute OEE per shift instead of per day, and compare shifts.

**You need:** FoaMES Engineer or System Manager.

1. Open **Shift Pattern** and create one, for example *Three shifts*.
2. Under **Shifts**, add a row per shift with a name, a start time, a length in minutes and the weekdays it runs:

   | Name | Start | Minutes | Days |
   | --- | --- | --- | --- |
   | Early | 06:00 | 480 | Mon to Fri |
   | Late | 14:00 | 480 | Mon to Fri |
   | Night | 22:00 | 480 | Mon to Fri |

   Shifts must not overlap, including a Sunday night that runs into Monday. A shift belongs to the day it **starts** on.
3. Under **Non-Working Days**, add plant holidays and shutdowns. No shift starts on those dates.
4. On each **Machine** that follows the pattern, set **Shift Pattern**. The machine's Shift Start and Scheduled Minutes Per Day are then ignored.
5. Record scheduled breaks as Downtime Records with a reason that **Counts As Planned Downtime**. They are not part of the pattern.

## Check

- After the next daily run, the **OEE Period** list has one period per shift, with the shift's name in **Shift**.
- In the **OEE Trend** report, set **Group By** to **Shift** to compare shifts on a time-weighted basis.
- The Floor View tile shows the running shift.

A pattern applies to periods created after the change. To recompute a past day by shift, delete that day's periods and run:

```bash
bench --site $SITE execute foames.foames_mes.doctype.oee_period.oee_period.compute_daily_oee --kwargs "{'for_date': '2026-10-30'}"
```

More in [docs/oee.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/oee.md#shift-patterns).
