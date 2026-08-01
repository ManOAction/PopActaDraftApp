"""Reading source data into the domain: FantasyPros CSVs and Sleeper payloads.

**This is the only layer allowed to do I/O.** Everything in `popacta.domain` is pure.

The rule that governs this package: *fail loudly at import time, never silently at draft
time.* An unmatched player, a missing bye week, an unparsed column, an export that turns
out not to be superflex — all of it raises here, days before the draft, where there is
time to fix it. The 2025 app defaulted bad data to `0` and displayed wrong numbers for a
season (LEG-4).
"""
