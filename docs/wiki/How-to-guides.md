How-to guides are recipes for people who already run FoaMES and need to get one job done. They assume you know the basics from the [Tutorials](Tutorials). Each guide says what you need first, gives the steps, and tells you how to check the result.

## Getting data in

| Guide | Use it to |
| --- | --- |
| [Send machine data](How-to-Send-machine-data) | Connect a PLC, gateway or IoT bridge through the signed webhook, MQTT, OPC UA or Sparkplug B |
| [Run the gateways in production](How-to-Run-the-gateways-in-production) | Keep the MQTT, Sparkplug B and OPC UA gateways running under supervisor or systemd |
| [Connect Ignition](How-to-Connect-Ignition) | Bring an Ignition SCADA gateway's tags into FoaMES |
| [Read a process historian](How-to-Read-a-process-historian) | Read tag history from AVEVA PI, InfluxDB, Ignition Tag Historian or a SQL historian, read-only |

## Connecting business systems

| Guide | Use it to |
| --- | --- |
| [Connect ERPNext](How-to-Connect-ERPNext) | Use ERPNext on the same site: references, Job Card roll-ups, Workstation status, downtime, inspections, asset repairs |
| [Connect SAP S/4HANA](How-to-Connect-SAP-S4HANA) | Resolve references over OData, post confirmations and goods movements, receive IDocs |
| [Connect an MES or Tulip](How-to-Connect-an-MES-or-Tulip) | Reach Tulip, Plex, SAP Digital Manufacturing, AVEVA MES and other platforms through the shared REST framework |
| [Write an adapter](How-to-Write-an-adapter) | Add an adapter for an ERP or system that FoaMES does not support yet |

## Running the floor

| Guide | Use it to |
| --- | --- |
| [Set up shift patterns](How-to-Set-up-shift-patterns) | Compute OEE per shift and compare shifts |
| [Monitor a measurement with SPC](How-to-Monitor-a-measurement-with-SPC) | Chart a temperature, pressure or dimension and get suggestions when a run rule signals |
| [Plan preventive maintenance](How-to-Plan-preventive-maintenance) | Schedule service by calendar, run hours or counts and work the due list |
| [Run andon calls](How-to-Run-andon-calls) | Let operators call for help and measure how fast help arrives |
| [Control SOPs](How-to-Control-SOPs) | Keep standard operating procedures under revision control with sign-off and training |
| [Mine your process](How-to-Mine-your-process) | Build an event log and find the real paths, bottlenecks and deviations |

## Taking part

| Guide | Use it to |
| --- | --- |
| [Contribute](How-to-Contribute) | Set up for development, sign the CLA and open a pull request |

Looking for read-only mode or the risk register? They are still in review; see [Upcoming features](Upcoming-features).
