These features are in open pull requests on the repository. They are **not on `main`**, are not described elsewhere in this wiki, and may change or be dropped in review. Do not plan a rollout around them until they merge; this page will move each one into the tutorials, guides and reference when it does.

| Feature | What it will add | Pull request |
| --- | --- | --- |
| Read-only mode | Connectors read first; any write waits for an operator's e-signature, with an audit log | [#64](https://github.com/CLR-Technologies-Inc/foames/pull/64) |
| Enterprise risk management | A risk register, hierarchy of controls, risk tolerance and periodic review | [#66](https://github.com/CLR-Technologies-Inc/foames/pull/66) |
| Finite-capacity scheduling | Production scheduling against machine capacity | [#49](https://github.com/CLR-Technologies-Inc/foames/pull/49) |
| Time projections | Automatic and manual projections of when work will finish | [#47](https://github.com/CLR-Technologies-Inc/foames/pull/47) |
| Work instructions | Revision-controlled steps run at the station, citing their governing SOP | [#53](https://github.com/CLR-Technologies-Inc/foames/pull/53) |
| PFMEA | Process FMEA with AIAG-VDA action priority and a floor-observed occurrence check | [#51](https://github.com/CLR-Technologies-Inc/foames/pull/51) |
| Process validation and qualification | IQ, OQ, PQ, PPQ and continued process verification | [#50](https://github.com/CLR-Technologies-Inc/foames/pull/50) |
| Equipment commissioning | FAT and SAT, loop checks, punch list and handover | [#54](https://github.com/CLR-Technologies-Inc/foames/pull/54) |
| Environmental health and safety | Incidents, permits and lockout/tagout, hazards and exposure | [#55](https://github.com/CLR-Technologies-Inc/foames/pull/55) |
| P&ID support | A tag register, DEXPI and CSV import, and a live P&ID view | [#57](https://github.com/CLR-Technologies-Inc/foames/pull/57) |
| Topology graph | A live graph of the plant's machines and the data paths that serve them | [#59](https://github.com/CLR-Technologies-Inc/foames/pull/59) |
| Operator recognition | Kudos, credited ideas, milestones and team highlights | [#56](https://github.com/CLR-Technologies-Inc/foames/pull/56) |
| Vendor discovery skills | Read-only agent skills for discovering a site's vendor installations securely | [#65](https://github.com/CLR-Technologies-Inc/foames/pull/65) |
| Lineside inventory | Point-of-use stock per machine or line, read from the ERP and estimated from machine counts between reads, with reorder point, min-max or kanban replenishment. Nothing is written to the ERP | [#72](https://github.com/CLR-Technologies-Inc/foames/pull/72) |
| Material queues | The buffer in front of each machine, with FIFO, priority, earliest due or earliest expiry dispatch, minimum and maximum waits (Q-time, floor life, pot life), and starved or blocked machine detection | [#72](https://github.com/CLR-Technologies-Inc/foames/pull/72) |
| Dry-line alerts | Warnings before a line is starved of material (Reorder, Running Dry, Will Run Dry, Dry), allowing for lead time and conditioning time | [#72](https://github.com/CLR-Technologies-Inc/foames/pull/72) |
| Material processing complexity (MPC) | Materials rated 1 to 5 from standard handling factors. MPC 4 is Human Expert Recommended and MPC 5 is Expert Team Required. See [Material processing complexity](Explanation-Material-processing-complexity) | [#72](https://github.com/CLR-Technologies-Inc/foames/pull/72) |
| Equipment Complexity Level on Machine | An ECL field on each Machine, and agents tied to a machine only if their model tier meets its ECL. Planned, not yet in a pull request. The benchmark side is in [Equipment complexity levels](Explanation-Equipment-complexity-levels) | Planned |
| SPDX licence headers | One Apache-2.0 SPDX header in every source file, checked in CI, and a licensing guide | [#62](https://github.com/CLR-Technologies-Inc/foames/pull/62) |

To follow or comment on one, open its pull request. See [open pull requests](https://github.com/CLR-Technologies-Inc/foames/pulls) for the current list.
