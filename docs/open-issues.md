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
| BLK-1 | **Rankings export pulled, but it is the wrong variant — still blocking.** See below. | Survival probability, tier detection, bye weeks | Jacob |
| BLK-2 | **No DST data at all in the current exports.** The superflex ("OP") rankings file covers QB/RB/WR/TE only. `DEF` is a required starter. Needs both an ordering *and* projected points — low variance, so a rough source suffices. | Complete board, VORP for DEF | Jacob |
| BLK-3 | **Draft slot unknown.** Sleeper's `draft_order` is not yet populated for draft `1385689586394488832`. | Next-pick math uses a placeholder until set | Sleeper |

### BLK-1 detail — what was pulled, and what is still missing

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

**Usable today, without the re-pull:** `RK` gives a superflex consensus ordering, `TIERS` and
`BYE` are complete (0 missing across all 768 rows), and `POS` carries positional rank. **Bye weeks
can be imported from this file now** — that closes the LEG-4 gap independently of the ADP problem.

**Watch out — this export drops DST and K.** Positions present are QB (63), RB (242), WR (294),
TE (169) only. The superseded 1QB "ALL" export *did* include 32 DST and 29 K rows. **DEF is a
required starter**, so keep a DST-bearing export alongside this one rather than replacing it. See
BLK-2.

---

## Open

| ID | Issue | Severity | Notes |
| --- | --- | --- | --- |
| OPEN-1 | **FantasyPros→Sleeper name matching is unsolved.** Suffixes (`Patrick Mahomes II`), DST naming (`San Francisco 49ers` vs `SF`), and in-season trades will all mismatch. | **High** | A silent mismatch means a drafted player never gets marked. Must fail loudly at import, never at draft time. Plan: match on Sleeper's `search_full_name` + a committed manual override list. |
| OPEN-2 | **Draft-day rehearsal not scheduled.** A full mock draft end-to-end is the only real test of Sleeper polling. | **High** | Must happen with days of margin before 2026-08-28, not the night before. |
| OPEN-3 | ADP moves through August; a stale export produces wrong survival estimates. | Medium | Import must be re-runnable. Re-pull within a few days of the draft. |
| OPEN-4 | No decision on how manual pick entry and Sleeper auto-sync reconcile when they disagree. | Medium | Needs an answer before Phase 3. Last-write-wins is probably wrong. |

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
| BLK-8 | `npm install` failed with `EBADF` on the Google Drive path | 2026-07-31 | **Repo relocated to `C:\Projects\PopActaDraftApp`.** `npm install` there succeeds — 184 packages, exit 0, ~27s. The Drive sync layer was the entire cause; nothing in the repo needed changing. `web/` is scaffolded and CI is green. |
