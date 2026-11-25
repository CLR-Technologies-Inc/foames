# Licensing

FoaMES is licensed under the [Apache License 2.0](../LICENSE). Copyright 2026 CLR Technologies Inc. Contributors keep the copyright in their work and license it to everyone under Apache-2.0 through the [CLA](../CONTRIBUTING.md#contributor-license-agreement). [NOTICE](../NOTICE) carries the third-party notices and credits that must travel with the code.

## File headers

Every Python, JavaScript, shell, YAML, TOML, CSS, HTML, pip requirements and Dockerfile source file starts with the Apache License 2.0 boilerplate notice (the one in the appendix of [LICENSE](../LICENSE)), followed by the SPDX identifier:

```python
# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
```

`//` comments are used in JavaScript, a `/* */` block in CSS and an `<!-- -->` block in HTML. The notice goes after the `#!` line in scripts and after `<!doctype html>` in HTML. The copyright line says who holds the copyright, the notice states the license grant and the disclaimer, and the [SPDX identifier](https://spdx.org/licenses/Apache-2.0.html) names the license in a form tools can read. JSON (DocType definitions) and Markdown files carry no full notice, as comments are not possible or not customary there; the repository [LICENSE](../LICENSE) covers them, and Markdown pages that have a header keep the short `<!-- Copyright ... -->` and `<!-- SPDX-License-Identifier: Apache-2.0 -->` comments. Generated output under `benchmarks/results/` is not checked.

`.github/scripts/check_license_headers.py` checks this on every pull request (through `pre-commit`) and locally after `pre-commit install`. Run it with `--fix` to add the notice to new files, or to replace the older two-line header. A third-party file that keeps its own header goes on the script's `THIRD_PARTY` list, with an entry in NOTICE.

### History

The repository was created with a BSD 3-Clause LICENSE file and relicensed to Apache-2.0 a day later, before any outside contribution; CLR wrote all of the code up to then, so it could relicense it. The DocType, report and page files kept the header that Frappe's generator writes ("For license information, please see license.txt"). In a new Frappe app that file exists; here the license lives in LICENSE, so the reference dangled. Those headers were replaced with a two-line copyright and SPDX header (PR #62), which was then expanded to the full Apache-2.0 notice above.

## Dependencies and sources

FoaMES bundles no third-party code. Everything below is installed separately (by bench, pip or the user), or is a specification or design that FoaMES was written from. The [SBOM](sbom.md) published with each release lists every installed package with its license.

| Component | License | How FoaMES uses it | Compatible with Apache-2.0 |
|---|---|---|---|
| [Frappe Framework](https://github.com/frappe/frappe) | MIT | The platform FoaMES runs on; the app scaffold was generated from Frappe's templates (notice in NOTICE). Werkzeug and the rest of Frappe's stack come with it. | Yes |
| [ERPNext](https://github.com/frappe/erpnext) | GPL-3.0 | Optional. The ERPNext adapter calls ERPNext's public functions at run time through `frappe.get_attr`, only when ERPNext is installed on the same site. No ERPNext code is copied, the core installs and passes its tests without it, and only the integration tests import it. | Yes, see below |
| [paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) | EPL-2.0 or EDL-1.0 (BSD-3-Clause) | Optional; MQTT and Sparkplug B gateways, imported only when they run | Yes |
| [asyncua](https://github.com/FreeOpcUa/opcua-asyncio) | LGPL-3.0 | Optional; OPC UA gateway, imported only when it runs | Yes, see below |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause | Optional; OPC UA certificate trust and the site CBOM | Yes |
| [Bluesky](https://github.com/bluesky/bluesky), [Tiled](https://github.com/bluesky/tiled), [ophyd](https://github.com/bluesky/ophyd) | BSD-3-Clause | Optional extras of `bridges/bluesky`; ophyd only in its tests | Yes |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT | Tests only; the MCP server itself uses the standard library | Yes |
| [CycloneDX Python](https://github.com/CycloneDX/cyclonedx-python) tools | Apache-2.0 | CI only, to build the SBOM | Yes |
| [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) | see that repository | CI only, fetched at run time, not distributed | Not distributed |
| Sparkplug B and OPC UA specifications | Public specifications | The Sparkplug B decoder is written from the specification; no Eclipse Tahu code | Yes |
| Vendor APIs (SAP S/4HANA, MES and IIoT platforms) | Vendor terms | Adapters are written from public documentation only; no vendor code, SDKs or API metadata (see each adapter's `AGENTS.md`) | Yes |
| [Floorgraph](https://github.com/s1dharthpv/floorgraph), [FactorySemantics MES](https://github.com/factorysemantics/factorysemantics-mes), [frappe/erpnext#50827](https://github.com/frappe/erpnext/issues/50827) | MIT, Apache-2.0, issue | Prior art and requirements, credited in NOTICE; no code copied | Yes |

### ERPNext (GPL-3.0)

Apache-2.0 code may be combined with GPL-3.0 code: the Free Software Foundation lists Apache-2.0 as compatible with GPLv3. FoaMES's own source stays Apache-2.0 whether or not ERPNext is present. If you distribute FoaMES and ERPNext together as one combined work, the GPL-3.0 terms apply to that combination as a whole, which Apache-2.0 allows. Using them together on your own site is not distribution.

To keep this clean, FoaMES does not copy ERPNext code, does not import ERPNext at module level and has no Link fields to ERPNext DocTypes ([adapter rules](../foames/foames_adapters/AGENTS.md)). Contributions that copy ERPNext code will not be accepted.

### asyncua (LGPL-3.0)

FoaMES uses asyncua as an unmodified library that the user installs, which the LGPL allows for software under any license. If you ship asyncua inside an image or installer, include its license and source (or a link to it), and keep it replaceable, as the LGPL requires.
