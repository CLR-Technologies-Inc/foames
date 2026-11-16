## FoaMES

| Item | Value |
| --- | --- |
| Licence | [Apache License 2.0](https://github.com/CLR-Technologies-Inc/foames/blob/main/LICENSE) |
| Copyright | Copyright 2026 CLR Technologies Inc. |
| Notices | [NOTICE](https://github.com/CLR-Technologies-Inc/foames/blob/main/NOTICE), which must travel with redistributions |
| Contributions | Under a Contributor License Agreement: [Individual](https://github.com/CLR-Technologies-Inc/foames/blob/main/cla/ICLA.md) or [Corporate](https://github.com/CLR-Technologies-Inc/foames/blob/main/cla/CCLA.md), signed through CLA Assistant on your first pull request |

Under Apache-2.0 you may use, modify and redistribute FoaMES, including commercially and in closed products, provided you keep the licence and NOTICE, mark files you changed, and do not use the project's trademarks to endorse your product. Each contributor grants a patent licence for their contribution; that licence ends for anyone who sues claiming FoaMES infringes a patent. This is a summary, not legal advice; the licence text governs.

## Credits in NOTICE

- [frappe/erpnext#50827](https://github.com/frappe/erpnext/issues/50827), the requirement list FoaMES takes up.
- [Floorgraph](https://github.com/s1dharthpv/floorgraph) (MIT), an earlier, independent shop-floor app for ERPNext. FoaMES contains no Floorgraph code.
- [Bluesky](https://github.com/bluesky/bluesky) and [Tiled](https://github.com/bluesky/tiled) (BSD-3-Clause), whose published document model and client API the Bluesky bridge reads. None of their code is bundled.

## Main dependencies

Licences as published by each project; the SBOM below is the authoritative list for a given release.

| Component | Role | Licence | Scope |
| --- | --- | --- | --- |
| Frappe framework | Required | MIT | required |
| ERPNext | Optional, same site; FoaMES imports nothing from it | GPL-3.0 | optional |
| paho-mqtt | MQTT and Sparkplug B gateways | EPL-2.0 or EDL-1.0 | optional |
| asyncua | OPC UA gateway | LGPL-3.0 | optional |

Adapters talk to each vendor's published interfaces only. No vendor's proprietary code, API metadata or SDK is in the repository.

## Software bill of materials

FoaMES publishes a [CycloneDX](https://cyclonedx.org/) 1.7 SBOM for every change on `main` and every release, one per Frappe line (`foames-<version>-frappe-v15.cdx.json`, `foames-<version>-frappe-v16.cdx.json`).

| Where | How |
| --- | --- |
| Releases | Attached as assets to each [GitHub release](https://github.com/CLR-Technologies-Inc/foames/releases) |
| Any commit or pull request | Workflow artifacts `sbom-frappe-v15` and `sbom-frappe-v16` of the **SBOM** workflow |

It lists every library with version, licence, package URL and scope (`required`, `optional`, `excluded`), a cryptography bill of materials (algorithms, protocols, certificates and kinds of secret, with the file that uses each), and the services FoaMES exposes and connects to with their trust boundaries. It is marked `TLP:CLEAR`. A site-level CBOM of the deployed OPC UA certificates is written by `bench --site <site> execute foames.foames_mes.site_cbom.write`.

Details: [docs/sbom.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/sbom.md). Why FoaMES chose Apache-2.0 is explained in [Why Apache-2.0](Explanation-Why-Apache-2.0).
