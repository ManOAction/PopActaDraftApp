# Open issues

Bug and issue tracker. Read this when **triaging a bug**, or before writing code in an area that
burned us in 2025.

**Conventions.** Each issue gets a stable ID so commits and docs can cite it. Move items to
*Closed* with the date and what actually fixed it — don't delete them, the history is the point.
`LEG-*` are defects in the 2025 app: they are **not** work items, they are traps to avoid
reproducing.

---

## Blocked — needs external input

| ID | Issue | Blocks | Owner |
| --- | --- | --- | --- |
| BLK-1 | **`Std Dev` source not identified.** ADP itself was solved 2026-08-01. Blocks *only* survival probability and the `Plan` assembly; the interim `u(p \| R)` board needs neither. See below. | `survival.py`, `advisor.Plan` | Jacob |
| BLK-3 | **Draft slot unknown.** Sleeper's `draft_order` is not yet populated for draft `1385689586394488832`. | Next-pick math uses a placeholder until set | Sleeper |

### BLK-1 update, 2026-08-01 — ADP landed, dispersion did not

`FantasyPros_2026_Superflex_ADP_Rankings.csv` (278 rows) supplies **real superflex ADP**: Josh
Allen at `OP` 1, complete coverage of the 160-pick window, and on the same scale as pick numbers
(top-160 values run 1.5 … 164.0).

**What it unblocked immediately:** the draft-demand replacement basis is now confirmed against
market data rather than consensus rank — **32 QBs go inside the top 160**, versus the 29 estimated
earlier. Replacement level, the lineup DP, tier detection and bye-week import are all unblocked.

**What is still blocked:** the file carries **no `Std Dev`** and no `Best`/`Worst` columns.
Survival probability needs ADP *and* its variance, so it — and the `Plan` assembly that consumes
it — remain blocked. The remaining candidate source is the FantasyPros **ECR rankings** export
variant carrying `Best / Worst / Avg / Std Dev`. Modelling `σ = f(ADP)` instead would mean
inventing a coefficient, which is how LEG-1 and LEG-5 happened; prefer pulling the file.

Five parsing traps in this export — including an `Overall` column that is the **1QB** rank sitting
beside the superflex `OP` — are documented in
[reference_fantasypros_exports.md](reference_fantasypros_exports.md).

### BLK-1 detail — the earlier cheat-sheet export

`data/fantasypros/FantasyPros_2026_Draft_OP_Rankings.csv` (768 rows), pulled 2026-07-31.

**The superflex half is solved.** Verified: the top 6 overall are all QBs (Allen, Jackson, Maye,
Burrow, Daniels, Hurts) and 13 of the top 24 are QBs. That is what superflex ordering looks like;
the earlier 1QB export had its first QB at overall rank 26. Use this file, not a standard one.

**The ADP half is not.** This is the **draft cheat-sheet variant**, whose header is:

```
RK, TIERS, PLAYER NAME, TEAM, POS, BYE, UPSIDE, BUST, SOS, ECR VS ADP, AVG. DIFF, % OVER
```

There is **no `ADP` column and no `Std Dev` column**. `ECR VS ADP` is an integer *rank delta* and
`AVG. DIFF` is not a rank standard deviation. Survival probability needs an absolute ADP **and its
variance**; neither is recoverable from these columns.

**What to pull:** same Half PPR + Superflex ("OP") settings, but the export variant that carries
**`Best / Worst / Avg / Std Dev / ADP`**.

**Usable today, without the re-pull:** `RK` gives a superflex consensus ordering, `TIERS` is
complete on all 768 rows, and `POS` carries positional rank. **Bye weeks can be imported from
this file now** — that closes the LEG-4 gap independently of the ADP problem.

**Correction (2026-07-31):** an earlier version of this entry claimed `BYE` was also complete on
all 768 rows. It is not — `BYE` is the literal `'-'` on **125 rows**, starting at `RK 200`
(`Stefon Diggs`). Every affected row is ranked 200 or worse, i.e. outside the 160-pick draftable
window, so bye weeks are complete for every player who can actually be drafted and the conclusion
above still holds. Detail in [reference_fantasypros_exports.md](reference_fantasypros_exports.md).

**The missing DST and K rows turned out not to matter.** This export covers QB (63), RB (242),
WR (294), TE (169) only. That is now exactly the universe this app ranks — see BLK-2, closed by
decision. No supplementary export is needed.

---

## Open

| ID | Issue | Severity | Notes |
| --- | --- | --- | --- |
| OPEN-1 | **FantasyPros→Sleeper name matching is unsolved.** Suffixes (`Patrick Mahomes II`), DST naming (`San Francisco 49ers` vs `SF`), and in-season trades will all mismatch. | **High** | A silent mismatch means a drafted player never gets marked. Must fail loudly at import, never at draft time. Plan: match on Sleeper's `search_full_name` + a committed manual override list. |
| OPEN-2 | **Draft-day rehearsal not scheduled.** A full mock draft end-to-end is the only real test of Sleeper polling. | **High** | Must happen with days of margin before 2026-08-28, not the night before. |
| OPEN-3 | ADP moves through August; a stale export produces wrong survival estimates. | Medium | Import must be re-runnable. Re-pull within a few days of the draft. |
| OPEN-4 | No decision on how manual pick entry and Sleeper auto-sync reconcile when they disagree. | Medium | Needs an answer before Phase 3. Last-write-wins is probably wrong. |
| OPEN-5 | **Uncapped draft demand produces a degenerate board.** Deferred 2026-08-01 in favour of end-to-end testing. | **High** — but not blocking | See below. |

### OPEN-5 detail — the replacement-level cap

Draft demand sets `r_pos` to the `(D+1)`-th best player. Real superflex ADP gives `D_QB = 32`, so
`r_QB = QB33`. Measured consequence:

| basis | `r_QB` | top-16 board |
| --- | --- | --- |
| `D_QB = 29` (consensus-derived — what the decision was made on) | QB30 = 192.7 | **1 QB**, #1 Gibbs (RB) |
| `D_QB = 32` (real ADP) | QB33 = 108.9 | **12 QBs**, #1 Allen (QB) +263.3 |
| starter demand (rejected) | QB21 = 269.6 | 1 QB, #1 Gibbs (RB) |

The middle row reproduces the exact board the Phase 2 research independently flagged as degenerate
("+263, QBs at 1, 3, 5–16"). **The cause is a projection cliff, not a modelling error:** the market
drafts 32 QBs, but FantasyPros projects only 29 at starter volume. QB33 is a backup at 238 pass
attempts. Draft demand asks *"what am I stuck with if I punt?"*, which assumes the `(D+1)`-th player
is startable; here it measures the end of the projection list instead.

**Proposed fix (one line in `replacement_levels`):** cap the baseline at the startable cliff —
`r_pos` = the `(D+1)`-th best player **or** the last player projected for starter-level usage,
whichever is better. Self-correcting: for RB/WR/TE the cliff sits well past demand, so nothing
changes there.

**Why it is safe to defer:** the interim board ranks on `u(p | R)` alone, and the cap changes only
the *magnitude* of `r_QB`, not the plumbing. Decide it against a real board during the mock-draft
rehearsal (OPEN-2) — which is a better test than any amount of further analysis. The uncapped
board is visibly wrong, so this will not slip silently.

---

## LEG-* — defects in the 2025 app. Do not reproduce.

All confirmed by reading `legacy/` or last year's `app.db`. Each shipped.

| ID | Defect | Consequence |
| --- | --- | --- |
| LEG-1 | **Roster slots stored as fixed integer columns** (`qb_slots`, `rb_slots`, …), with `flex_eligible_positions` hardcoded to `("RB","WR","TE")`. | **Superflex is inexpressible.** Settings were hand-fudged to `qb_slots=2, rb_slots=3, wr_slots=3, flex_slots=3` against a real roster of `QB1 RB2 WR2 TE1 FLEX2 SUPER_FLEX1 DEF1`. Those numbers fed the VORP baseline, so the engine solved a league that doesn't exist. `DEF` was simply absent. |
| LEG-2 | **`te_slots` omitted from `DraftSettingsUpdate`.** The UI sent it; Pydantic dropped it silently (no `extra="forbid"`). | TE slots could never be changed. Silently corrupted the VORP replacement baseline. |
| LEG-3 | **Pick numbers assigned as `max(actual_pick_number) + 1`.** | Undoing a mid-draft pick leaves a permanent hole in the sequence. Snake order was never modelled at all — `total_teams` was used only as picks-per-round. |
| LEG-4 | **Bye weeks defaulted to `0` on any parse failure**, silently. | All 527 players in last year's DB have `bye_week = 0`. The board displayed "Bye: 0" for every player, all season. |
| LEG-5 | **VORP baseline computed against globally remaining starters**, not against who'd be available at your next pick. | The metric answered a question nobody asks. See `docs/FeatureDescription_PickAdvisor.md`. |
| LEG-6 | **ADP was never imported** — `predicted_pick_number` populated for 0 of 527 players. | No survival math was possible. The column existed and was always null. |
| LEG-7 | **Raw SQLAlchemy ORM objects returned from endpoints**; no response schemas. | Client types were hand-duplicated and drifted from the server. |
| LEG-8 | **No tests. Anywhere.** | Every change was a guess. |
| LEG-9 | `CORSMiddleware` with `allow_origins=["*"]` **and** `allow_credentials=True`. | Invalid combination; browsers reject it. Latent, since there were no credentials. |
| LEG-10 | **`Column` component defined inside `Draft`'s render body.** | Remounted the entire board on every state change. |
| LEG-11 | **Infrastructure documented but never built.** README and roadmap promised Let's Encrypt/TLS; nginx listened only on `:80`, there was no certbot service and no frontend service. | The deployment story was fiction. Being replaced by Caddy. |
| LEG-12 | `alembic` in `requirements.txt` but never used; "migration" meant dropping and recreating the DB. | No schema history. |
| LEG-13 | Import parsed `predicted_pick_number` but the UI never surfaced it; `K` and `DST` were seeded but excluded from every view. | Dead paths that looked functional. |

---

## Closed

| ID | Issue | Closed | Resolution |
| --- | --- | --- | --- |
| BLK-4 | Superflex ADP source unidentified | 2026-07-31 | FantasyPros rankings export supports Half PPR + superflex ("OP"). Folded into BLK-1. |
| BLK-5 | Unclear whether league scoring differed from FantasyPros defaults | 2026-07-31 | Recomputed `FPTS` from raw stats for all 518 players; max deviation 0.62 pts, all rounding. Offensive scoring is identical to default Half PPR. DST unverified — still custom. |
| BLK-6 | Whether the FantasyPros API could replace the CSV loader | 2026-07-31 | **No.** Free tier caps every endpoint at 10 rows (10 of 768 rankings, 10 of 8,509 players). Full access prohibitively expensive. CSV export it is. |
| BLK-7 | Whether to build draft-day notifications | 2026-07-31 | Not building. Slow draft (1hr timer) and Sleeper already notifies. |
| BLK-2 | No DST projections; `DEF` is a required starter | 2026-07-31 | **Closed by decision, not by data.** The strategy is to stream defenses, and the league has no K slot, so neither position is projected, ranked, or recommended. `DEF` and `K` still *parse* — other teams draft defenses and Sleeper sends us those picks, so a model that rejected them would break draft-night sync. Two sets now exist: `Position` (everything parseable) and `RANKED_POSITIONS` (QB/RB/WR/TE). The `DEF` roster slot is excluded from `ranked_starter_slots`, so it never surfaces as an unfilled need. See `docs/plan_phase1_domain_core.md`, decision 1. |
| BLK-8 | `npm install` failed with `EBADF` on the Google Drive path | 2026-07-31 | **Repo relocated to `C:\Projects\PopActaDraftApp`.** `npm install` there succeeds — 184 packages, exit 0, ~27s. The Drive sync layer was the entire cause; nothing in the repo needed changing. `web/` is scaffolded and CI is green. |
