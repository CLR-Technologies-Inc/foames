# OEE from a state timeline that has holes in it

A cell's gateway sends a state event only when the machine's state changes (Running, Idle, Down, Setup). The gateway also drops off the network now and then, and nothing arrives while it is gone. The plant wants OEE for any window computed straight from that timeline, without a site.

Add a pure function to `foames/foames_mes/oee.py`:

```python
def ledger_from_timeline(changes, period_start, period_end, stale_after_minutes=None) -> TimeLedger: ...
```

- `changes` is an iterable of `(timestamp, state, planned)` tuples: a naive or aware `datetime` (all the same kind), the state the machine entered at that moment, and for a Down state whether the downtime was planned. They may arrive in any order.
- A state holds from its timestamp until the next change. Only time inside `[period_start, period_end)` counts; a change before `period_start` sets the state the window opens with.
- With `stale_after_minutes`, a state is trusted for at most that many minutes after the event that reported it; any time beyond that, until the next event, is a gap.
- Return a `TimeLedger` whose `planned_minutes` is the length of the window. Raise `ValueError` when `period_end` is not after `period_start`.

Treat the time the data does not cover the way FoaMES's rules say it must be treated, and keep `compute_oee` and `ledger_from_states` working as they do now.
