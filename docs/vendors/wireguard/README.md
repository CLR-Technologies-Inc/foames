# Native WireGuard connectivity and topology

Native [WireGuard](https://www.wireguard.com/) is an optional transport for FoaMES's existing
IP connections. Run it on a gateway, bridge host or server using the operating system's packages.
FoaMES's `wireguard` topology collector observes those interfaces and peers so that their
connectivity evidence appears in the same graph as the plant's other assets.

The integration is alpha: automated tests exercise command output, snapshots and report mapping.
Validate the actual tunnel and application connection at the site before relying on it.

## Where it fits

| Existing path | Native WireGuard use |
| --- | --- |
| [Ignition](../ignition/README.md) publishing Sparkplug B or a gateway-script webhook | Carry MQTT or HTTPS between the gateway and a private broker or FoaMES site. Ignition keeps the device drivers and tag mapping. |
| Generic [MQTT and signed machine-event webhooks](../../machine-data.md) | Give a remote collector private IP reachability to the configured endpoint. |
| [BACnet/IP and Modbus TCP bridge](../../../bridges/bms/README.md) | Carry configured unicast device reads or, preferably, keep polling local and carry the signed building-point posts. |
| [Historian bridge](../historian/README.md) | Reach a private database or API, or run the bridge near the historian and carry its event posts. |
| [Bluesky and Tiled bridge](../bluesky/README.md) | Reach a Tiled catalog or carry scalar measurement posts from the lab. |

WireGuard transports IP packets. Serial, USB, GPIB and other non-IP instruments still need a local
collector or protocol gateway. BACnet discovery and other broadcast-dependent protocols need
their own routed-network configuration; a tunnel does not automatically extend an Ethernet LAN.
Keep control loops and time-sensitive acquisition local. Application buffering, retries and
replay belong to the collector or broker.

The existing `network` collector continues to observe Tailscale. Native WireGuard is useful where
the plant manages its own peers and routes. Tailscale provides additional coordination and
connection mechanisms; selecting the native collector does not configure or replace either VPN.
If both are present, plan their routes explicitly and give their collectors different providers.

## Deploy the transport

1. Install a supported [WireGuard package](https://www.wireguard.com/install/). On Linux, prefer
   the kernel implementation and `wireguard-tools`; on Windows, use the official WireGuard
   client, which includes WireGuardNT. Make the `wg` executable available to the collector.
2. Have the network administrator configure the peers and OS-managed tunnel service. Keep private
   and preshared keys in the host's protected WireGuard configuration or the site's secret
   management system. FoaMES has no VPN key field and does not ingest these keys.
3. Route only the required addresses or subnets. Equipment without a WireGuard client needs a
   gateway and a working return route or suitable NAT. Resolve overlapping plant subnets before
   connecting them. Allow the necessary UDP tunnel traffic and application traffic through the
   appropriate firewalls; `AllowedIPs` does not replace service-level firewall rules.
4. Keep MQTT authentication and authorization, HTTPS certificate verification and webhook HMAC
   signing enabled. The VPN secures transport between its endpoints; FoaMES's existing permissions
   and write gate still govern application actions.
5. Confirm the application's connection using its own read or ingest checks. A successful
   handshake alone does not prove that the broker, historian, device or FoaMES API is available.

For NAT mappings that must remain open during idle periods, the network administrator may use
WireGuard's persistent keepalive setting. Raw WireGuard still requires a viable UDP path; the
collector supplies no NAT negotiation, relay service or DNS configuration.

## Observe native interfaces

Install the standalone topology package on the host where `wg` can inspect the interfaces:

```sh
pip install ./bridges/topology
foames-topology-collect wireguard --provider wg-gateway-1 --host-name gateway-1 --dry-run
```

`--host-name` identifies the gateway, including when a saved snapshot is read elsewhere. Keep it
stable. Interface and peer identifiers are scoped to the provider, gateway and interface, with peer
identity derived from its public key. Changing a peer's endpoint does not change its identity;
rotating its public key does. A peer represents the local gateway's view, not a discovered host
name or a complete network inventory. An optional `--site-name` creates a site within that
provider's observation scope; it does not take ownership of another collector's site asset.

The live collector reads only selected, non-secret `wg show` fields. It never uses `dump` or
`showconf`, reads a configuration file, or requests private or preshared keys. It also never runs
`wg set`, starts a tunnel, changes routes, sends probes or writes to a peer.

Give the collector only the OS permissions needed for those reads. Some platforms require
administrative access to inspect interfaces. Where the same OS permission also permits changes,
use a dedicated service or an administrator-controlled export of the non-secret snapshot instead
of granting an application account unrestricted tunnel administration. Keep API credentials in
the service's protected environment, supplied as `FOAMES_API_KEY` and `FOAMES_API_SECRET`.

After inspecting the dry-run report, a scheduled service can post it with an API user holding the
**FoaMES Integration** role:

```sh
foames-topology-collect wireguard --provider wg-gateway-1 --host-name gateway-1 --tenant "Plant A" --site-name "Plant A" --url https://foames.example.com
```

Use a distinct provider per gateway and collector. Current reports retire missing observations
owned by that provider; stale or future snapshots cannot retire missing observations. A failed or
malformed read must be resolved before a complete report can be sent; do not substitute an empty
snapshot for a failed command.

## Reading the report

Each local interface is a **Network Device**, each peer is a **Host**, and their relationship is
a **Network** link. The report includes the observed endpoint, allowed IPs, received and transmitted
byte counters, persistent keepalive setting and last handshake. Allowed IPs express WireGuard's
peer routing configuration; they are not evidence that every address is reachable.

| Handshake evidence | Peer status |
| --- | --- |
| Handshake within `--handshake-max-age` seconds (default 180), with a current observation | OK |
| No handshake, an older handshake, future timestamp or stale observation | Unknown |

An idle WireGuard peer can remain silent for a long time. Unknown is therefore not an assertion
that a peer is down. Conversely, OK means recent tunnel evidence, not successful device reads.
Compare it with the application connection and the age of its data. Byte counters are cumulative
WireGuard transport counters, not production counters or measurements for OEE.

For offline checks, `--status-file` accepts the collector's non-secret JSON snapshot shape:
an `observed_at` UTC timestamp and an `interfaces` list. The checked-in
[example](../../../bridges/topology/examples/wireguard-status.json) shows the fields.
Use `--snapshot` to export this shape from the live collector. It prints the sanitized observation
instead of a topology report and cannot be combined with `--url`.

```sh
foames-topology-collect wireguard --provider wg-gateway-1 --host-name gateway-1 --snapshot > wireguard-status.json
foames-topology-collect wireguard --provider wg-example --host-name example-gateway --status-file bridges/topology/examples/wireguard-status.json --dry-run
```

Old snapshots retain their original observation time. Replaying one does not make its peers
currently healthy. Endpoint addresses and public keys may still identify the plant's network;
keep operational snapshots local rather than attaching them to public issues.

## Verification at a site

Check a dry-run report against the administrator's interface and peer inventory. Then exercise a
representative read or test ingest through the configured application path, checking its timestamp
and quality. In a test environment, observe a reconnect and confirm that the application resumes
without duplicated events or invented production. Test allowed routes and firewall restrictions
using the site's approved network checks. The collector's status is supporting evidence for
these checks, not their substitute.

The implementation's automated checks run with:

```sh
cd bridges/topology
python -m unittest discover -s tests -v
```

## Sources and licensing

- [WireGuard installation](https://www.wireguard.com/install/),
  [conceptual overview](https://www.wireguard.com/) and
  [quick start](https://www.wireguard.com/quickstart/).
- [`wg` command manual](https://git.zx2c4.com/wireguard-tools/about/src/man/wg.8).
- [Official Windows client](https://git.zx2c4.com/wireguard-windows/about/).

FoaMES invokes the separately installed `wg` command. It contains no WireGuard implementation,
driver or copied WireGuard source. `wireguard-tools` is GPL-2.0-only and appears as an optional
external component in the curated SBOM; the FoaMES collector remains Apache-2.0.
