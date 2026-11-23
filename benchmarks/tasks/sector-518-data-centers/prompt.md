# Did the no-cost cooling changes cut the data hall's overhead by 46 percent?

Plant A here is a 1 MW enterprise data hall inside a multi-use building. Its operators raised chilled water and supply air setpoints, rebalanced the cooling units and slowed fans that ran flat out, without buying anything.

A US Department of Energy Better Buildings showcase of a project like this (<https://betterbuildingssolutioncenter.energy.gov/showcase-projects/no-cost-energy-savings-measures-at-a-1-mw-data-center>) reports a 46% reduction in PUE minus 1. In FoaMES the hall reports the UPS output to IT equipment as its line output (counter `good`, in IT kWh) and the overhead meter as its energy, so specific energy is exactly PUE minus 1. The facility manager wants the measured reduction set against the claim. Time the UPS reports a fault is unplanned downtime; there is no scrap counter, so the `scrap` counter stays at zero.
