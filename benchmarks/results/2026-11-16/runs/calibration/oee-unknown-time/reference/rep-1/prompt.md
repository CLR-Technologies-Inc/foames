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

## How to work

- This directory is a copy of FoaMES, an ERP-agnostic manufacturing execution system on the Frappe framework. Read `AGENTS.md` first: it lists the invariants every change must keep.
- No Frappe site is available. The modules this task touches are pure Python. Run tests like this from the repository root:

  ```
  PYTHONPATH=.foames-bench/stubs:. python -m unittest foames.foames_mes.test_machine_data_logic
  ```

  `.foames-bench/stubs` holds a stand-in `frappe` package that only lets imports succeed; do not change it.
- Add or update unit tests for what you change, next to the module, in a `test_*.py` file.
- Keep the change to what the task needs. Do not reformat unrelated code.
- When you finish, write `BENCH_NOTES.md` in the repository root: what you changed, what you assumed, and anything the data or the request cannot tell you. A few short paragraphs are enough.
- Work without asking questions; nobody will answer. Where the request is ambiguous, choose the reading that keeps the plant's numbers honest, and say so in `BENCH_NOTES.md`.
