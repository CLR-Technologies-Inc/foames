**Goal:** set up a development environment, make a change and get it merged.

## 1. Set up

Follow [Tutorial 1](Tutorial-1-Install-FoaMES), then:

```bash
bench --site foames.localhost set-config allow_tests true
cd apps/foames && pre-commit install
```

Or use the [Docker dev bench](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/dev-bench.md): `cd docker && ./bench.sh up && ./bench.sh test` runs the CI matrix (Frappe v15, v16, and v16 with an ERP app) in containers.

## 2. Run the tests

```bash
# pure-logic tests, no site needed
python -m unittest foames.foames_mes.test_oee_and_rules foames.foames_mes.test_machine_data_logic foames.foames_mes.test_sparkplug foames.foames_mes.test_kpi
python -m unittest foames.foames_process_mining.test_process_mining_logic foames.foames_mcp.test_mcp_protocol

# everything, on a bench
bench --site foames.localhost run-tests --app foames
```

## 3. Make the change

- Read [AGENTS.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/AGENTS.md) first. It lists the invariants (no Link fields to ERP DocTypes, counters never invent production, agents only suggest) and where each kind of change belongs.
- Put arithmetic in a pure module with a unit test, and keep Frappe code thin around it.
- Strings shown to users go through `frappe._`. Formatting is ruff, eslint and prettier through pre-commit.
- Adding cryptography, a secret or a connected service? Update `sbom/curated.json` in the same pull request.

## 4. Sign the CLA and open a pull request

Contributions need a signed Contributor License Agreement. You keep your copyright; the CLA grants a copyright and patent licence on Apache terms.

- **As an individual:** open your pull request. The CLA Assistant check posts a link; sign in with GitHub and accept the [Individual CLA](https://github.com/CLR-Technologies-Inc/foames/blob/main/cla/ICLA.md). You sign once.
- **For an employer:** the employer signs the [Corporate CLA](https://github.com/CLR-Technologies-Inc/foames/blob/main/cla/CCLA.md) once and lists you on Schedule A.

Keep each pull request to one change, explain why it is needed, add or update tests, and credit any third-party code with its licence notice. CI runs the tests on Frappe v15 and v16 with and without an ERP, plus Frappe's semgrep rules, pip-audit and the SBOM build.

See [CONTRIBUTING.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/CONTRIBUTING.md).
