# foames
Free Opensource Agentic MES

FOA MES is intended to be the visual technical MES you've always wanted. Simplified views over standard shop operations, integrated yields, core visuals in dashboards...WHAT A DREAM! 
Thanks for requirements and added some of my own. 
Intended for the Frappe ERP Next ecosystem, and designed with humans in mind. 

Other information is included in this project as a one stop shop for engineers looking LEAN, Six Sigma, SPC, and other manufacturing analytical tools, as they may eventually disappear from the internet.

## Architecture

FoaMES is a single Frappe app that depends on the Frappe framework only. ERP systems are optional and are reached through adapters, so the same core can run with ERPNext, with another ERP, or with no ERP at all.

| Module | What it holds |
| --- | --- |
| FoaMES Kernel | The shared records every FoaMES product builds on, plus `External Reference` (a pointer to a record in an ERP) and `FoaMES Settings` |
| FoaMES MES | Shop-floor execution: monitoring, downtime, OEE and machine data |
| FoaMES Adapters | The ERP adapter contract and the ERPNext adapter |

FoaMES records never use Link fields to ERP DocTypes. They store an `External Reference` (ERP system, reference type, external ID) and the matching adapter resolves it. The ERPNext adapter activates only when ERPNext is installed on the same site. Other apps can register more adapters through the `foames_erp_adapters` hook.

## Installation

FoaMES supports Frappe v15 and v16. ERPNext is optional.

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/CLR-Technologies-Inc/foames
bench --site $SITE install-app foames
```

## Contributing

This app uses `pre-commit` for formatting and linting (ruff, eslint, prettier):

```bash
cd apps/foames
pre-commit install
```

GitHub Actions runs the tests on Frappe v15 and v16 without an ERP, and on Frappe v16 with ERPNext. It also runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

## Prior art and credits

- [frappe/erpnext#50827](https://github.com/frappe/erpnext/issues/50827) asked for real-time machine monitoring, plant floor visibility, downtime tracking, OEE, work order and job card tracking, and PLC/IoT integration in ERPNext. It was closed as a product in its own right, and FoaMES takes up that requirement list.
- [Floorgraph](https://github.com/s1dharthpv/floorgraph) by [s1dharthpv](https://github.com/s1dharthpv) (MIT) is an earlier shop-floor execution app for ERPNext built in response to that issue. FoaMES is an independent implementation. If any Floorgraph code is ever reused, its MIT notice will ship with it.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright 2026 CLR Technologies Inc.
