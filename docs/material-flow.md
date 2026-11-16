# Material flow: lineside inventory, material queues, dry lines and MPC

FoaMES watches the material at the machines: the stock at each point of use, the material waiting in front of each machine, and how hard each material is to handle. It warns before a line runs dry, keeps queues in their dispatch order, flags material that is close to or past its queue-time limit, and scales the controls to the material's Material Processing Complexity (MPC).

The ERP stays the inventory system of record. FoaMES reads stock from the ERP through its adapter and never posts a stock movement. People call for material, move it and consume it against the job in the ERP; FoaMES tells them what to call for and when.

| Record | What it is |
| --- | --- |
| **Lineside Bin** | Point-of-use stock of one item at a machine or line, with its replenishment rule and its line-dry forecast |
| **Material Queue** | The buffer in front of a machine or work centre: dispatch rule, capacity, queue-time warning |
| **Material Queue Entry** | Material waiting in a queue: item, lot, quantity, job, minimum and maximum wait, expiry |
| **Material Handling Profile** | How complex a material is to handle and process, rated MPC 1 to 5 from standard handling factors |

The **FoaMES Material** workspace links them with the **Line Dry Forecast** and **Material Queue Status** reports.

## Lineside inventory

A Lineside Bin names the machine it feeds, the ERP item code and, for stock read from the ERP, the ERP location (an ERPNext warehouse) that holds the lineside stock. Item and location are kept as the ERP's own ids, not links, so the core runs with any ERP or none.

Every 10 minutes the material check:

1. **Reads the stock.** With Stock Source ERP, the quantity comes from the first reader in the `foames_stock_readers` hook that knows the item. The ERPNext adapter reads its Bin table (actual, projected, ordered, reserved and requested quantities). With Stock Source Manual, the last count a person entered is used.
2. **Estimates what was used since.** Units the machine counted since the read (good plus scrap) times the bin's Quantity per Unit Produced, plus its scrap allowance. This is backflush arithmetic, done only to estimate; nothing is posted.
3. **Measures the rate.** The same consumption over the bin's rate window (2 hours by default), per hour.
4. **Assesses the bin** and stores the status, hours to dry, the time it runs dry and the quantity to call for.

A read above the estimate means material arrived: the bin starts a new replenishment cycle.

### Replenishment rules

| Method | Call for |
| --- | --- |
| Reorder Point | One container (or up to the maximum) when stock on hand plus in transit reaches the reorder point |
| Min-Max | Up to the maximum when stock plus in transit reaches the reorder point (the minimum) |
| Kanban | One container for each card whose container is empty: cards minus full containers |
| Manual | Nothing is computed; the bin still forecasts when it runs dry |

For kanban bins FoaMES recommends the number of cards from what it measured, with the usual formula: cards = use per hour x replenishment lead time x (1 + safety margin) / container quantity, rounded up.

## Dry lines

A line runs dry when a machine is starved of material: its lineside stock is empty, or its queue holds nothing ready to start. Industry also calls this line starvation or a material shortage stop. The forecast warns while there is still time to act.

| Bin status | Meaning | Suggestion |
| --- | --- | --- |
| OK | Enough stock | none |
| Reorder | At the reorder point, or kanban cards are waiting | Info |
| Running Dry | Runs out inside the warning horizon | Warning |
| Will Run Dry | Runs out before a replenishment called now can arrive and be made ready | Critical |
| Dry | Empty: the machine is starved | Critical |

The lead time is the bin's replenishment lead time plus the material's conditioning time from its handling profile (thawing, degassing, baking, acclimatising). The warning horizon is that lead time times the MPC safety multiplier times one plus the warning margin (50 percent by default). Material already in transit holds off the dry warnings while it is on its way. A bin whose machine is not consuming has no dry forecast.

When a machine is starved, record the idle time with a No Material reason, so OEE shows the loss as availability lost to material, not as a machine fault. FoaMES never infers production from silence.

"Dry" has a second meaning on some floors: dry-process lines, such as battery cell assembly in dew-point controlled dry rooms, or dry granulation as opposed to wet. That is a property of the material and the room, not a stock level, so it is the **Atmosphere** factor of the material's handling profile (Dry room scores high).

## Material queues

A Material Queue sits in front of a machine or work centre. Each entry records when the material arrived and, when the material has them:

- a **minimum wait** before it may start: cure, degas, cool or thaw time;
- a **maximum wait**: the queue-time limit (Q-time) of a semiconductor fab, a pharmaceutical hold time, the floor life of a moisture-sensitive part (J-STD-033), the out-time of a composite prepreg or a pot life;
- an **expiry**: the lot's shelf-life or retest date.

| Readiness | Meaning |
| --- | --- |
| Conditioning | Still inside its minimum wait; may not start |
| Ready | May start |
| Q-time Warning | Has used the queue's warning share (80 percent by default) of its maximum wait |
| Q-time Exceeded | Past its maximum wait; never dispatched |
| Expired | Past its expiry; never dispatched |
| On Hold, In Process | From the entry's status |

### Dispatch rules

| Rule | Starts first |
| --- | --- |
| FIFO | The earliest arrival |
| Priority | The highest priority, then the earliest arrival |
| Earliest Due | The nearest due time |
| Earliest Expiry | The nearest queue-time limit or expiry (first expired, first out) |

The dispatch list (the queue's **Dispatch list** button, `get_dispatch_list`, the `foames_get_dispatch_list` MCP tool) shows what may start, in that order.

### Starting material

Setting an entry In Process is refused while it is conditioning. Material past its queue-time limit or expiry starts only with a reason, given by FoaMES Quality or FoaMES Engineer; otherwise a person holds it and decides its disposition (rework, recondition, requalify or scrap) under the site's procedure. MPC 5 material needs an expert review recorded on the entry before it starts, and MPC 4 material shows a reminder that one is recommended.

### Starved and blocked

The check raises a suggestion when a Running or Idle machine has nothing ready in its queue (starved), and when a queue holds as many waiting entries as its capacity (the machines feeding it are blocked). Each finding is raised once per episode: a starved queue is keyed on its last start or finish, a full one on its oldest waiting entry, so a dismissed suggestion stays dismissed until the queue moves.

## Material Processing Complexity (MPC)

MPC rates how complex a material is to handle and process on the floor, from 1 to 5. It is the material counterpart of the Equipment Complexity Level (ECL). No single standard scale exists for this, so MPC is built from factors that existing standards already define, each scored 0 to 4:

| Factor | Standard it comes from |
| --- | --- |
| Hazard | NFPA 704 highest rating; GHS signal words |
| Occupational exposure band | OEB 1 to 5 |
| Moisture sensitivity | IPC/JEDEC J-STD-033 MSL 1 to 6 |
| Storage temperature | USP <659>: controlled room temperature, refrigerated, frozen; cold chain practice |
| Atmosphere (dry process) | Dew-point controlled dry rooms; inert gas; gloveboxes and isolators |
| Cleanroom class at point of use | ISO 14644-1 |
| ESD sensitivity | ANSI/ESD S20.20; ANSI/ESDA/JEDEC JS-001 HBM classes |
| Physical form | Bulk solids flowability (Carr index, Hausner ratio, USP <1174>) |
| Shortest time limit | Shelf life (ICH Q1A), hold time, Q-time, floor life, out-time, pot life |
| Conditioning steps | Thaw, degas, bake, acclimatise, premix |
| Critical material attributes | ICH Q8 |

The highest factor sets the level (score 0 is MPC 1, score 4 is MPC 5). Three or more factors at score 2 or above compound and raise the level one more, up to 5.

| MPC | Label | Expert oversight | Line-dry safety multiplier |
| --- | --- | --- | --- |
| 1 | Standard | none | 1.0 |
| 2 | Basic controls | none | 1.1 |
| 3 | Controlled | none | 1.25 |
| 4 | Critical: Human Expert Recommended | a single expert | 1.5 |
| 5 | Extreme: Expert Team Required | a team of experts | 2.0 |

MPC changes how FoaMES treats the material: a time-sensitive material suggests the Earliest Expiry dispatch rule, conditioning time lengthens the line-dry lead time, the safety multiplier widens the warning horizon, MPC 4 and 5 are named in every suggestion, and MPC 5 material needs a recorded expert review to start. The levels and multipliers are starting priors to tune per site, not measured results.

## On the floor and for agents

- The floor snapshot gains a `material` section (`bins`, `queues`), and each machine gains `material`: bins, bins at risk, whether one is dry, the fewest hours to dry, queue waiting and ready counts.
- Suggestions use the category **Material** and the agent `foames-material`.
- MCP tools, all read-only: `foames_get_material_status`, `foames_get_dispatch_list`, `foames_get_material_readiness`.
- `foames.foames_mes.material_flow.material_readiness(machine, hours)` answers whether a machine has the material to run for the next hours. A scheduler can call it before dispatching an operation.

## Hooks

```python
# hooks.py of your app
foames_stock_readers = ["myapp.stock.read_stock"]  # (item, location) -> {"actual_qty": ...} or None
```

A reader for another ERP returns at least `actual_qty`; the first reader that knows the item wins, and a reader that fails is logged and skipped.

## What FoaMES does not do here

- It does not post stock movements, material requests or consumption to the ERP. Those stay with people in the ERP. An automatic call for material would be an ERP write and belongs behind the read-only write gate, signed off by a person.
- Queue entries carry the ERP's own lot id and a quantity only; the lot's history stays in the ERP.
