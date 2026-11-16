# Catch small drifts in a coating thickness

Quality engineering measures coating thickness on every part. The I-MR chart in `foames/foames_mes/spc.py` catches big jumps but misses the slow 0.5 to 1 sigma drifts that come from a nozzle wearing. They want an EWMA chart next to the Shewhart charts.

Add to `foames/foames_mes/spc.py`:

```python
def ewma_chart(values, lam=0.2, L=3.0, baseline=None) -> dict: ...
```

- The centre line is the mean of the first `baseline` values (all of them when None) and sigma is estimated the same way `imr_chart` does it, from the average moving range of those baseline values. Every value is then judged against those limits.
- The EWMA statistic starts at the centre line: `z_i = lam * x_i + (1 - lam) * z_(i-1)`.
- Use the exact, time-varying limits for point i (counting from 1): `cl ± L * sigma * sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * i)))`.
- Return a dict with `chart` ("EWMA"), `points` (the z values), `cl`, `ucl` and `lcl` (lists, one limit per point), `signals` (a list of dicts with at least `index`, counted from 0, and `rule` set to "EWMA") for points strictly outside their limits, `sigma_within`, `lambda`, `L` and `baseline_points`.
- Raise `ValueError` for `lam` outside (0, 1], for `L` not above zero, and for fewer than two baseline values (including a `baseline` of zero or less).

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
