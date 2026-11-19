# Discovery skills: finding out how a plant's systems are set up

Many of the systems FoaMES connects to are configured per site: their API paths, versions, objects and tables, authentication and tag namespaces are chosen when the plant installs them, so FoaMES cannot ship them. These skills walk an agent, with a person from the plant (the **operator**), through discovering one installation **before** a FoaMES connector is configured for it, and they do it safely: read-only, through documented vendor interfaces only, on hosts the operator allowlists, with credentials the agent never sees, and with a dry-run plan the operator approves first.

They are adoption files for agents that set FoaMES up at a plant. Each skill is a folder with a `SKILL.md` (front matter with `name` and `description`, then instructions), the layout agent tools load skills from; an agent without skill support can read the Markdown directly.

## Start here

1. [baseline/SKILL.md](baseline/SKILL.md): the rules every discovery follows (read-only through FoaMES's write gate, least-privilege short-lived credentials from a secret store, allowlisted documented APIs, no scanning, rate limits and timeouts, an approved dry-run plan, stop on any authentication error, redaction, a local git-ignored report, vendor data treated as data), the procedure, the plan and report templates, and how the rules line up with IEC 62443 and NIST SP 800-82.
2. The vendor's skill below, which adds what that system's installations decide and the documented reads that settle it.
3. Reports go to `.foames-discovery/<connector>/`, which this repository's `.gitignore` excludes, or to a folder outside every repository. They are site configuration: they stay with the plant and are never committed, attached to an issue or pasted into a chat.

## Skills

| System | Kind | Skill | Name |
| --- | --- | --- | --- |
| Aegis FactoryLogix | MES / MOM | [aegis_factorylogix/SKILL.md](aegis_factorylogix/SKILL.md) | `foames-discover-aegis-factorylogix` |
| AVEVA Manufacturing Execution System | MES / MOM | [aveva_mes/SKILL.md](aveva_mes/SKILL.md) | `foames-discover-aveva-mes` |
| Bluesky and Tiled | Lab and beamline data acquisition | [bluesky/SKILL.md](bluesky/SKILL.md) | `foames-discover-bluesky` |
| Critical Manufacturing MES | MES / MOM | [critical_manufacturing/SKILL.md](critical_manufacturing/SKILL.md) | `foames-discover-critical-manufacturing` |
| Dassault Systèmes DELMIA Apriso | MES / MOM | [delmia_apriso/SKILL.md](delmia_apriso/SKILL.md) | `foames-discover-delmia-apriso` |
| ERPNext | ERP | [erpnext/SKILL.md](erpnext/SKILL.md) | `foames-discover-erpnext` |
| Rockwell FactoryTalk ProductionCentre and PharmaSuite | MES / MOM | [factorytalk_productioncentre/SKILL.md](factorytalk_productioncentre/SKILL.md) | `foames-discover-factorytalk-productioncentre` |
| Process historians: AVEVA PI, InfluxDB, Ignition Tag Historian, TimescaleDB and SQL | Historian | [historian/SKILL.md](historian/SKILL.md) | `foames-discover-historian` |
| Ignition | SCADA | [ignition/SKILL.md](ignition/SKILL.md) | `foames-discover-ignition` |
| Siemens Insights Hub (Opcenter Intelligence) | Industrial data platform | [insights_hub/SKILL.md](insights_hub/SKILL.md) | `foames-discover-insights-hub` |
| Körber Werum PAS-X MES | MES / MOM | [koerber_pasx/SKILL.md](koerber_pasx/SKILL.md) | `foames-discover-koerber-pasx` |
| Rockwell Plex Smart Manufacturing Platform | MES / MOM | [plex/SKILL.md](plex/SKILL.md) | `foames-discover-plex` |
| Proficy Smart Factory MES (Velotic) | MES / MOM | [proficy/SKILL.md](proficy/SKILL.md) | `foames-discover-proficy` |
| SAP S/4HANA | ERP | [s4hana/SKILL.md](s4hana/SKILL.md) | `foames-discover-s4hana` |
| SAP Digital Manufacturing | MES / MOM | [sap_dmc/SKILL.md](sap_dmc/SKILL.md) | `foames-discover-sap-dmc` |
| Tulip | MES / MOM | [tulip/SKILL.md](tulip/SKILL.md) | `foames-discover-tulip` |
| WireGuard | Native VPN topology | [wireguard/SKILL.md](wireguard/SKILL.md) | `foames-discover-wireguard` |

There is one skill per vendor folder under [docs/vendors/](../../vendors/README.md), named the same way.

## Writing a skill for another vendor

Copy [_template/](_template/SKILL.md) to a folder named like the vendor's folder under `docs/vendors/`, fill in every placeholder from the vendor's **public** documentation (never from material behind a customer login, and never naming a customer, tenant or plant), keep the Hard stops block word for word, and run the check:

```bash
python -m unittest discover -s .github/scripts -p "test_*.py" -v
```

`.github/scripts/check_discovery_skills.py` checks that every vendor has a skill, that each has valid front matter, the required sections in order and the Hard stops block identical to the baseline's, that no placeholder is left, that its links resolve, that it carries no credential-like strings and recommends no unsafe commands, and that the report folder is git-ignored. CI runs it on every pull request.
