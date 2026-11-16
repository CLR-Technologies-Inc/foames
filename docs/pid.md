# P&IDs: the tag register, DEXPI import and the live P&ID view

A piping and instrumentation diagram (P&ID) is how a process plant names its equipment, lines, valves and instruments. FoaMES keeps those names as a **tag register**, ties each tag to the machine and signal that carry its live value, and shows any P&ID with the plant's live state on it. Engineers keep drawing in their P&ID tool; FoaMES imports what it draws.

What this gives you:

- One plant-wide register of tags (`FIC-101`, `P-101`, line `1002`), each with its type, what it is located on, its ISA-5.1 meaning and its range.
- Import from **DEXPI**, the open P&ID exchange standard that AVEVA, Hexagon Smart P&ID, AutoCAD Plant 3D and other P&ID tools export, or from an instrument index spreadsheet as CSV.
- The **P&ID Viewer** page: the drawing's layout with machine states on equipment and live values on instruments, refreshed every 30 seconds.
- Links from tags to signals, with suggestions made from the OPC UA nodes and Sparkplug metrics already mapped and the measurement names machines report.
- An hourly suggestion rule that flags linked instruments that went silent or read at a range limit.
- Read-only MCP tools, so an agent can answer "what feeds E-101" or "what is FIC-101 reading".

FoaMES only reads. It never writes to an instrument, a PLC or a SCADA system, and a P&ID in FoaMES is a view of the drawing, not the drawing of record.

## The records

| DocType | Holds |
| --- | --- |
| **PID Component** | One tag. Named by the tag itself, so a tag is one record however many drawings show it. Type (Equipment, Instrument, Line, Valve, Actuator, Other), class (for example `CentrifugalPump`, `GlobeValve`, or `Field` / `CentralLocation` for an instrument), description, drawing, plant area, **Located On** (the equipment or line it belongs to; for a transmitter, the instrument function it serves), the ISA-5.1 reading, the live signal (machine, event type, signal name, source, address, historian tag), the range (unit, low, high), an ERP reference and the attributes the P&ID tool exported. |
| **PID Drawing** | One sheet: drawing number, title, revision, status (Draft, Issued, Superseded), plant area, the DEXPI file, the layout, and the process and signal **connections** drawn on it. |

Roles: FoaMES Engineer and System Manager create and change both; every other FoaMES role reads them.

## ISA-5.1 tags

Instrument tags follow the ANSI/ISA-5.1 identification letters: a first letter for the measured variable, optional variable modifiers, then the functions, then the loop number. FoaMES reads them when a component of type Instrument or Valve is saved and fills **Meaning**, **Measured Variable**, **Functions** and **Loop Number**:

| Tag | Meaning | Loop |
| --- | --- | --- |
| `FIC-101` | Flow indicate control | F-101 |
| `PDT-2003A` | Differential pressure transmit (parallel instrument A) | P-2003 |
| `10-LSHH-305` | Level switch high high, area 10 | 10-L-305 |
| `PSV-12` | Pressure safety valve | P-12 |
| `PI4712.01` | Pressure indicate (DEXPI-style number) | P-4712.01 |

Separators are normalised (`FIC 101`, `FIC_101` and `FIC-101` are the same tag); dots stay, because DEXPI loop numbers use them. Where the standard is ambiguous the reader resolves it the way P&IDs commonly do: `S` straight after the first letter is the safety modifier only before `V` or `E` (PSV, TSE) and the switch otherwise (PSH, LSLL); `F` after the first letter is the ratio modifier only for flow (FFIC). The letters marked "user's choice" in the standard are reported as such. The rules are in `foames/foames_pid/isa51.py`, and the `foames_pid_parse_tag` tool reads any tag without a record.

## Importing a DEXPI file

1. Export the P&ID from your P&ID tool as DEXPI (Proteus XML, DEXPI 1.x) or as a DEXPI 2.x model file.
2. Create a **PID Drawing** with its drawing number, set **Source Format** to DEXPI, attach the file and save.
3. Click **Import DEXPI**.

The import reads:

- **Equipment** with its tag (`TagName`, or prefix, sequence number and suffix), class, description and design attributes. Sub-equipment such as chambers and nozzles is drawn, not registered.
- **Lines**: each piping network system with a line number becomes a Line component (description: nominal diameter, fluid code, piping class).
- **Valves** that carry a plant tag: the valve an actuating system operates gets the actuating system's number (`FV-101`), and a valve with a position number (`SV 104.01`) gets that. Component numbers that count within a line (`C1`, `C2`) are not plant tags and are not registered.
- **Instruments**: each process instrumentation function becomes its tag (category + functions + number), and each signal-generating function with a number (the transmitter, `FT-101`) becomes a component located on it. Where the transmitter sits (a piping item, a nozzle) gives the instrument's **Located On**: the line or the equipment.
- **Loops**: the loop number from the instrumentation loop function.
- **Connections**: following the piping from nozzle to nozzle through tees, valves and reducers gives the **process connections** between equipment, each labelled with the line it leaves by. Each instrument gives a **signal connection** from where it measures.
- **Layout**: the position of each item, the centre lines of the piping and the measuring and signal lines, and the sheet extent.

Importing again updates what the file says about each tag (type, class, description when the file has one, Located On, loop, attributes) and replaces the drawing's connections and layout. It never changes what people set in FoaMES: the machine, the signal, the range, the historian tag and the ERP reference stay. A tag that another drawing already owns is left as it is and listed in **Last Import**; tags that were on the drawing before but are no longer in the file are kept and listed there too, for someone to check and disable. The file's own tag is used as written: if the P&ID writes `PI4712.01`, that is the tag.

What the import does not do: write DEXPI back, draw the originating tool's symbols (the viewer uses simple generic symbols in the spirit of ISA-5.1 and ISO 10628), or import DEXPI process models (`Process/ProcessModel`, block-flow level). A file that declares a DOCTYPE or entities is refused, as DEXPI never needs one.

## Importing an instrument index (CSV)

Most plants keep an instrument index and equipment list in a spreadsheet. Save it as CSV (comma, semicolon or tab) and import it with `foames.foames_pid.api.import_tag_register` (`csv_text`, optional `drawing`). Headers are matched loosely:

| Field | Headers that map to it |
| --- | --- |
| Tag | Tag, Tag No, Tag Number, Tag Name, Instrument Tag |
| Type | Type, Component Type, Item Type, Category (blank: read from the tag, an ISA tag with functions is an Instrument, otherwise Equipment) |
| Description | Description, Service, Name |
| Drawing | Drawing, P&ID, P&ID No, Drawing Number |
| Located On | Parent, Equipment, Line, Line Number, Located On |
| Machine, Signal | Machine; Signal, Signal Name, Measurement, Counter |
| Address | Address, Node ID, OPC UA Node, SCADA Tag, PLC Address |
| Historian Tag | Historian, Historian Tag, PI Tag, PI Point |
| Range | LRV, Range Low; URV, Range High; UoM, EU, Units |

Other columns are kept as attributes. A blank cell leaves the field as it is, so a partial sheet updates only what it has. A machine or drawing that does not exist is reported and left empty. **Export tag register** on a drawing (or `export_tag_register`) writes the same columns back out.

A drawing typed in by hand (Source Format Manual) needs no file: give components the drawing and Located On, add connection rows for what feeds what, and the viewer lays it out from the register, equipment left to right in process order with their instruments above them. Layout X and Layout Y on a component place it exactly.

## Linking tags to live signals

The **Live Signal** section of a PID Component says which Machine Events carry its value:

| Component | Machine | Event Type | Signal Name |
| --- | --- | --- | --- |
| Pump `P-101` | the pump's Machine | State | (empty: the machine's state) |
| Transmitter `PT-201` | the machine whose gateway reports it | Measurement | the measurement name in its events |
| Totaliser `FQI-7` | the machine | Count | the counter name |

Signal Source, Signal Address and Historian Tag record where the value comes from, for people and agents; FoaMES reads the value from Machine Events, which arrive through the usual paths ([machine-data.md](machine-data.md)).

**Suggest signal links** on a drawing compares each unlinked tag with machine codes, titles and Source IDs, with the OPC UA nodes and Sparkplug metrics in Machine Data Settings, and with the measurement names machines reported in the last 30 days. `ns=2;s=[default]Area1/FIC_101/PV` and `Line1/FIC101PV` both match `FIC-101`; `FIC-1010` does not. Each suggestion shows why it was made, and nothing is linked until a person ticks it and applies it.

## The P&ID Viewer

Open it from a drawing (**Open in P&ID Viewer**), from a component (**Show on drawing**, which highlights it), or at `/app/pid-viewer`. Equipment linked to a machine is coloured by the machine's state (the Floor View colours); an instrument shows its last value and unit, in red when it is at or beyond its calibrated range limit and in grey italics when it is more than an hour old. Click any tag to open its component. The page refreshes every 30 seconds.

`foames.foames_pid.api.get_drawing_view(drawing)` returns the same SVG with the overlay, for other pages and agents. Every tagged symbol is a `<g data-tag="...">`, so the picture can be read without parsing geometry.

## The suggestion rule

`foames.foames_pid.rules.instrument_signals` runs with the hourly suggestion rules. For each instrument linked to a Measurement or Count signal it raises a **Machine Data** suggestion when:

- no value has arrived in 24 hours (`pid-signal-silent:<tag>`): the gateway mapping or the instrument needs a look, or the link should be cleared if the tag is out of service;
- the last value is at or beyond Range Low or Range High (`pid-range-high:<tag>`, `pid-range-low:<tag>`): a transmitter pinned at a range limit is no longer measuring.

Both keep one open suggestion per tag; a resolved one reopens if the finding recurs.

## For agents

| Tool | Returns |
| --- | --- |
| `foames_pid_list_components(drawing, component_type, machine, linked, search, limit)` | The register, filtered |
| `foames_pid_get_component(tag)` | One tag: register entry, ISA reading, live value with its flag, what is located on it, its connections |
| `foames_pid_get_drawing(drawing)` | A drawing's title block, components and connections: what feeds what, along which line |
| `foames_pid_parse_tag(tag)` | The ISA-5.1 reading of any tag |
| `foames_pid_suggest_links(drawing)` | Candidate signal links with reasons; applying them stays with people |

An agent tracing a quality problem can go from a machine to its P&ID tag, to the line it feeds, to the instruments on that line and their values, without anyone drawing the connection for it.

## Code

| Path | What |
| --- | --- |
| `foames/foames_pid/isa51.py` | ISA-5.1 tag reading (pure) |
| `foames/foames_pid/dexpi.py` | DEXPI 1.x and 2.x reader into a `PlantDiagram` (pure) |
| `foames/foames_pid/svg.py` | The SVG view and the auto layout (pure) |
| `foames/foames_pid/linking.py` | Link suggestions (pure) |
| `foames/foames_pid/register.py` | The CSV register (pure) |
| `foames/foames_pid/overlay.py` | Live value flags and the rule's findings (pure) |
| `foames/foames_pid/api.py`, `rules.py` | Whitelisted methods and the suggestion rule |
| `foames/foames_pid/doctype/`, `page/pid_viewer/` | PID Component, PID Drawing (with PID Connection, PID Component Attribute), the viewer page |

DEXPI is maintained by the DEXPI initiative ([dexpi.org](https://dexpi.org)); the importer was checked against the public DEXPI training test cases and reference P&ID. ISA-5.1 is the ANSI/ISA standard *Instrumentation and Control Symbols and Identification*.
