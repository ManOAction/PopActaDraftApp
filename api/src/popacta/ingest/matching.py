"""Resolving FantasyPros names to Sleeper player ids.

Tracked as OPEN-1, and measured before being specified.

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

Regenerating the test fixture
-----------------------------

Tests run against `api/tests/fixtures/sleeper_players_subset.json`, never the network and
never the 14 MB live dump — CI is offline and a live dump would make the measured counts
non-deterministic. The subset is built by this rule:

    keep a Sleeper row if
        normalize_name(row["full_name"]) matches any name in the two FantasyPros
            exports (this pulls in *every* same-key row, so the ambiguity the tie-break
            ladder exists to resolve survives into the fixture), or
        row["position"] == "DEF"   (all 32; they carry no "full_name" key at all), or
        row["player_id"] is a MANUAL_OVERRIDES target
    then keep only the keys this module reads, intersected with the keys actually
        present on that row — so a DEF row keeps its *missing* "full_name" key.

`api/tests/ingest/test_matching.py` carries a runnable `_regenerate_fixture()` under its
`__main__` guard; point it at a fresh dump from `https://api.sleeper.app/v1/players/nfl`.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from popacta.domain.errors import ImportDataError

__all__ = ["MANUAL_OVERRIDES", "normalize_name", "resolve_players"]

MANUAL_OVERRIDES: Mapping[str, str | None] = {
    # Nicknames. No edit-distance metric reaches these, which is why fuzzy matching is
    # not the answer to them.
    "Hollywood Brown": "5848",  # Sleeper: Marquise Brown, WR PHI
    "Bam Knight": "8122",  # Sleeper: Zonovan Knight, RB ARI
    "Chip Trayanum": "13438",  # Sleeper: DeaMonte Trayanum, RB NYJ
    # Absent from Sleeper entirely. All free agents, all ranked 352 or worse.
    "Tommy Myers": None,  # rankings RK 352, TE, FA
    "Graig Cooper": None,  # rankings RK 633, RB, FA
    "Omarius Hines": None,  # rankings RK 649, WR, FA
    "Dale Moss": None,  # rankings RK 676, WR, FA
    "Mazeo Bennett": None,  # rankings RK 767, WR, FA
}
"""FantasyPros name -> Sleeper `player_id`, or `None` to drop the player deliberately.

**Pin the id, never a name** — names drift. `None` entries exist so the import proves it
saw a player and dropped him on purpose, rather than losing him silently.

Known members: the three nicknames above, plus five players absent from Sleeper entirely.
All are ranked 254 or worse, so none affects a real pick. Budget 2-5 additions after the
pre-draft re-pull (OPEN-3) as August roster churn lands.
"""

_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})

_TEAM_ALIASES: Mapping[str, str] = {"JAC": "JAX"}
"""FantasyPros team code -> Sleeper team code.

Measured: `JAC` is the only real divergence (37 rows across both exports). `FA` is not an
alias — it means *no team*, and is handled by `_normalize_team` returning `None`.
"""

_DEFENSE = "DEF"

_FIXTURE_FIELDS = (
    "player_id",
    "full_name",
    "first_name",
    "last_name",
    "search_full_name",
    "team",
    "position",
    "fantasy_positions",
    "active",
    "search_rank",
)
"""Every Sleeper field this module reads. The trimmed test fixture carries exactly these."""


def normalize_name(name: str) -> str:
    """Reduce a name to its match key. Applied identically to both sides.

    In order: NFKD-normalize and drop combining marks; lowercase; replace every
    non-`[a-z0-9]` character with a space (handles `'`, `-`, `.` uniformly); **pop trailing
    tokens in `{jr, sr, ii, iii, iv, v}`** while more than one token remains; join with no
    separator.

    This reproduces Sleeper's `search_full_name` recipe plus suffix removal.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))
    spaced = re.sub(r"[^a-z0-9]", " ", folded.lower())
    tokens = spaced.split()
    while len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def _normalize_team(team: str | None) -> str | None:
    """Sleeper's team code for a FantasyPros team, or `None` for a free agent.

    FantasyPros writes `FA` where Sleeper writes `null`; both mean "no team", and neither
    is a value a comparison should ever match on.
    """
    if team is None:
        return None
    cleaned = team.strip().upper()
    if cleaned in ("", "FA"):
        return None
    return _TEAM_ALIASES.get(cleaned, cleaned)


def _search_rank(row: Mapping[str, Any]) -> float:
    """Sleeper's `search_rank`, with a missing value sorting last rather than first."""
    rank = row.get("search_rank")
    return float("inf") if rank is None else float(rank)


def _load_dump(sleeper_dump: Path) -> Mapping[str, Mapping[str, Any]]:
    """Read a Sleeper `/v1/players/nfl` payload (or a trimmed subset of one) from disk."""
    payload = json.loads(sleeper_dump.read_bytes())
    if not isinstance(payload, dict) or not payload:
        raise ImportDataError(
            f"Sleeper dump {str(sleeper_dump)!r} is not a non-empty object of player rows"
        )
    return payload


def _index_by_name(
    dump: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, str]]:
    """Split a Sleeper dump into a name index and a defense id index.

    Defenses are separated out **first and unconditionally**: all 32 `DEF` rows carry no
    `full_name` at all, so any name path over them raises `AttributeError`. Their
    `player_id` *is* the team abbreviation (`"SF"`), and `first_name`/`last_name` spell the
    club out (`"San Francisco"` / `"49ers"`), so both forms index cleanly by id.
    """
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    defenses: dict[str, str] = {}
    for player_id, row in dump.items():
        if row.get("position") == _DEFENSE:
            defenses[player_id.strip().upper()] = player_id
            spelled = normalize_name(f"{row.get('first_name') or ''} {row.get('last_name') or ''}")
            if spelled:
                defenses[spelled] = player_id
            continue
        full_name = row.get("full_name")
        if not full_name:
            continue
        by_name.setdefault(normalize_name(full_name), []).append(row)
    return by_name, defenses


def _tie_break(
    candidates: list[Mapping[str, Any]], team: str | None, position: str
) -> list[Mapping[str, Any]]:
    """Narrow same-name candidates, dropping any filter that would empty the set.

    Order is load-bearing and is spelled out in `resolve_players`. Each step is applied
    only while more than one candidate survives, and only if it leaves at least one.
    """
    surviving = candidates

    if len(surviving) > 1:
        matched = [
            row
            for row in surviving
            if row.get("position") == position or position in (row.get("fantasy_positions") or [])
        ]
        surviving = matched or surviving

    wanted_team = _normalize_team(team)
    if len(surviving) > 1 and wanted_team is not None:
        matched = [row for row in surviving if _normalize_team(row.get("team")) == wanted_team]
        surviving = matched or surviving

    if len(surviving) > 1:
        matched = [row for row in surviving if row.get("team")]
        surviving = matched or surviving

    if len(surviving) > 1:
        matched = [row for row in surviving if row.get("active")]
        surviving = matched or surviving

    if len(surviving) > 1:
        best = min(_search_rank(row) for row in surviving)
        matched = [row for row in surviving if _search_rank(row) == best]
        surviving = matched or surviving

    return surviving


def _describe(rows: Iterable[Mapping[str, Any]]) -> str:
    """One-line summary of candidate rows, for an exception message."""
    return ", ".join(
        f"{row.get('player_id')}={row.get('full_name')!r}"
        f" ({row.get('position')}/{row.get('team')}, active={row.get('active')},"
        f" search_rank={row.get('search_rank')})"
        for row in rows
    )


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
    leave 0 ambiguous on both files. **Corrected 2026-08-01:** stopping at *position*
    leaves 3 on the rankings and 2 on the projections, not 1 — 1 is what
    *position -> team* leaves. The earlier wording conflated two rows of the ablation
    table. The three survivors of a position-only ladder are `Frank Gore Jr.`,
    `Kyle Williams` and `Tyler Davis`.

    > **Team must be a tie-break, never a match requirement.** 12 real players have a stale
    > FantasyPros team (released since), and requiring team would drop all of them.
    > Alias `JAC -> JAX` (21 rows); treat FantasyPros `FA` as `None`.

    > **Suffix-stripping can merge two different real people.** `Frank Gore Jr.` (RB, BUF)
    > collides with **his own father**, still `active` in Sleeper. Position does not
    > separate them — team does. This is the silent-wrong-player case OPEN-1 warns about,
    > and it is why the ladder must never stop at position.

    Names in `MANUAL_OVERRIDES` bypass the name path entirely: an id is used as given (and
    is checked against the dump, so a pin that goes stale fails here rather than at the
    draft), and a `None` drops the player deliberately, leaving him out of the result.

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
    dump = _load_dump(sleeper_dump)
    by_name, defenses = _index_by_name(dump)

    resolved: dict[str, str] = {}
    unmatched: list[str] = []
    ambiguous: list[str] = []

    for name, (team, position) in fantasypros_names.items():
        # DEF first, by id — before anything can touch a null full_name.
        if position == _DEFENSE:
            for key in (_normalize_team(team), normalize_name(name), name.strip().upper()):
                if key is not None and key in defenses:
                    resolved[name] = defenses[key]
                    break
            else:
                unmatched.append(f"{name!r} (DEF, team={team!r}) — no Sleeper defense with that id")
            continue

        if name in MANUAL_OVERRIDES:
            override = MANUAL_OVERRIDES[name]
            if override is None:
                continue
            if override not in dump:
                raise ImportDataError(
                    f"MANUAL_OVERRIDES pins {name!r} to Sleeper id {override!r}, which is not in "
                    f"{str(sleeper_dump)!r} — the override is stale, re-derive it"
                )
            resolved[name] = override
            continue

        candidates = by_name.get(normalize_name(name), [])
        if not candidates:
            unmatched.append(f"{name!r} ({position}, team={team!r})")
            continue

        surviving = _tie_break(candidates, team, position)
        if len(surviving) > 1:
            ambiguous.append(f"{name!r} ({position}, team={team!r}) -> {_describe(surviving)}")
            continue

        player_id = surviving[0].get("player_id")
        if not isinstance(player_id, str) or not player_id:
            raise ImportDataError(
                f"Sleeper row matching {name!r} carries no usable player_id: {surviving[0]!r}"
            )
        resolved[name] = player_id

    if unmatched:
        raise ImportDataError(
            f"{len(unmatched)} FantasyPros name(s) matched no Sleeper player and are not in "
            f"MANUAL_OVERRIDES: {'; '.join(sorted(unmatched))}"
        )
    if ambiguous:
        raise ImportDataError(
            f"{len(ambiguous)} FantasyPros name(s) still ambiguous after the full tie-break "
            f"ladder — refusing to guess: {'; '.join(sorted(ambiguous))}"
        )

    claimed: dict[str, str] = {}
    collisions: list[str] = []
    for name, player_id in resolved.items():
        if player_id in claimed:
            collisions.append(f"{claimed[player_id]!r} and {name!r} both resolve to {player_id!r}")
        else:
            claimed[player_id] = name
    if collisions:
        raise ImportDataError(
            f"{len(collisions)} Sleeper id(s) claimed by more than one FantasyPros name — one "
            f"player's board entry would mask another's: {'; '.join(sorted(collisions))}"
        )

    return resolved
