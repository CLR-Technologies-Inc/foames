# Production counts jump after a PLC restart

Line 3's press reports its parts counter as a running total. Last night the PLC restarted at 02:14. Its counter went from 48,112 to 0 and then counted up again. FoaMES's OEE for that shift shows about 4,800 more good parts than the line made, and the planner already noticed.

Find out why FoaMES counted parts that were never made and fix it. Keep every counter rule that `AGENTS.md` describes, including rollover handling for machines whose Counter Rollover is known. Add tests that would have caught this.
