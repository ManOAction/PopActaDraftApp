# Reference — FantasyPros CSV exports

Validated 2026-07-31 against the exports in `scripts/data/FantasyProsExports/`
(pulled 2026-07-31 for the 2026 season). Durable facts about the file format and how it
relates to Pop Acta Premier League scoring.

## Scoring is already correct — verified, not assumed

The league's offensive scoring is **identical to FantasyPros' default Half PPR**. Recomputing
`FPTS` from the raw stat columns using the league's Sleeper `scoring_settings` reproduces their
number across all 518 players:

| file | rows | max abs diff | mean abs diff |
| --- | --- | --- | --- |
| QB | 82 | 0.54 | 0.145 |
| RB | 131 | 0.58 | 0.149 |
| WR | 189 | 0.62 | 0.154 |
| TE | 117 | 0.40 | 0.135 |
| FLX | 436 | 0.62 | 0.147 |

The residual is rounding: FantasyPros publishes stats to one decimal, so recomputation from
rounded inputs drifts a few tenths. There is no systematic difference.

**Still recompute from stats rather than reading `FPTS`.** It costs ~20 lines, it is a pure
function worth unit-testing, and it makes a mid-August scoring change by the commissioner a
non-event instead of a silent wrong-number bug.

**This validates offense only.** DST is absent from these exports and DST scoring *is* custom in
this league (points-allowed tiers). Do not generalize the result to DST.

## Column layout — the trap

Headers repeat (`YDS` and `TDS` each appear twice) **and the order differs between files**:

```
WR.csv   "Player","Team","REC","YDS","TDS","ATT","YDS","TDS","FL","FPTS"   <- receiving first
FLX.csv  "Player","Team","POS","ATT","YDS","TDS","REC","YDS","TDS","FL","FPTS"  <- rushing first
```

A parser keyed on column *names* silently swaps rushing and receiving for every WR in `FLX.csv`.
It does not crash. It just produces wrong projections.

**Key on `(file, column index)`, never on header name.**

Verified layouts:

| file | columns in order |
| --- | --- |
| QB | player, team, pass_att, cmp, pass_yd, pass_td, pass_int, rush_att, rush_yd, rush_td, fl, fpts |
| RB | player, team, rush_att, rush_yd, rush_td, rec, rec_yd, rec_td, fl, fpts |
| WR | player, team, rec, rec_yd, rec_td, rush_att, rush_yd, rush_td, fl, fpts |
| TE | player, team, rec, rec_yd, rec_td, fl, fpts |
| FLX | player, team, pos, rush_att, rush_yd, rush_td, rec, rec_yd, rec_td, fl, fpts |

## Other parsing notes

- **Row 2 of every file is a junk spacer row** (`" ","","",""`). Skip rows whose first field is
  blank.
- Numeric fields use **thousands separators inside quotes** — `"1,381.0"`. Strip commas before
  `float()`.
- Encoding is UTF-8; read with `utf-8-sig` to tolerate a BOM.
- `FLX.csv`'s `POS` column embeds position *and* positional rank (`RB1`, `WR3`) — useful, and the
  only place positional rank appears.
- **`FLX` ∪ `QB` = all 518 players** (436 + 82). The per-position files are subsets. Importing
  just those two files is sufficient and halves the parsing surface.

## What these files do NOT contain

These are **projections** exports. They carry no ADP, ECR, tier, bye week, or rank std dev.

A separate **rankings** export is required for those — set to **Half PPR** and **superflex
("OP")** on the FantasyPros site. That export supplies:

- `ADP` and `Std Dev` — the inputs to survival probability
- `Tier` — cross-checks the tier detection in Phase 2
- `Bye` — absent here; last year's import silently defaulted every bye week to 0

**DST projections are also missing** and must be sourced separately. DEF is a required starter.

## Why not the FantasyPros API

The free API tier caps **every** endpoint at 10 rows (`public_api_limited: true`) — 10 of 768
ranked players, 10 of 8,509 in the player list. Unusable for a 160-pick draft, and full access is
prohibitively expensive. Verified 2026-07-31. Use the web CSV export.
