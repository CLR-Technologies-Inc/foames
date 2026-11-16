FoaMES is licensed under the [Apache License 2.0](https://github.com/CLR-Technologies-Inc/foames/blob/main/LICENSE). This page explains why, and how that fits with the CLA and with the projects FoaMES runs on.

## What the project wanted from a licence

- **Plants and integrators can adopt it without legal friction.** A manufacturer can run FoaMES, change it for its own lines, and build closed extensions or adapters on top of it, without having to publish its own process knowledge. Shop-floor software often encodes exactly the know-how a plant competes on.
- **Vendors and system integrators can ship it.** Apache-2.0 allows commercial redistribution, including inside products, as long as the licence and NOTICE travel with it.
- **Clear patent terms.** Unlike MIT or BSD, Apache-2.0 includes an express patent licence from every contributor for their contribution, and ends that licence for anyone who sues over patents in FoaMES. For industrial users, whose legal teams ask about patents first, that clarity matters.
- **Credit is kept.** The NOTICE file carries the prior art and credits (the ERPNext issue it answers, Floorgraph, Bluesky and Tiled) to every redistribution.

## Why a CLA

Contributors sign a Contributor License Agreement modelled on the Apache Software Foundation's individual and corporate CLAs. You keep the copyright in your work. The CLA records that you had the right to contribute it and grants the same copyright and patent licence that Apache-2.0 describes, to the project and to everyone who receives FoaMES. That gives every user confidence that each line in the repository was contributed with the rights to do so.

## How it sits next to Frappe and ERPNext

- The **Frappe framework** is MIT-licensed, a permissive licence compatible with Apache-2.0.
- **ERPNext** is GPL-3.0. FoaMES does not import ERPNext or include any of its code; it is a separate app, and the ERPNext adapter reads ERPNext's tables and calls its whitelisted functions at run time only when ERPNext happens to be installed on the same site. FoaMES installs and passes its tests without ERPNext.
- **Optional gateway libraries** (paho-mqtt, asyncua) are installed by you into the bench, only if you use those gateways.

Each release's CycloneDX SBOM lists every dependency with its licence, so you can check the whole tree against your own policy ([Licensing and SBOM](Reference-Licensing-and-SBOM)).

This page explains the project's reasoning; it is not legal advice.
