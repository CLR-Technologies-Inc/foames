# Does the hospital's meter show the energy saving it reported?

Plant A here is a 496-bed hospital of about a million square feet. Its facilities team retrofitted lighting to LED, capped operating room air changes at 20 an hour in use and 6 when empty, widened setpoints outside patient areas, set back unoccupied spaces and maintained its steam traps.

A US Department of Energy Better Buildings showcase of a project like this (<https://betterbuildingssolutioncenter.energy.gov/showcase-projects/cleveland-clinic-hillcrest-hospital>) reports energy use intensity falling from 587 to 460 kBtu per square foot a year, which over the building's area is about 127,000 MMBtu a year. The hospital's FoaMES site reports the inpatient census as the line's output, in patient-days, and the site energy meter. The energy manager wants the measured saving per patient-day set against that figure. The census never stops, so there is no downtime, setup or scrap; the `scrap` counter stays at zero.
