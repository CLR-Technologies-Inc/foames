# Machine data: how events reach FoaMES

FoaMES takes machine events four ways. All four end in the same place: a Machine Event record that is processed into machine state, downtime and counter deltas.

| Path | How | Needs |
| --- | --- | --- |
| Signed webhook | `POST /api/method/foames.foames_mes.api.ingest_machine_events` with `{"events": [...]}`; headers `X-FoaMES-Timestamp` (Unix seconds) and `X-FoaMES-Signature` (hex HMAC-SHA256 of `<timestamp>.<body>` with the secret in Machine Data Settings) | Nothing installed; any PLC gateway or IoT bridge that can POST JSON |
| MQTT | `bench --site <site> execute foames.foames_mes.gateway.mqtt.run`; subscribes to `<prefix>/<machine source id>/<event type>` | `pip install paho-mqtt`, a broker |
| OPC UA | `bench --site <site> execute foames.foames_mes.gateway.opcua.run`; polls the nodes mapped in Machine Data Settings, with optional Sign or SignAndEncrypt message security (see [OPC UA security](#opc-ua-security)) | `pip install asyncua` |
| Sparkplug B | `bench --site <site> execute foames.foames_mes.gateway.sparkplug.run`; subscribes to `spBv1.0/<group>/#` on the same broker and decodes the protobuf payloads itself | `pip install paho-mqtt`, a broker; this is how Ignition publishes, see [ignition.md](ignition.md) |

A logged-in user with the FoaMES Operator role may also post events unsigned, which is how a manual entry or a test harness works.

## OPC UA security

The OPC UA gateway takes its message security from the **OPC UA Security** section of Machine Data Settings.

| Field | What it does |
| --- | --- |
| Message Security Mode | `None`, `Sign` or `SignAndEncrypt`. Use `SignAndEncrypt`. `Sign` stops tampering but leaves the values readable. `None` keeps the old behaviour: nothing is signed or encrypted, and the gateway logs a warning to `foames.opcua` each time it starts. |
| Security Policy | `Basic256Sha256` (the default, which every current server offers), `Aes128_Sha256_RsaOaep` or `Aes256_Sha256_RsaPss`. Pick one that the server's endpoint lists. The deprecated `Basic128Rsa15` and `Basic256` policies are not offered. |
| Client Certificate | The X.509 certificate, DER or PEM, that the gateway presents. |
| Client Private Key | The certificate's private key, PEM or DER. It must be uploaded as a **private** file. Saving the settings with a public key file is refused. |
| Private Key Passphrase | Only if the key is encrypted. It is stored as a Frappe password field. |
| Client Application URI | Must equal the `URI:` entry in the certificate's subjectAltName. Most servers reject a session whose application URI does not match its certificate. |
| Server Certificate | Optional. The server's own certificate. When it is set, the gateway uses this one instead of the one the server sends, so a different server at the same address cannot stand in for it. |
| Trusted Certificates | Optional. A PEM bundle, or one DER file, of the certificates the server's certificate must be or chain to: the plant CA, or the server certificates themselves. See [Validating the server](#validating-the-server). |

Username and Password in the OPC UA section still give username authentication, and they work in every mode. With mode `None`, the password is protected only if the server's user token policy encrypts it, so use a secure mode wherever the server allows one.

Saving Machine Data Settings with `Sign` or `SignAndEncrypt` but no certificate or key is refused, so a misconfiguration shows up on the form, not when the gateway starts.

The algorithms behind each policy (RSA-OAEP and RSA signatures in the handshake, AES-CBC and HMAC-SHA256 on the messages) are listed per policy in the cryptography bill of materials, see [sbom.md](sbom.md#the-cryptography-bill-of-materials).

The certificates a site has attached, with their subject, issuer, validity and key, are read into a site-level CBOM by `bench --site <site> execute foames.foames_mes.site_cbom.write`; see [sbom.md](sbom.md#the-site-cbom-with-the-deployed-certificates).

### Making a client certificate

An OPC UA application certificate needs the application URI in its subjectAltName, plus the digital signature, key encipherment, data encipherment and non-repudiation key usages, and both client and server extended key usage. With OpenSSL 3:

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 730 -nodes \
  -keyout foames-opcua.key.pem -out foames-opcua.cert.pem \
  -subj "/CN=FoaMES OPC UA gateway/O=Example Plant" \
  -addext "subjectAltName=URI:urn:example.com:foames:opcua-gateway,DNS:$(hostname)" \
  -addext "keyUsage=critical,digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment" \
  -addext "extendedKeyUsage=clientAuth,serverAuth"
openssl x509 -in foames-opcua.cert.pem -outform der -out foames-opcua.cert.der
```

Attach `foames-opcua.cert.der` as the Client Certificate, attach `foames-opcua.key.pem` as a private file for the Client Private Key, and set Client Application URI to `urn:example.com:foames:opcua-gateway`. Use RSA 2048 for `Basic256Sha256` and `Aes128_Sha256_RsaOaep`. For `Aes256_Sha256_RsaPss` the server may require RSA 3072 or larger.

### Validating the server

Without Trusted Certificates, the gateway takes the server's certificate as the server presents it (or as pinned by Server Certificate) and logs that it does so. With a bundle attached, the gateway hands asyncua a certificate validator, and the connection is refused unless the server's certificate

- is one of the certificates in the bundle, or chains to one through certificates in the bundle (a plant CA that signed the server certificate; an intermediate CA has to be in the bundle too),
- is within its validity period, as is every certificate on that chain,
- and carries the server's application URI, the one its endpoint announces, in its subjectAltName.

A refused server shows up in the gateway's log with the reason: unknown certificate, expired on a date, or an application URI mismatch. Saving Machine Data Settings with a bundle that holds no certificate, or a file that is not PEM or DER, is refused. This needs asyncua 1.1 or later; with an older release the gateway stops at start with a message rather than running unvalidated. Revocation lists are not checked.

To build the bundle, export the CA certificate from the server's certificate manager, or the server's own certificate for a self-signed one, and concatenate PEM files when there are several:

```bash
cat plant-ca.pem line1-opcua.pem > trusted.pem
```

### Trusting the certificate on the server

Most OPC UA servers put an unknown client certificate in a rejected or quarantine list on the first connection attempt. Start the gateway once, move the FoaMES certificate to the trusted list on the server, and start it again. On Ignition, that is Config, OPC UA, Security, Server tab: select the certificate under **Quarantined Certificates** and choose Trust. For a CA-signed certificate, trust the issuing CA instead.

The gateway reads the files when it starts, so restart it after replacing a certificate or key.

## Event shape

```json
{"machine": "press-1", "type": "Count", "counter": "good", "value": 1234, "timestamp": "2026-10-30T02:00:00Z", "id": "press-1-000981"}
```

| `type` | Fields | Effect |
| --- | --- | --- |
| `State` | `state`: Running, Idle, Down, Setup, Unknown (aliases such as run, fault, changeover are accepted) | Sets the machine state. Down opens a Downtime Record; the next other state closes it |
| `Count` | `counter` (good, scrap, or any name), `value` = the machine's running total | The delta from the previous reading of that counter is stored on the event and feeds OEE. A first reading, a reset, or a reading that arrives after a later one counts zero: FoaMES never invents production. Set the machine's Counter Rollover to handle wrap-around |
| `Measurement` | `name`, `value` | Stored for SPC and OEE work |
| `Alarm` | `code` or `value`, `text` | Stored and marks the machine Down |
| `Message` | `text` | Stored; refreshes the machine's last-seen time |

A meter is sent as a counter too: `{"type": "Count", "counter": "energy_kwh", "value": 48213.6}` with the meter's running total. Counters named `energy`, `kwh`, `power`, `electricity`, `water`, `gas`, `feed`, `steam`, `air` or `fuel`, exactly or with a unit suffix, are treated as consumed inputs rather than production: their deltas feed the specific-consumption figure (`foames.foames_mes.kpi.resource_intensity`) and the consumption-with-no-output rule on the Floor View, and never count towards OEE. A continuous unit without a cycle reports its production the same way, as a flow or mass totaliser named `good`.

`id` is optional and deduplicates retries. `timestamp` is ISO 8601 or Unix seconds; missing means now.

## Extending the processing

After an event is processed, every dotted path registered under the `foames_machine_event_handlers` hook is called with the Machine Event document and its Machine. Another app uses this to attach counts and done messages to its own execution records:

```python
# hooks.py of the other app
foames_machine_event_handlers = ["myapp.floor.on_machine_event"]
```

A Machine also carries a **Current Job Reference**, an External Reference of type Job Card for whatever ERP is connected, and **Current Job Since**. Set it on the form or with `foames.foames_mes.api.set_current_job(machine, reference, at=None)` (pass no reference to end the job). Whenever it changes, every dotted path under the `foames_machine_job_changed` hook is called with the Machine, the previous reference and the time of the change. The ERPNext adapter uses this to roll the counts of the job that ended up to its Job Card; see [erpnext-adapter.md](erpnext-adapter.md#rolling-machine-counts-up-to-job-cards).

Every state change (from an event, a manual entry or the stale-machine task) also calls each dotted path under the `foames_machine_state_changed` hook with the Machine, the previous state, the new state and the time of the change. The ERPNext adapter uses this to show the state on the machine's ERPNext Workstation; see [erpnext-adapter.md](erpnext-adapter.md#workstation-status-and-downtime).

A machine that stops reporting is marked Unknown after the configured minutes by a scheduled task, so a silent line never looks like a running one.
