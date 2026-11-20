# Coffee: from land to cup

This example follows a fictional coffee lot through twelve stages: land, nursery,
trellis establishment, cultivation, harvest, wet processing, drying, green coffee,
roasting, packaging, brewing and cup delivery. It demonstrates how process evidence,
quality decisions and material identity can stay connected across a long journey.

All lots, people, orders, quantities, timings, limits and outcomes in the replay are
simulated. Source material explains the process; it is not the origin of the demo's
production measurements. The example has no affiliation with the producers in its
sources and makes no claim of food-safety, agronomic or equipment certification.

## Evidence and scope

[`catalog.json`](catalog.json) contains the ordered stages and a source registry.
Each source records its publisher, URL, type, location, supported claim and limits.
Each stage identifies its sources, candidate FoaMES records and research still to add.
The record names describe how a deployment can represent the evidence; the catalog
does not create those records or claim they exist on a live site.

The sources include university extension guidance, research summaries, standards
overviews, a trellis patent, producer descriptions and the two supplied video tours.
Video findings come from exported English captions, not visual inspection. The
shorter facility tour uses auto-generated captions with transcription errors. No
full transcripts or video media are redistributed here.

The selected trellis method is attributed in the catalog. An independent supporting
paper is pending. Producer claims of increased yield or improved flavor are not
used as simulation multipliers. Historical processing examples and published
averages are not universal recipes or measured results for this fictional lot.

Track material streams separately: coffee fruit, pulp, parchment, removed water,
green beans, roast loss, packaged coffee, spent grounds and beverage. Brew water
is an input; the beverage mass is not the mass of coffee solids consumed. Nursery
seed counts and later harvested fruit mass also have different units and time spans.

## Adding a paper

1. Follow the repository's [research-to-code guide](../../docs/agents/research-to-code.md).
   Check applicability before turning a result into a calculation or acceptance limit.
2. Add a source entry with a stable `id`, title, publisher, durable URL or DOI,
   `kind`, a page/table/section `locator`, one concise supported `claim`, and
   `limitations`. Distinguish a full-paper review from an abstract-only review.
3. Add that ID to the relevant stage's `source_ids` and update its `paper_status`.
   Preserve earlier sources so changes in evidence remain reviewable.
4. Keep demo assumptions explicit. A paper changes a simulation parameter only
   after its population, method, units and uncertainty are applicable and checked.
   Do not infer farm yield, safety or sensory benefits from a title or patent.

Use links and brief original summaries rather than copying papers or proprietary
forms. Stage IDs are stable navigation and traceability keys; retain their order.

## Hosting and integration

Build and verify from the repository root with Python 3.10 or later:

```sh
python -m unittest discover -s examples/coffee -v
python examples/coffee/build.py --out .coffee-build
python -m http.server 8787 --bind 127.0.0.1 --directory .coffee-build
```

Open `http://127.0.0.1:8787`. The output directory is portable: copy its contents
to the existing website's `public/coffee/` directory. The site must permit scripts,
styles and JSON from its own origin on that path. No CDN, server, cookies, account,
third-party scripts or new service subscription is required.

The public replay executes FoaMES's actual pure counter, OEE, process discovery and
OCEL export modules at build time. The browser explores the resulting five recorded
scenarios; it does not connect to a live Frappe database. `data.json` identifies the
source revision and every input is simulated. The normal scenario has an explicit
cup handoff; a moisture hold has no downstream records; a missing state interval
stays Unknown loss; a later package concern preserves delivery history while
identifying downstream records for review. Export buttons download the selected
scenario and its object-centric event log (OCEL).

The mass balance uses one illustrative 1,000 kg cherry lot. Nursery counts and land
area are identities, not mass inputs. Wash water is outside the simplified cherry
balance and must be metered separately in a real deployment. Brewing is a sampled
18 g dose from one 250 g package; its 336 g water input is explicitly included.
Other packaged inventory is not implicitly brewed or delivered. Packaging OEE is
for a 90-minute window with a fictional six-second ideal package cycle; it does not
measure orchard productivity or the whole multi-year journey.

Live Frappe record integration is a separate step and is not established by these
content files. Public replay interactions must not write to equipment, change a
production lot, post an ERP transaction or claim to be a live plant connection.
Any later authenticated write path must retain FoaMES permissions, the write gate,
human approval where required, and idempotent event handling.

## Three views of one operation

The supply chain, manufacturing and engineering modes share the same stage,
scenario, material trace and asset identities. Changing the view changes the
information emphasized; it does not restart a lot, create equipment or change a
quality decision. Supply chain follows material and handoffs, manufacturing
connects work instructions to production evidence, and engineering exposes asset
definitions and signals.

[`explorer.py`](explorer.py) supplies sample assets, work instructions, graphs and
a new-product proposal. Equipment silhouettes are keyed to named sample records
using the actual FoaMES DocType fields. Agricultural locations and infrastructure
retain their appropriate Facility Zone or Facility Asset identity. The drawings
identify equipment functions; they are original schematic illustrations, not OEM
drawings, dimensional models or verified installed hardware.

The **How FoaMES supports this** controls open concrete sample instructions and
record definitions. Work-instruction examples expose steps, capture types and
review requirements. They are teaching examples, not approved operating procedures;
opening a sample neither starts a Work Instruction Run nor signs a step. Graphs
identify their units and scenario, and include readable data tables. Missing
signals remain missing; stages not reached by a held lot have no production data.

## CLR espresso and PID demonstration

**Explore CLR espresso** opens a Gaggia Classic Pro RI9380-inspired sample Machine
with an original SVG illustration, a CLR blue (`#3683A4`) powder-coat concept,
olive (`#A2A342`) accents, a custom PID display and an espresso cup. Manufacturer
documentation supports the machine's recognizable form; the coating, retrofit
and model values are fictional customizations. Source links and their limits are
included under brewing evidence. This is not a depiction of the newer Classic UP
or an assertion that the original Classic Pro shipped with a PID.

The `espresso_pid` scenario reuses the normal upstream lot and adds its own brew
and cup identities. Its teaching balance is 18 g coffee plus 54 g water becoming
36 g beverage and 36 g wet puck/retention; the original filter route stays unchanged.
At an assumed 10% TDS, that espresso has 20% extraction. A separate recorded handoff
is still required; filling the cup in the playback does not create a delivery.

[`espresso.py`](espresso.py) computes a deterministic, one-second PID teaching
model with proportional, integral and derivative feedback, output clamping and
anti-windup. Its 90-second replay starts at an assumed 90°C, uses a fictional 93°C
setpoint, introduces a brew heat load at 45 seconds and shows recovery after 75.
The coefficients are not fitted to Gaggia equipment, and assumed cup flow is
independent of temperature control. The panel can play, pause, restart or scrub
the precomputed samples; it never writes tags or connects to hardware. The full
sample tables and a Draft espresso-review instruction remain available.

## New coffee introduction and feature coverage

The Arabica introduction is a proposed product/variety trial, not a claim that
Arabica is new to Kona or that the existing lot has changed species. Its visual
route reuses the same stage and equipment IDs. Requirements, trial planning,
review gates, transfer and release evidence remain distinct from the completed
coffee scenario. A proposal does not add production events, release a held lot,
or enter material genealogy.

The feature coverage view distinguishes computed replay behavior, sample record
mappings and future integrations. In a real deployment the next work includes
supplier and ERP identities, finite-capacity scheduling, maintenance and
commissioning, calibration/qualification, safety and risk, utilities and climate
context, and authenticated work-instruction execution. A link to a FoaMES feature
does not mean that feature has executed in this static demo. The future climate
providers require their own data acquisition, provenance and licensing review.

| Capability | Coffee use and remaining coverage |
| --- | --- |
| [Work instructions](../../docs/work-instructions.md) | Inspect sample steps and limits here; an authenticated site is needed for released revisions, execution, independent sign-off and hold disposition. |
| [NPI and transfer](../../docs/life-sciences.md) | The Arabica proposal maps product requirements and trial evidence onto the existing route. Customize the life-sciences templates for coffee; no review is approved here. |
| [Scheduling](../../docs/scheduling.md) | Plan trial and regular batches against shared roaster/packager capacity. This demo does not reserve equipment or compute a finite-capacity schedule. |
| [Maintenance](../../docs/maintenance.md) and [commissioning](../../docs/commissioning.md) | Shared asset IDs provide the link for readiness, service and handover evidence; current sample graphs are not service or commissioning records. |
| [SPC](../../docs/spc.md) and [qualification](../../docs/validation.md) | Future measured roast, fill-weight and brew trials can support analysis. The sample graphs do not establish statistical control, calibration or qualification. |
| [Risk](../../docs/risk-management.md) and [P&IDs](../../docs/pid.md) | Link hazards, controls and instrument tags to the same equipment. Neither a safety review nor an engineered drawing is completed by this replay. |
| [Building management](../../docs/building-management.md) | Utilities and environmental context can later join the asset framework with explicit measurement quality and provenance. No weather provider is connected here. |
| [Adapters](../../docs/adapters.md) and [machine data](../../docs/machine-data.md) | Supplier/order identities and actual equipment observations need configured connections. All shown identities and readings remain simulated. |

## Acceptance checks

Run the coffee suite above after changing the explorer, including its DocType
field checks and scenario consistency checks. The Coffee demo workflow runs it
on Python 3.10 and 3.14. Browser verification additionally checks:

- Switching all three modes preserves the selected stage, scenario and trace.
- Each stage resolves its asset and work-instruction sample; equipment dialogs
  display the corresponding definition, graph units and underlying table.
- Keyboard users can open and close dialogs, including Escape, and return to
  their originating control. The layout remains usable on a narrow viewport.
- The moisture hold has no downstream readings or cup; the network gap remains
  visible; recall preserves delivery history and forward-trace scope.
- The proposed Arabica route uses existing stages/assets without changing replay
  records, quantities, OEE, work-instruction execution or release decisions.
- Downloaded scenario data retains the shared definitions and simulation labels.
- The espresso view preserves exact model samples, pauses on dialog close and
  scenario changes, and supports keyboard scrubbing without automatic playback.
  Cup fill and readouts agree with the selected sample. Filter and espresso assets
  never display each other's signals, and the espresso OCEL retains its own cup.

Before calling a hosted version complete, verify the deployed journey from the
first stage to cup handoff, backward lot tracing, held-lot behavior, source links,
simulation labels and the calculations shown. Report separately which checks ran
locally, on the hosted replay, and on a live Frappe site.
