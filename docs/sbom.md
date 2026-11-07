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
| `components` (cryptographic assets) | A cryptography bill of materials (CBOM): every algorithm, protocol, certificate and kind of secret FoaMES uses, with the source file that uses it | maintainers (`sbom/curated.json`) |
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
| OPC UA secure channel (protocol, type `other`) | Message security between the OPC UA gateway and the server when Machine Data Settings chooses `Sign` or `SignAndEncrypt`. Its three cipher suites are the offered policies, each with its OPC UA policy URI and the algorithms below | `gateway/opcua.py`, `machine_data_settings.py` |
| RSA-OAEP with SHA-1 and with SHA-256 (family `RSAES-OAEP`) | Encrypting the OPC UA handshake to the server's certificate, and the password token when the server asks for it. SHA-1 is the OAEP padding hash the `Basic256Sha256` and `Aes128_Sha256_RsaOaep` profiles fix; `Aes256_Sha256_RsaPss` uses SHA-256 | `gateway/opcua.py` |
| RSA PKCS#1 v1.5 with SHA-256 (family `RSASSA-PKCS1`), RSA-PSS with SHA-256 (family `RSASSA-PSS`) | Signing the OPC UA handshake with the gateway's key and verifying the server's. PKCS#1 v1.5 under the first two policies, PSS under `Aes256_Sha256_RsaPss`. PKCS#1 v1.5 with SHA-256 is also what the profiles require on the certificates | `gateway/opcua.py` |
| AES-128-CBC, AES-256-CBC (family `AES`) | Encrypting OPC UA messages after the handshake, in mode `SignAndEncrypt` only. 128 under `Aes128_Sha256_RsaOaep`, 256 under the other two | `gateway/opcua.py` |
| P_SHA256 key derivation (family `HMAC`) | Deriving each secure channel's signing key, encryption key and IV from the exchanged nonces | `gateway/opcua.py` |
| OPC UA gateway certificate, pinned server certificate, trusted certificates bundle (certificates) | The X.509 certificate the gateway presents, the optional server certificate that pins the server, and the optional bundle the server's certificate must chain to. All are files attached to Machine Data Settings; subject, issuer and validity belong to the plant that issued them, and the [site CBOM](#the-site-cbom-with-the-deployed-certificates) fills them in | `gateway/opcua.py`, `gateway/opcua_trust.py`, `cbom.py` |
| OPC UA gateway private key (private key), its passphrase (password) | The RSA key of the gateway certificate, accepted only as a private Frappe File, and its passphrase in a Password field | `gateway/opcua.py` |
| Webhook secret (secret key) | The shared HMAC key, in a Password field of Machine Data Settings | |
| ERP and broker credentials | S/4HANA Basic or OAuth 2.0 client credentials, MQTT and OPC UA passwords, in Password fields | |
| S/4HANA OAuth bearer token (token) | The access token from the OAuth 2.0 token endpoint, held in memory only | `s4hana/odata.py` |

HMAC-SHA256 has two roles: the webhook signature, from the standard library, and the symmetric signature of every OPC UA message, from `asyncua` on the `cryptography` package. The OPC UA algorithms are not chosen by FoaMES: the OPC UA specification (Part 7, security policy profiles) fixes them per policy, and `asyncua` implements them on the host's OpenSSL. FoaMES chooses the policy, the mode, and the certificate and key.

**Post-quantum.** FoaMES's own code uses no asymmetric algorithms or elliptic curves, so the webhook, the idempotency markers and the ERP paths have no migration work beyond what TLS on the host provides. The one asymmetric algorithm in the CBOM is RSA, 2048 to 4096 bits, in the OPC UA handshake, and only when a secure mode is on. A quantum-safe policy can only arrive through the OPC UA specification and the servers; until then the RSA handshake is the item to track, and the AES-256 and HMAC-SHA256 session keys it protects are at sizes considered quantum-safe. Auditors who flag SHA-1 should note that under `Basic256Sha256` and `Aes128_Sha256_RsaOaep` it is only the OAEP padding hash, where collision resistance is not needed; `Aes256_Sha256_RsaPss` removes it.

**What the CBOM still makes visible.** Message security is off until someone turns it on: with the default mode `None`, the OPC UA session is neither signed nor encrypted, and the user name and password travel in the clear unless the server encrypts the user token. The gateway logs a warning at each start in that mode. Run a mode `None` gateway only on a protected OT network segment, and switch to `SignAndEncrypt` with `Basic256Sha256` or `Aes256_Sha256_RsaPss` wherever the server offers it; [machine-data.md](machine-data.md#opc-ua-security) walks through the certificate. Without a pinned Server Certificate or a Trusted Certificates bundle the gateway accepts the certificate the server presents; attach the plant CA as Trusted Certificates so that an unknown, expired or misnamed server certificate is refused, as [machine-data.md](machine-data.md#validating-the-server) describes.

### The site CBOM with the deployed certificates

The published CBOM cannot say which certificates a plant has installed. A site can build that itself:

```bash
bench --site <site> execute foames.foames_mes.site_cbom.write --kwargs "{'out': 'site-cbom.cdx.json'}"
```

or fetch the same document as JSON from `/api/method/foames.foames_mes.site_cbom.get_site_cbom` as a System Manager. It is a CycloneDX 1.7 document whose components are the curated cryptographic assets above, with the OPC UA certificate assets filled in from the files attached to Machine Data Settings: `subjectName`, `issuerName`, `notValidBefore`, `notValidAfter` and the signature algorithm reference in `certificateProperties`, and as `foames:certificate:` properties the status (`active`, `expired`, `not-yet-valid`, or `not-configured`, `missing` and `not-pinned` when no file is attached), the days to expiry, the SHA-256 fingerprint, the key algorithm and size, the serial number and the application URIs. Each certificate of the trusted bundle appears as its own asset, the private key carries its size, and the secure channel lists only the configured policy's cipher suite (none in mode `None`). The site, the endpoint, the security mode and the policy are properties of the document's subject. Load it into the plant's SBOM tooling alongside the published SBOM and alert on `daysToExpiry`. The builder uses the standard 1.7 fields plus properties, so every 1.7 consumer reads it without extensions.

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
| Certificate expiry as a suggestion | Raise an Agent Suggestion from the scheduler when a deployed OPC UA certificate in the site CBOM is within its last weeks, so the renewal lands on the floor's list rather than in a log | CBOM `certificate` validity dates |
