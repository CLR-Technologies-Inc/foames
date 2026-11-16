Every integration below ships on `main` and is **alpha**: built against the vendor's published interfaces and tested against stand-ins (ERPNext against a real ERPNext test site). Treat each as unproven until you have run it against your own system. None is required, and nothing in the core depends on any of them.

## ERP and industrial data platforms

| System | Adapter key | Connection | Guide |
| --- | --- | --- | --- |
| ERPNext | `ERPNext` | Same site, direct reads, ERPNext Outbox | [Connect ERPNext](How-to-Connect-ERPNext) |
| SAP S/4HANA | `S4HANA` | OData V2, IDoc XML over HTTP, S4HANA Outbox | [Connect SAP S/4HANA](How-to-Connect-SAP-S4HANA) |
| Siemens Insights Hub (Opcenter Intelligence) | `INSIGHTS_HUB` | REST, time series, Insights Hub Outbox | [docs/vendors/insights_hub](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/insights_hub/README.md) |

## MES, MOM and frontline platforms (shared REST framework)

| System | Adapter key | Guide |
| --- | --- | --- |
| Tulip | `TULIP` | [docs/vendors/tulip](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/tulip/README.md) |
| Rockwell Plex Smart Manufacturing Platform | `PLEX` | [docs/vendors/plex](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/plex/README.md) |
| Rockwell FactoryTalk ProductionCentre and PharmaSuite | `FTPC` | [docs/vendors/factorytalk_productioncentre](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/factorytalk_productioncentre/README.md) |
| SAP Digital Manufacturing | `SAP_DMC` | [docs/vendors/sap_dmc](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/sap_dmc/README.md) |
| Dassault Systèmes DELMIA Apriso | `APRISO` | [docs/vendors/delmia_apriso](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/delmia_apriso/README.md) |
| AVEVA Manufacturing Execution System | `AVEVA_MES` | [docs/vendors/aveva_mes](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/aveva_mes/README.md) |
| Critical Manufacturing MES | `CMF_MES` | [docs/vendors/critical_manufacturing](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/critical_manufacturing/README.md) |
| Aegis FactoryLogix | `FACTORYLOGIX` | [docs/vendors/aegis_factorylogix](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/aegis_factorylogix/README.md) |
| Körber Werum PAS-X MES | `PASX` | [docs/vendors/koerber_pasx](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/koerber_pasx/README.md) |
| Proficy Smart Factory MES (Velotic) | `PROFICY` | [docs/vendors/proficy](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/proficy/README.md) |

How the framework works: [Connect an MES or Tulip](How-to-Connect-an-MES-or-Tulip).

## SCADA, historians and lab data

| System | Path | Guide |
| --- | --- | --- |
| Ignition (Inductive Automation) | Sparkplug B, OPC UA or a gateway script | [Connect Ignition](How-to-Connect-Ignition) |
| AVEVA PI, InfluxDB, Ignition Tag Historian, TimescaleDB and SQL historians | Read-only bridge outside the app | [Read a process historian](How-to-Read-a-process-historian) |
| Bluesky and Tiled (NSLS-II) | Bridge outside the app, Measurement events | [docs/vendors/bluesky](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/bluesky/README.md) |
| Building automation (BMS / BAS) controllers and meters | BACnet/IP or Modbus TCP, read-only gateway outside the app, building point readings | [Monitor building systems](How-to-Monitor-building-systems) |
| Any PLC, gateway or IoT bridge | Webhook, MQTT, Sparkplug B or OPC UA | [Send machine data](How-to-Send-machine-data) |

## Kernel reference types

An adapter declares which of these it supports: Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Job Card, Bill of Materials, Routing, Workstation and Asset.

## Planned

Odoo, Microsoft Dynamics 365, Epicor Kinetic, Infor, Oracle NetSuite and Fusion; Kepware and ThingWorx, HighByte, Litmus Edge, FactoryTalk Optix; IBM Maximo, SAP Plant Maintenance, Fiix and UpKeep. None is built yet. To propose another, open an issue.
