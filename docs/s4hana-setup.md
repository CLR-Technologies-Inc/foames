# Connecting FoaMES to S/4HANA: users, communication arrangements and OAuth

This guide walks through the S/4HANA side of the adapter setup: which user FoaMES logs in as,
which services have to be exposed for it, and how to check the services before switching the
adapter on. The FoaMES side (S4HANA Settings) and the day-to-day operation are described in
[s4hana-adapter.md](s4hana-adapter.md); the postings themselves in
[s4hana-postings.md](s4hana-postings.md).

Menu paths and app names differ between S/4HANA Cloud, private cloud and on-premise releases.
Where they differ, both are given. Nothing here needs SAP add-ons, RFC or the SAP Cloud SDK.

## 1. Choose how FoaMES authenticates

| Method | Use when | What you need in S4HANA Settings |
| --- | --- | --- |
| Basic (communication user) | On-premise and private cloud; the simplest setup | User name, password |
| OAuth 2.0 client credentials | S/4HANA Cloud, or an on-premise system behind an OAuth-capable gateway or API management layer | Token URL, client ID, client secret, optional scope |

With Basic, FoaMES sends the user name and password with every request. With OAuth, FoaMES posts
the client ID and secret to the token URL (HTTP Basic on the token request, `grant_type`
`client_credentials`), caches the access token until shortly before it expires, and sends it as a
bearer token. A 401 on the token request or on an API call is treated as temporary, so a rotated
secret only delays postings until S4HANA Settings is updated; nothing is failed.

Either way the user is a technical user: no dialog logon, no password expiry policy that would
lock it out, and only the authorizations of the services below.

## 2. Create the user

### S/4HANA Cloud (public edition)

1. Open **Maintain Communication Users** and create a user, for example `FOAMES`. Choose a
   password, or leave it for the certificate or OAuth setup in the arrangement.
2. Open **Maintain Communication Systems** and create a system for the FoaMES site: host name of
   the FoaMES server, the communication user from step 1 as the user **for inbound communication**.
   For IDocs, also add a user for outbound communication (the FoaMES API user, see step 5).
3. The communication arrangements in step 3 tie the user, the system and the scenarios together.
   The arrangement shows the OAuth 2.0 details (token endpoint, client ID) when the inbound
   authentication is set to OAuth; copy them into S4HANA Settings.

### On-premise and private cloud

1. In **SU01**, create a user of type **Communications Data** (or **System**), for example
   `FOAMES`. A communications user cannot log on to the GUI and does not get password-change
   prompts.
2. Give it a role (PFCG) that contains the OData services from step 3: on the role's Menu tab,
   add each service through **Authorization Default** > **TADIR Service** > `IWSG` (the service
   group) and `IWSV` (the service), and generate the profile. The role also needs the business
   authorizations behind the services: display of orders, routings and BOMs; posting of
   confirmations (`C_AFRU_AWK`, `C_AFRU_ORD`) and goods movements (`M_MSEG_BWA`, `M_MSEG_WMB`,
   `M_MSEG_BMB` for the movement types and plants used). The quickest way to find the exact
   objects is to post one confirmation and one goods movement with the user in a test client and
   read the authorization trace (`STAUTHTRACE`).
3. For OAuth on-premise, create an OAuth 2.0 client in **SOAUTH2** for the user, assign the
   scopes of the OData services, and enable the **client credentials** grant. The token endpoint is
   `https://<host>/sap/bc/sec/oauth2/token`. Not every release offers client credentials for OData
   V2 services; where it does not, use Basic over TLS.

## 3. Expose the services

The adapter uses these released OData V2 services. Each needs to be reachable by the user above.

| Service | FoaMES uses it for | Communication scenario (Cloud) |
| --- | --- | --- |
| `API_PRODUCT_SRV` | Item references | `SAP_COM_0009` Product Integration |
| `API_BATCH_SRV` | Batch references | `SAP_COM_0073` Batch Integration |
| `API_PRODUCTION_ORDER_2_SRV` | Work Order references, order reads (operations, components, status) | `SAP_COM_0104` Production Planning Integration |
| `API_PROCESS_ORDER_2_SRV` | Process order reads | `SAP_COM_0104` |
| `API_PROD_ORDER_CONFIRMATION_2_SRV` | Production order confirmations and their cancellation | `SAP_COM_0104` |
| `API_PROC_ORDER_CONFIRMATION_2_SRV` | Process order confirmations and their cancellation | `SAP_COM_0104` |
| `API_MATERIAL_DOCUMENT_SRV` | Goods movements, their reversal, Stock Movement references, movements per order | `SAP_COM_0106` Material Document Integration |
| `API_PRODUCTION_ROUTING` | Routing reads and Routing references | `SAP_COM_0105` Bill of Operations Integration |
| `API_BILL_OF_MATERIAL_SRV;v=0002` | BOM reads and Bill of Materials references | `SAP_COM_0105` |
| `API_WORK_CENTERS` | Work center reads and Workstation references | `SAP_COM_0105` |

The scenario IDs are those SAP publishes for the public cloud; search the **Communication
Arrangements** app by the API name if an ID has moved on your release. Only expose the services
you use: a site that never posts goods movements from FoaMES does not need
`API_MATERIAL_DOCUMENT_SRV` write access.

### S/4HANA Cloud

Open **Communication Arrangements**, create one arrangement per scenario above, pick the
communication system from step 2, and activate. The arrangement lists the service URLs; the host
part of those URLs is the **Base URL** for S4HANA Settings (without `/sap/opu/odata/sap/...`).

### On-premise and private cloud

1. In **/IWFND/MAINT_SERVICE**, add each service (Add Service, system alias `LOCAL`, filter by
   technical service name) and activate it. Services that are already active show a green ICF node.
2. In **SICF**, check that the node `/sap/opu/odata/sap/<SERVICE>` is active.
3. In **/IWFND/ERROR_LOG** you will later find the reason for any 4xx or 5xx the adapter reports.

## 4. Check each service before switching the adapter on

From any machine that can reach S/4HANA, with the user from step 2:

```sh
# Does the service answer, and does it give a CSRF token? (Basic authentication)
curl -sS -u FOAMES:'<password>' -H 'X-CSRF-Token: Fetch' -D - -o /dev/null \
  'https://<host>:<port>/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/?sap-client=100'

# What are the entity sets and fields on this release?
curl -sS -u FOAMES:'<password>' \
  'https://<host>:<port>/sap/opu/odata/sap/API_PROD_ORDER_CONFIRMATION_2_SRV/$metadata?sap-client=100'

# OAuth: can the client get a token?
curl -sS -u '<client id>:<client secret>' -d 'grant_type=client_credentials' \
  'https://<token host>/sap/bc/sec/oauth2/token'
```

A `403` with `x-csrf-token: Required` on a GET means the service is active but the user lacks the
service authorization (step 2). A `404` means the service is not activated (step 3). A `401` means
the credentials are wrong.

Compare the `$metadata` of each service with the names the adapter uses:

- entity sets and key fields: `foames/foames_adapters/s4hana/entities.py` (override any of them in
  **S4HANA Settings > Entity Mappings**); the routing key includes the internal version, and the
  material BOM key has seven fields including the material and plant;
- confirmation fields: `foames/foames_adapters/s4hana/confirmations.py`;
- material document fields: `foames/foames_adapters/s4hana/goods_movements.py`;
- function imports: `foames/foames_adapters/s4hana/actions.py`;
- reads: `foames/foames_adapters/s4hana/orders.py`.

The names follow SAP's released APIs, but older releases lack some fields and SAP renames
navigation properties between versions. A field S/4HANA does not know is answered with HTTP 400 and
a message naming the property; the outbox records it on the posting as a failure with the message,
so a wrong name is caught on the first posting, not silently.

## 5. IDocs from S/4HANA to FoaMES (optional)

Only needed when S/4HANA should push orders, materials or batches to FoaMES instead of FoaMES
reading them on demand.

1. In FoaMES, create a user with the **FoaMES Integration** role and generate an API key and
   secret for it (User > Settings > API Access).
2. In S/4HANA, **SM59**: an RFC destination of type **G** (HTTP to external server) with the
   FoaMES host, path prefix `/api/method/foames.foames_adapters.s4hana.api.receive_idoc`, SSL
   active, and Basic authentication with the API key as user and the secret as password.
3. **WE21**: an XML HTTP port on that destination. **WE20**: a partner profile for the FoaMES
   logical system with the outbound message types (`LOIPRO`, `MATMAS`, `BATMAS` or others) on that
   port, with the IDoc type of your release.
4. Send a test IDoc (`WE19`, or a change pointer run for `MATMAS`). It appears as an **S4HANA
   Inbound IDoc** with status Processed.

## 6. Certificates

If S/4HANA uses a certificate from a private CA, put the CA chain in PEM form on the FoaMES server
and set **CA Bundle Path** in S4HANA Settings. For IDocs the other way round, the FoaMES server's
certificate chain goes into S/4HANA's **STRUST** (SSL client, anonymous or standard).

## 7. Licensing

SAP's Digital Access licensing counts documents that third-party systems create in S/4HANA.
Material documents are on SAP's list; confirmations are not, unless they create goods movements.
Check the customer's SAP contract before enabling goods movements from FoaMES. The adapter does
not change what gets counted; it only makes the postings visible in the outbox.
