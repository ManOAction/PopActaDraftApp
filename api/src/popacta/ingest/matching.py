"""Resolving FantasyPros names to Sleeper player ids.

SIGNATURES ONLY — wave 1. Tracked as OPEN-1, and measured before being specified.

On draft night Sleeper reports picks by **player id**; our projections are keyed by name
and team. A silent mismatch means a player another team drafted stays on our board as
available, and the app recommends someone already gone.

**Measured on a live Sleeper dump (12,204 rows) against both source files:**

    760 / 768 rankings rows resolve  (98.96%)   0 fuzzy matches needed
    516 / 518 projections rows       (99.6%)    0 ambiguous after tie-break
    injective: 0 collisions

Four manual aliases are required; eight entries to be safe.

**Suffixes are 100% of the normalization work** (9.2% of rows). Sleeper strips them
essentially universally, FantasyPros keeps them, so the rule is one-directional. Inside
the top 100: `James Cook III` (23), `Patrick Mahomes II` (24), `Kenneth Walker III` (39).

**Punctuation, initials and accents are complete non-issues** — `Ja'Marr`, `Amon-Ra`,
`A.J.`, `DK` all resolve unchanged, because Sleeper's own normalization strips the same
characters. Verified: `search_full_name == normalize(full_name)` for all 12,204 rows, 0
exceptions.

**Do not build fuzzy matching.** Zero fuzzy hits at any sane cutoff. The real residual
failures are nicknames — `Hollywood Brown` -> `Marquise Brown`, `Bam Knight` ->
`Zonovan Knight` — which no edit-distance metric reaches. Fuzzy matching buys nothing here
and only adds a way to be silently wrong.
"""

from collections.abc import Mapping
from pathlib import Path

__all__ = ["MANUAL_OVERRIDES", "normalize_name", "resolve_players"]

MANUAL_OVERRIDES: Mapping[str, str | None] = {}
"""FantasyPros name -> Sleeper `player_id`, or `None` to drop the player deliberately.

**Pin the id, never a name** — names drift. `None` entries exist so the import proves it
saw a player and dropped him on purpose, rather than losing him silently.

Known members: the three nicknames above, plus four players absent from Sleeper entirely.
All are ranked 254 or worse, so none affects a real pick. Budget 2-5 additions after the
pre-draft re-pull (OPEN-3) as August roster churn lands.
"""


def normalize_name(name: str) -> str:
    """Reduce a name to its match key. Applied identically to both sides.

    In order: NFKD-normalize and drop combining marks; lowercase; replace every
    non-`[a-z0-9]` character with a space (handles `'`, `-`, `.` uniformly); **pop trailing
    tokens in `{jr, sr, ii, iii, iv, v}`** while more than one token remains; join with no
    separator.

    This reproduces Sleeper's `search_full_name` recipe plus suffix removal.
    """
    raise NotImplementedError


def resolve_players(
    fantasypros_names: Mapping[str, tuple[str | None, str]],
    sleeper_dump: Path,
) -> Mapping[str, str]:
    """Resolve `{fantasypros_name: (team, position)}` to `{fantasypros_name: sleeper_id}`.

    Index Sleeper on **`full_name`**, not `search_full_name` — the latter is `null` for all
    32 `DEF` rows.

    **Tie-break strictly in this order**, dropping any filter that would empty the set:
    position (accept `position` or membership in `fantasy_positions`) -> team (skip when
    FantasyPros says `FA`) -> has-a-team -> `active` -> lowest `search_rank`. Measured to
    leave 0 ambiguous on both files; stopping at position leaves 1.

    > **Team must be a tie-break, never a match requirement.** 12 real players have a stale
    > FantasyPros team (released since), and requiring team would drop all of them.
    > Alias `JAC -> JAX` (21 rows); treat FantasyPros `FA` as `None`.

    > **Suffix-stripping can merge two different real people.** `Frank Gore Jr.` (RB, BUF)
    > collides with **his own father**, still `active` in Sleeper. Position does not
    > separate them — team does. This is the silent-wrong-player case OPEN-1 warns about,
    > and it is why the ladder must never stop at position.

    Raises:
        ImportDataError: any name with **zero** candidates (expect exactly the
            `MANUAL_OVERRIDES` set — an unexpected member means Sleeper's dump changed);
            any name still **ambiguous** after the full ladder (expect 0 — this is the
            wrong-player-silently case); or **two names resolving to one id** (expect 0 —
            one player's board entry would be masking another's).

    Note:
        `DEF` picks must be handled **by id, before any name path**. All 32 Sleeper `DEF`
        rows have `full_name: null`, so `players[pid]["full_name"].lower()` raises
        `AttributeError` mid-draft. Their `player_id` *is* the team abbreviation (`"SF"`).
        We never rank them, but ~10 of 160 live picks will be defenses.
    """
    raise NotImplementedError
