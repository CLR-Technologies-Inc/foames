# Production counts jump after a PLC restart

Line 3's press reports its parts counter as a running total. Last night the PLC restarted at 02:14. Its counter went from 48,112 to 0 and then counted up again. FoaMES's OEE for that shift shows about 4,800 more good parts than the line made, and the planner already noticed.

Find out why FoaMES counted parts that were never made and fix it. Keep every counter rule that `AGENTS.md` describes, including rollover handling for machines whose Counter Rollover is known. Add tests that would have caught this.

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
