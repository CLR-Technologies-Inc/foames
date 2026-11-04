# A line that keeps dropping off the network

Line 7 intermittently loses its network connection, for anything from a few seconds to most of a shift. Its PLC keeps running and keeps counting. The plant manager's request, in full:

> Develop a process for reconstructing production performance after these outages without inflating output, incorrectly reporting availability, or creating duplicate ERP postings.

Do not write the implementation. Write the process and the specification an implementer would follow:

1. `PLAN.md` in the repository root, with these sections: Requirements, Ambiguities and questions, Invariants at risk, Design, Acceptance criteria, Risks, and What cannot be inferred. Tie every acceptance criterion to a requirement. Say which FoaMES modules and records the design touches.
2. Executable acceptance criteria in `acceptance/test_*.py`: unit tests against the current FoaMES code that pin down the behaviour the design relies on. They must pass now, and they must fail if that behaviour is broken later.

Do not change anything under `foames/`.
