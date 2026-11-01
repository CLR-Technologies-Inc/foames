# Software bill of materials (CycloneDX 1.7)

FoaMES publishes a [CycloneDX](https://cyclonedx.org/) 1.7 software bill of materials (SBOM) for every change on `main` and every release. A plant that runs FoaMES can load it into its vulnerability and license tooling, hand it to an auditor, or check it against its own OT security policy, without reading the source.

There is one SBOM per supported Frappe line, because FoaMES runs on whichever Frappe the bench installs and the transitive dependencies differ between v15 and v16:

| File | Describes |
| --- | --- |
| `foames-<version>-frappe-v15.cdx.json` | FoaMES with Frappe `version-15` on Python 3.11 |
| `foames-<version>-frappe-v16.cdx.json` | FoaMES with Frappe `version-16` on Python 3.14 |

## Where to get it

- **Releases:** attached as assets to each [GitHub release](https://github.com/CLR-Technologies-Inc/foames/releases).
- **Any commit on `main` or any pull request:** the **SBOM** workflow run keeps both files as workflow artifacts (`sbom-frappe-v15`, `sbom-frappe-v16`).

## What is in it

| Part of the document | Contents | Asserted by |
| --- | --- | --- |
| `metadata.component` | FoaMES itself: version, git commit, Apache-2.0, CLR Technologies Inc. as supplier, links to the source, license, docs and issues | `foames-sbom-builder` |
| `components` (libraries) | Frappe and every Python package it pulls in, plus `paho-mqtt` and `asyncua` and theirs, with versions, licenses, package URLs and the dependency graph | `cyclonedx-py` |
| `components` (ERPNext) | ERPNext as an optional application: the ERPNext adapter activates only when ERPNext is on the same site | maintainers (`sbom/curated.json`) |
| `components` (cryptographic assets) | A cryptography bill of materials (CBOM): every algorithm, protocol and kind of secret FoaMES uses, with the source file that uses it | maintainers (`sbom/curated.json`) |
| `services` | The endpoints FoaMES exposes (the machine-event webhook, the S/4HANA IDoc receiver), listed under `provides` in the dependency graph, and the services it connects to (the MQTT broker, OPC UA servers, SAP S/4HANA OData, the OAuth 2.0 token endpoint), listed under `dependsOn`, each with its trust boundary and data flow | maintainers (`sbom/curated.json`) |
| `citations` | Which tool or which people asserted each of the parts above (new in 1.7) | |
| `metadata.distributionConstraints` | `TLP:CLEAR`: the document may be shared without restriction, since FoaMES is public (new in 1.7) | |

### Scope

Every component carries a `scope`, worked out from the dependency graph rooted at FoaMES:

| Scope | Meaning | Examples |
| --- | --- | --- |
| `required` | Needed to run FoaMES at all: Frappe and everything it depends on | `frappe`, `werkzeug`, `pymysql` |
| `optional` | Needed only by a feature you may not use: the MQTT and Sparkplug B gateways, the OPC UA gateway, the ERPNext adapter | `paho-mqtt`, `asyncua` and what only they pull in, `erpnext` |
| `excluded` | Present in the scan environment but not part of FoaMES | `pip` |

If a vulnerability scanner reports a finding in an `optional` component, it matters only if you run that gateway or adapter.

### The cryptography bill of materials

The CBOM uses the 1.7 `algorithmFamily` names, so tools can group and audit them consistently:

| Asset | Used for | Where |
| --- | --- | --- |
| HMAC-SHA256 (family `HMAC`) | Signing and verifying machine events on the webhook, with a constant-time compare and a replay window | `foames/foames_mes/signing.py` |
| SHA-256 (family `SHA-2`) | Identifiers, not secrets: External Reference keys and the idempotency markers on ERPNext and S/4HANA postings | `external_reference.py`, `s4hana/outbox.py`, `erpnext/postings.py` |
| TLS | S/4HANA OData and IDoc calls, and MQTT or Sparkplug B when MQTT TLS is on. Version and ciphers come from the host's OpenSSL | `s4hana/odata.py`, `gateway/mqtt.py`, `gateway/sparkplug.py` |
| Webhook secret (secret key) | The shared HMAC key, in a Password field of Machine Data Settings | |
| ERP and broker credentials | S/4HANA Basic or OAuth 2.0 client credentials, MQTT and OPC UA passwords, in Password fields | |
| S/4HANA OAuth bearer token (token) | The access token from the OAuth 2.0 token endpoint, held in memory only | `s4hana/odata.py` |

FoaMES uses no asymmetric algorithms or elliptic curves of its own, so it has no post-quantum migration work beyond what TLS on the host provides.

The CBOM also makes one gap visible: the OPC UA gateway connects with a user name and password but sets no OPC UA message security policy, so the session is neither signed nor encrypted unless the plant network protects it. Run it only on a protected OT network segment until FoaMES supports `Basic256Sha256` or `Aes256_Sha256_RsaPss`.

## Using it

Validate a file against the CycloneDX 1.7 schema:

```bash
pip install "cyclonedx-python-lib[json-validation]"
python -c "import sys; from cyclonedx.schema import SchemaVersion; from cyclonedx.validation.json import JsonStrictValidator; print(JsonStrictValidator(SchemaVersion.V1_7).validate_str(open(sys.argv[1]).read()) or 'valid')" foames-0.0.1-frappe-v16.cdx.json
```

Scan it for known vulnerabilities, for example with [Grype](https://github.com/anchore/grype) (`grype sbom:foames-0.0.1-frappe-v16.cdx.json`) or by uploading it to an [OWASP Dependency-Track](https://dependencytrack.org/) project for continuous monitoring. Tools that do not yet read 1.7 ignore `citations` and `distributionConstraints`; if one rejects the file outright, convert it down with the [CycloneDX CLI](https://github.com/CycloneDX/cyclonedx-cli) (`cyclonedx convert --input-file foames.cdx.json --output-file foames-1.6.cdx.json --output-version v1_6`).

## Building it yourself

The workflow is `.github/workflows/sbom.yml`. The same steps by hand, for one Frappe line:

```bash
python -m venv /tmp/app-env
/tmp/app-env/bin/pip install "frappe @ git+https://github.com/frappe/frappe@version-16" paho-mqtt asyncua

python -m venv /tmp/cdx
/tmp/cdx/bin/pip install "cyclonedx-bom>=7.2.0" "cyclonedx-python-lib[json-validation]>=11.5.0"

/tmp/cdx/bin/cyclonedx-py environment --spec-version 1.7 --output-format JSON \
  --output-file /tmp/env.cdx.json /tmp/app-env/bin/python

SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)" /tmp/cdx/bin/python sbom/build_sbom.py \
  --env-bom /tmp/env.cdx.json --frappe-line v16 --out dist/foames-frappe-v16.cdx.json --validate
```

To scan the bench a site actually runs, point `cyclonedx-py environment` at `~/frappe-bench/env/bin/python` instead. That SBOM then also lists the other apps on the bench.

`sbom/build_sbom.py` uses only the standard library; `--validate` needs `cyclonedx-python-lib`. `SOURCE_DATE_EPOCH` makes the output reproducible: the same commit and Frappe line give the same serial number and timestamp. Its tests run with `python -m unittest discover -s sbom`.

## Keeping it true

The dependency scan is automatic; `sbom/curated.json` is not. When a change adds or removes an algorithm, a protocol, a kind of secret, or a service FoaMES connects to, update `sbom/curated.json` in the same pull request. A test checks that every source file the CBOM names still exists.

## CycloneDX beyond the FoaMES SBOM

An MES sits between business systems and machines, which is where most OT supply-chain risk lands. These are directions CycloneDX supports that FoaMES could take next; none of them is built yet.

| Idea | What it would do | CycloneDX feature |
| --- | --- | --- |
| Machine and SCADA software inventory | Record, on each Machine, a reference to the SBOM its vendor publishes for the PLC firmware, HMI, OPC UA server or Ignition gateway, so the plant can see which machines are exposed when a vulnerability lands. FoaMES would store a link and a hash, not parse vendor SBOMs | `externalReferences` of type `bom`, BOM-Link |
| VEX with each release | Say which reported vulnerabilities in FoaMES's dependencies actually affect FoaMES, so plants are not chasing findings in code paths FoaMES never calls | VEX (`vulnerabilities` with `analysis`) |
| Signed SBOMs and build provenance | Sign the SBOM in the release workflow and attach a build attestation, so a plant can check the file came from this repository | JSF signatures, GitHub artifact attestations |
| Compliance attestations | Map FoaMES controls to IEC 62443-4-1 and the EU Cyber Resilience Act's SBOM duties, with evidence, in a machine-readable form | CycloneDX Attestations (CDXA) |
| OPC UA security in the CBOM | When the OPC UA gateway gains message security, list its security policies and certificates as CBOM assets | CBOM `protocol` and `certificate` assets |
