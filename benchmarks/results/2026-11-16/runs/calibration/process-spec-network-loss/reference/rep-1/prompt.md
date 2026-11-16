# A line that keeps dropping off the network

Line 7 intermittently loses its network connection, for anything from a few seconds to most of a shift. Its PLC keeps running and keeps counting. The plant manager's request, in full:

> Develop a process for reconstructing production performance after these outages without inflating output, incorrectly reporting availability, or creating duplicate ERP postings.

Do not write the implementation. Write the process and the specification an implementer would follow:

1. `PLAN.md` in the repository root, with these sections: Requirements, Ambiguities and questions, Invariants at risk, Design, Acceptance criteria, Risks, and What cannot be inferred. Tie every acceptance criterion to a requirement. Say which FoaMES modules and records the design touches.
2. Executable acceptance criteria in `acceptance/test_*.py`: unit tests against the current FoaMES code that pin down the behaviour the design relies on. They must pass now, and they must fail if that behaviour is broken later.

Do not change anything under `foames/`.

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
