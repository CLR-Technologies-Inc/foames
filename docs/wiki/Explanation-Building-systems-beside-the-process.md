A plant runs on more than its process route. Chilled water, compressed air, electricity, water and wastewater, the air handlers and rooftop units that hold a hall's temperature and humidity, the server room that runs the MES itself, the cabinets that hold flammable or corrosive stock: none of them is a step a part or a batch goes through, yet any of them can stop production or put people at risk. This page explains how FoaMES treats them and why.

## Watched, not commanded

Building systems already have their own controllers: a building automation system with its schedules, setpoints, interlocks and life-safety logic. That system is designed, commissioned and certified to run them. FoaMES does not replace it and does not write to it. The gateway in `bridges/bms` can only send BACnet ReadProperty requests and Modbus read function codes; the module has no command path. A setpoint written by an MES that does not know why the controller chose its own would be a new hazard, not a feature.

This is the same rule as everywhere in FoaMES ([Agents suggest, people act](Explanation-Agents-suggest-people-act)): a limit crossed becomes a Building Alarm and an Agent Suggestion for a person. If a site ever needs FoaMES to write a building point, it would pass the read-only write gate and wait for an authorised person's sign-off.

## Off the critical path, but on the same floor

Building systems are kept out of the machine model on purpose. A chiller is not a Machine: it has no OEE, no Job Card, no cycle time, and its silence is not production loss. Putting it on the OEE ledger would blur both. So the facility side has its own register (zones, assets, points) and its own alarms, and it meets the production side at four places only:

- **The floor snapshot** carries a facility section, so a person or an agent looking at a stopped line also sees that the hall's air handler has been in alarm for an hour.
- **Production lines on zones.** A zone can name the line it serves, which turns utility use into consumption per good unit made, the energy performance indicator ISO 50001 asks for.
- **Maintenance plans** can be for a facility asset, worn by its own run hours or meter counts.
- **Hazard assessments** link to hazmat storage, so an alarm there is a safety matter from the first second.

## Silence is a condition

As with machines, FoaMES does not fill gaps. A point that stops reporting does not keep its last value forever: after its stale time it raises a communication-loss alarm, its run hours stop counting, and its meter counts nothing across the gap. A meter that drops is a reset unless its rollover is known. These are the same choices as for machine counters and the OEE ledger ([How OEE is counted](Explanation-How-OEE-is-counted)), for the same reason: a number FoaMES shows must be one the plant actually measured.

## Shared vocabulary

Building systems already have open semantic models: Brick, Project Haystack and ASHRAE 223P. FoaMES fills a Brick class and Haystack tags on each asset and point from what it knows, and lets a site keep its own. That keeps the register readable by the tools a facilities team already uses, without FoaMES inventing yet another naming scheme.
