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
OCEL export modules at build time. The browser explores the resulting four recorded
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

Before calling a hosted version complete, verify the deployed journey from the
first stage to cup handoff, backward lot tracing, held-lot behavior, source links,
simulation labels and the calculations shown. Report separately which checks ran
locally, on the hosted replay, and on a live Frappe site.
