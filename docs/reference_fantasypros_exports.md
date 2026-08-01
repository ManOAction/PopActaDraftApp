# Reference — FantasyPros CSV exports

Validated 2026-07-31 against the exports now in `data/fantasypros/` (pulled 2026-07-31 for the
2026 season). Durable facts about the file format and how it relates to Pop Acta Premier League
scoring.

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

**DST projections are also missing**, which turns out not to matter — defenses are streamed and
there is no K slot, so QB/RB/WR/TE is the whole ranked universe (BLK-2, closed by decision).

## The rankings export — variants matter more than expected

Two different rankings exports were pulled on 2026-07-31, and the differences between them are
the whole story. Both are the **draft cheat-sheet** variant, sharing this header:

```
RK, TIERS, PLAYER NAME, TEAM, POS, BYE, UPSIDE, BUST, SOS, ECR VS ADP, AVG. DIFF, % OVER
```

| | 1QB ("ALL") | Superflex ("OP") — kept |
| --- | --- | --- |
| rows | 732 | 768 |
| first QB, overall rank | **26** | **1** |
| QBs in top 24 | 1 | **13** |
| DST / K rows | 32 / 29 | **none** |

Three durable facts:

**1. The scoring/format setting silently changes the whole ordering.** The 1QB file put Josh Allen
at overall rank 26; the superflex file has QBs at 1–6. Feeding the 1QB file into a superflex
league makes every QB decision wrong in the same direction.

> **Import-time integrity check:** if the first QB is not inside roughly the top 5 overall, the
> file is not a superflex export. Reject it and say so — do not import it.

**2. Neither variant has `ADP` or `Std Dev`.** `ECR VS ADP` is an integer *rank delta* and
`AVG. DIFF` is not a standard deviation. Survival probability needs absolute ADP **and** its
variance, so a different export variant — the one carrying
`Best / Worst / Avg / Std Dev / ADP` — is still required. Tracked as BLK-1 in
[open-issues.md](open-issues.md).

**3. The superflex export drops DST and K entirely** — positions are QB/RB/WR/TE only. This is
**fine**: defenses are streamed and the league has no K slot, so QB/RB/WR/TE is exactly the
universe this app ranks (BLK-2, closed by decision). Note the consequence for the projections
files too — `QB ∪ FLX` covers all 518 QB/RB/WR/TE players, so **the projection data already in
`data/fantasypros/` is complete for our purposes.** No supplementary export is needed.

What *is* good in the superflex file: `RK` as a consensus superflex ordering, positional rank
inside `POS`, and **`TIERS` complete on all 768 rows**.

> **Correction (2026-07-31).** This section previously claimed `BYE` was complete on all 768
> rows. **It is not.** `BYE` is the literal string `'-'` on **125 rows**, beginning at `RK 200`
> (`Stefon Diggs`) — free agents and unsigned players. `int(row["BYE"])` raises on row 200.
>
> Raising is the *correct* behaviour under the fail-loudly rule, so the importer needs no
> special casing — but it must not be surprised by it, and this doc must not promise otherwise.
> All 125 affected rows are ranked 200 or worse, i.e. outside the 160-pick draftable window, so
> bye weeks **are** complete for every player who can actually be drafted. Treat `'-'` as
> "unrostered, no bye" and reject it only for a player inside the draftable window.

Two further parsing notes for this file specifically:

- It has **no junk spacer row** — that trap belongs to the *projections* exports. All 768 rows
  are real. The `utf-8-sig` and quoted-thousands-separator traps still apply.
- **`RK` is a dense 1..768 sequence with no gaps**, so every consecutive difference is exactly 1.
  That makes rank useless as a clustering axis — there are no gaps in it to find. Cluster on
  projected points instead. See `docs/plan_phase2_decision_engine.md`.

## The ADP export — a third file, a different shape, five traps

`FantasyPros_2026_Superflex_ADP_Rankings.csv`, pulled 2026-08-01. **278 rows.** This is the *ADP*
page, not the rankings page, and its format resembles neither of the others.

```
OP,Overall,Player (Bye),Sleeper,FFPC,AVG,Real-Time
1,22,Josh Allen   BUF (7),1,2,1.5,3
```

It genuinely is superflex: Josh Allen sits at `OP` 1 with `Sleeper` ADP 1. Coverage is complete
across the 160-pick window — `AVG` is present on all 278 rows, and the top-160 `AVG` values run
**1.5 … 164.0**, confirming ADP is on the same scale as pick numbers rather than an
offence-only board that would compress well below 160.

> ### Trap 1 — `Overall` is the 1QB rank, sitting right beside the superflex one
>
> `OP` is the **superflex** ADP rank. `Overall` is the **1QB** rank. Josh Allen is `OP` 1 and
> `Overall` 22. Both columns are in the same file, adjacent, neither labelled "superflex".
>
> **Reading `Overall` silently reintroduces the exact bug this project has now guarded against
> three times.** Key on `OP`. Assert that the top of `OP` is QB-heavy at import.

**Trap 2 — missing values are an EM DASH (`—`, U+2014), not `-` and not empty.** The file is
valid UTF-8. A parser testing for `'-'` or `''` will treat em dashes as data and `float()` will
raise, or worse, a `.replace('-','')` will silently produce nonsense. Note the console renders
`—` as `?` because it is cp1252 — see the platform gotchas in
[architecture.md](architecture.md). Do not "fix" the file's encoding on the basis of that display.

**Trap 3 — `Player (Bye)` is a composite field.** `'Josh Allen   BUF (7)'` — name, **multiple
spaces**, team, then the bye in parentheses. Split on a 2-or-more-space run, not a single space.

**Trap 4 — three rows carry a name only.** `Stefon Diggs`, `Tyreek Hill`, `Joe Mixon` have no team
and no bye (free agents). The parser must accept a name-only field rather than raising.

**Trap 5 — `AVG` excludes `Real-Time`.** Verified on all 278 rows: `AVG == mean(Sleeper, FFPC)`,
and where `FFPC` is missing, `AVG == Sleeper`. `Real-Time` is a third, separate source that is
*not* folded in. Do not assume `AVG` is the mean of everything on the row.

### What it still does not contain

**No `Std Dev`, and no `Best`/`Worst`/range column.** Survival probability needs ADP *and its
variance*; this supplies only the first. BLK-1 stays open for the dispersion half.

The two independent sources (`Sleeper`, `FFPC`) give a cross-platform spread, and it does behave
the way a real dispersion measure should — median `|Sleeper − FFPC|` is **4.0** for ADP ≤ 40 and
**15.0** for ADP > 100, so spread grows with ADP. Useful as a **shape sanity check**; not a
substitute for `Std Dev`. It measures disagreement between two platforms with different formats,
not draft-to-draft variance within one, and two points cannot estimate a standard deviation.

## Why not the FantasyPros API

The free API tier caps **every** endpoint at 10 rows (`public_api_limited: true`) — 10 of 768
ranked players, 10 of 8,509 in the player list. Unusable for a 160-pick draft, and full access is
prohibitively expensive. Verified 2026-07-31. Use the web CSV export.
