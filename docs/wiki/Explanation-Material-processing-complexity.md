# Material processing complexity (MPC)

> **Upcoming.** MPC arrives with lineside inventory, material queues and dry-line forecasting in [pull request #72](https://github.com/CLR-Technologies-Inc/foames/pull/72). It is **not on `main` yet** and may change in review. This page explains the idea now. The how-to and reference pages will follow once the PR merges. See [Upcoming features](Upcoming-features).

Some materials are easy to handle: a carton of screws can wait on a rack for a month. Others are not. A moisture-sensitive component has a floor life measured in hours. A frozen adhesive must thaw before use. A potent drug substance needs containment, and battery electrode material needs a dry room. Material Processing Complexity (MPC) rates how complex a material is to handle and process on the floor, from 1 to 5. FoaMES then scales its controls to that rating.

MPC is the material counterpart of the [Equipment Complexity Level (ECL)](Explanation-Equipment-complexity-levels). ECL rates the machine. MPC rates what goes through it. The two scales share the same expert pattern at the top.

## Built from existing standards

As far as we found, no single standard scale for material handling complexity exists. Many standards already define the individual factors, though. MPC scores each factor from 0 to 4 using the standard's own classes:

| Factor | Standard it comes from |
| --- | --- |
| Hazard | NFPA 704 highest rating; GHS signal words |
| Occupational exposure band | OEB 1 to 5 |
| Moisture sensitivity | IPC/JEDEC J-STD-033 moisture sensitivity level (MSL) 1 to 6 |
| Storage temperature | USP <659> (controlled room temperature, refrigerated, frozen); cold chain practice |
| Atmosphere (dry process) | Dew-point controlled dry rooms; inert gas; gloveboxes and isolators |
| Cleanroom class at point of use | ISO 14644-1 |
| ESD sensitivity | ANSI/ESD S20.20; ANSI/ESDA/JEDEC JS-001 HBM classes |
| Physical form | Bulk solids flowability (Carr index, Hausner ratio, USP <1174>) |
| Shortest time limit | Shelf life (ICH Q1A), hold time, Q-time, floor life, out-time, pot life |
| Conditioning steps | Thaw, degas, bake, acclimatise, premix |
| Critical material attributes | ICH Q8 |

## From factors to a level

The highest factor sets the level: a score of 0 is MPC 1, and a score of 4 is MPC 5. A material that is moderately difficult in many ways is harder than any one factor suggests. So three or more factors at score 2 or above compound, raising the level by one more, up to 5.

| MPC | Label | Expert oversight | Line-dry safety multiplier |
| --- | --- | --- | --- |
| 1 | Standard | None | 1.0 |
| 2 | Basic controls | None | 1.1 |
| 3 | Controlled | None | 1.25 |
| 4 | Critical | **Human Expert Recommended**: a single expert | 1.5 |
| 5 | Extreme | **Expert Team Required**: a team of experts | 2.0 |

The oversight follows ECL. At MPC 4, one expert in the material can judge whether it is fit to use. At MPC 5, no one person covers every aspect, so a team of experts decides.

## What MPC changes

- **Dispatch.** A time-sensitive material suggests the Earliest Expiry (FEFO) dispatch rule for its queue.
- **Dry-line warnings.** Conditioning time (thaw, degas, bake) is added to the replenishment lead time. The safety multiplier then widens the warning horizon, so a line feeding hard material is warned earlier.
- **Suggestions.** Every suggestion about MPC 4 or 5 material names its level and the oversight it needs.
- **Starting material.** MPC 5 material cannot start until an expert review is recorded. Material past its time limit or expiry is never dispatched automatically at any level. It can only start with a reason given by Quality or Engineering.

## "Dry" in both senses

A line *runs dry* when a machine is starved of material. Industry also calls this line starvation or a material shortage stop, and FoaMES forecasts it from lineside stock. Some floors also run *dry processes*, such as battery cell assembly in a dew-point controlled dry room, or dry granulation. That is a property of the material and the room, not a stock level, so MPC scores it as the Atmosphere factor.

## A prior, not a measurement

The factor scores, the compounding rule and the multipliers are starting points to tune per site. They are not measured results. Like ECL, MPC keeps FoaMES's rule that [agents suggest and people act](Explanation-Agents-suggest-people-act): the rating decides *who* must review, and never lets an agent move or release material on its own. The [materials agent](How-to-Run-the-materials-agent) works this way. It reads lineside stock, queues and MPC, and when a material's MPC and its machine's ECL disagree, it applies the stricter oversight.
