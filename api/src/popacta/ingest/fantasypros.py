"""Parsing the FantasyPros CSV exports.

**Read `docs/reference_fantasypros_exports.md` before writing a line of this.** Every
trap below is documented and verified there; several would produce wrong numbers rather
than a crash.

Three files, three different shapes:

1. **Projections** (`QB.csv`, `FLX.csv`) — raw stats. Their union is the complete
   518-player set, so parsing just those two is sufficient and halves the surface.
2. **Rankings** (`..._OP_Rankings.csv`) — consensus rank, tiers, bye weeks.
3. **ADP** (`..._Superflex_ADP_Rankings.csv`) — superflex ADP from real drafts.
"""

import csv
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final

from popacta.domain.errors import ImportDataError
from popacta.domain.players import AdpEstimate
from popacta.domain.positions import Position

__all__ = [
    "AdpRow",
    "RawProjection",
    "RawRanking",
    "parse_adp",
    "parse_adp_rows",
    "parse_projections",
    "parse_rankings",
]

# --------------------------------------------------------------------------------------
# Shared literals
# --------------------------------------------------------------------------------------

EM_DASH: Final[str] = "—"
"""How the **ADP** export writes a missing value — U+2014, not `'-'` and not empty.

The file is valid UTF-8. A Windows console renders this as `?` because the console is
cp1252; that is a display artefact and not a reason to "fix" the file's encoding.
"""

MISSING_BYE: Final[str] = "-"
"""How the **rankings** export writes a missing bye week — an ASCII hyphen, not `EM_DASH`.

Two files, two different missing-value markers. Testing for the wrong one either raises on
good data or, worse, treats a marker as data.
"""

FREE_AGENT_TEAM: Final[str] = "FA"
"""FantasyPros' team code for an unrostered player. Normalised to `None`."""

DRAFTABLE_PICKS: Final[int] = 160
"""The pick window this app actually has to be right about — `teams x rounds` (12 x 16).

Pinned here rather than read from `LeagueConfig` because the parse functions take a path
and nothing else. It is used **only** to decide whether a missing bye week is fatal, and
the margin is wide: every missing bye in the pinned export sits at `RK 200` or worse. If
the league's shape ever changes, this is the one number to revisit.
"""

_POSITION_RANK_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z]+)(\d+)$")
_NAME_SPLIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s{2,}")
_ADP_TEAM_BYE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([A-Z]{2,4})\s*\((\d+)\)$")

_MIN_BYE_WEEK: Final[int] = 1
_MAX_BYE_WEEK: Final[int] = 18
"""A bye of `0` is the LEG-4 signature exactly — 527 players shown as "Bye: 0" for a
season because a parse failure was defaulted instead of raised. Reject it here."""

# --------------------------------------------------------------------------------------
# Projections: verified column layouts, keyed by (file, column index)
# --------------------------------------------------------------------------------------

PLAYER_COLUMN: Final[str] = "player"
TEAM_COLUMN: Final[str] = "team"
POSITION_COLUMN: Final[str] = "pos"
POINTS_COLUMN: Final[str] = "fpts"

_NON_STAT_COLUMNS: Final[frozenset[str]] = frozenset(
    {PLAYER_COLUMN, TEAM_COLUMN, POSITION_COLUMN, POINTS_COLUMN}
)

UNSCORED_STATS: Final[frozenset[str]] = frozenset({"pass_att", "pass_cmp", "rush_att"})
"""Volume columns this league's `scoring_settings` has no rule for.

Sleeper's payload carries no `pass_att`, `pass_cmp` or `rush_att` key, because they are
worth nothing in this league. `scoring.fantasy_points` raises on any stat it cannot score
— deliberately — so these are dropped **here**, once, as a named decision rather than
absorbed by a `.get(key, 0)` at scoring time. They are parsed and range-checked first, so
a malformed attempts column still fails the import.
"""

QB_COLUMNS: Final[tuple[str, ...]] = (
    PLAYER_COLUMN,
    TEAM_COLUMN,
    "pass_att",
    "pass_cmp",
    "pass_yd",
    "pass_td",
    "pass_int",
    "rush_att",
    "rush_yd",
    "rush_td",
    "fum_lost",
    POINTS_COLUMN,
)
"""`QB.csv`, positionally. Header reads `Player,Team,ATT,CMP,YDS,TDS,INTS,ATT,YDS,TDS,FL,FPTS`."""

FLX_COLUMNS: Final[tuple[str, ...]] = (
    PLAYER_COLUMN,
    TEAM_COLUMN,
    POSITION_COLUMN,
    "rush_att",
    "rush_yd",
    "rush_td",
    "rec",
    "rec_yd",
    "rec_td",
    "fum_lost",
    POINTS_COLUMN,
)
"""`FLX.csv`, positionally — **rushing first, receiving second**.

`WR.csv` orders them the other way round under the *same* header names (`YDS` and `TDS`
each appear twice in both files). Keying on header name therefore swaps rushing and
receiving for every WR in this file, silently. That is the whole reason these tuples
exist. See `docs/reference_fantasypros_exports.md`.
"""

# --------------------------------------------------------------------------------------
# Rankings and ADP: column *counts* and indices
# --------------------------------------------------------------------------------------

_RANKING_COLUMN_COUNT: Final[int] = 12
_RK, _TIERS, _RANK_NAME, _RANK_TEAM, _RANK_POS, _RANK_BYE = 0, 1, 2, 3, 4, 5

_ADP_COLUMN_COUNT: Final[int] = 7
_OP, _OVERALL, _ADP_PLAYER, _SLEEPER, _FFPC, _AVG, _REAL_TIME = 0, 1, 2, 3, 4, 5, 6
"""`_OP` is the **superflex** rank; `_OVERALL` is the 1QB rank sitting right beside it.

Josh Allen is `OP` 1 and `Overall` 22. Neither column is labelled "superflex". Reading
`_OVERALL` reintroduces the bug this project has now guarded against three times.
"""

SUPERFLEX_FIRST_QB_MAX_RANK: Final[int] = 5
"""In a superflex rankings export QBs occupy overall 1-6; in the 1QB variant the first is
26. If the first QB is not inside the top 5, the file is not a superflex export."""

_SUPERFLEX_TOP_N: Final[int] = 24
_SUPERFLEX_MIN_DISPLACED: Final[int] = 8
_SUPERFLEX_MIN_DISPLACEMENT: Final[int] = 20
"""The ADP export's position-free superflex signature.

The ADP file carries **no position column**, so the QB count cannot be taken from it
directly. What it does carry is both ranks at once, and superflex lifts QBs far above
their 1QB rank: all 8 QBs in the top 24 of `OP` are 21-61 places better than their
`Overall`, while no non-QB in that window moves 20. In a 1QB export the two orderings
agree and this count collapses to zero, which is exactly the file we must refuse.

The exact QB counts quoted in `docs/plan_phase2_decision_engine.md` (8 in the top 24, 32
in the top 160) are verified in the tests, which join this file to the rankings export for
positions. The check *inside* the parser cannot do that join and does not pretend to.
"""

_ADP_SOURCE_TOLERANCE: Final[float] = 0.051
"""`AVG` is published to one decimal, so the mean of two integer sources can differ by up
to 0.05 from it legitimately."""

STANDARD_DEVIATION_SOURCE: Final[Mapping[str, float] | None] = None
"""FantasyPros name -> standard deviation of draft position. `None` until BLK-1 lands.

**This is the seam, and it is deliberately empty.** No FantasyPros export we have carries
`Std Dev`: not the projections files, not either rankings variant, not the ADP page. The
remaining candidate is the ECR rankings variant with `Best / Worst / Avg / Std Dev`.

Until one arrives, `parse_adp` raises. It does **not** model `sd = f(adp)` — that means
choosing a dispersion coefficient with no data behind it, which is precisely how LEG-1 and
LEG-5 happened. Point this at a real source and `parse_adp` starts returning estimates
with no other change.
"""


@dataclass(frozen=True, slots=True)
class RawProjection:
    """One player's raw stat line, straight from the CSV — before scoring is applied.

    Deliberately *not* carrying `FPTS`. Points are recomputed from these stats using the
    league's own scoring settings (`domain.scoring`), so a mid-August scoring change by the
    commissioner is a non-event rather than a silent wrong-number bug.
    """

    name: str
    team: str | None
    position: str
    stats: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawRanking:
    """One row of the consensus rankings export."""

    name: str
    team: str | None
    position: str
    overall_rank: int
    positional_rank: int
    tier: int
    bye_week: int | None


@dataclass(frozen=True, slots=True)
class AdpRow:
    """One parsed row of the ADP export, before any dispersion is attached.

    Everything on this row is real, verified data. It is *not* an `AdpEstimate`: that type
    requires `sd > 0` and this export has no `Std Dev` column (BLK-1). Keeping the parsed
    values in their own type is what makes wiring in a dispersion source a small change
    rather than a rewrite.
    """

    superflex_rank: int
    one_qb_rank: int | None
    name: str
    team: str | None
    bye_week: int | None
    sleeper: float | None
    ffpc: float | None
    average: float
    real_time: float | None


def parse_projections(qb_csv: Path, flx_csv: Path) -> Sequence[RawProjection]:
    """Parse raw stat lines from the projections exports.

    > **Key on `(file, column index)`, NEVER on header name.** Headers repeat — `YDS` and
    > `TDS` each appear twice — *and the order differs between files*. `WR.csv` lists
    > receiving first, `FLX.csv` lists rushing first. A name-keyed parser silently swaps
    > rushing and receiving for every WR in `FLX.csv`. It does not crash. It just produces
    > wrong projections. **Write the test that catches exactly that.**

    Verified layouts are tabulated in the reference doc.

    Other traps: row 2 of every projections file is a junk spacer (skip rows whose first
    field is blank); numeric fields carry thousands separators inside quotes (`"1,381.0"`);
    read with `utf-8-sig`.

    Raises:
        ImportDataError: the column count for a file does not match its verified layout —
            check the shape, do not trust the header. Also raised if two rows share a
            name: downstream Sleeper matching is keyed by FantasyPros name, so a duplicate
            would mask one player behind another rather than fail.
    """
    projections: list[RawProjection] = [
        *_parse_projection_file(qb_csv, QB_COLUMNS, fixed_position=Position.QB),
        *_parse_projection_file(flx_csv, FLX_COLUMNS, fixed_position=None),
    ]

    seen: dict[str, str] = {}
    for projection in projections:
        previous = seen.get(projection.name)
        if previous is not None:
            raise ImportDataError(
                f"{projection.name!r} appears twice in the projections "
                f"({previous}, then {projection.position}); Sleeper matching is keyed by "
                "FantasyPros name, so one entry would silently mask the other"
            )
        seen[projection.name] = projection.position

    return tuple(projections)


def parse_rankings(csv_path: Path) -> Sequence[RawRanking]:
    """Parse the superflex consensus rankings export: `RK`, `TIERS`, `BYE`, positional rank.

    Traps: `BYE` is the literal `'-'` on 125 rows from `RK 200` (free agents), so
    `int(row["BYE"])` raises there. That is correct behaviour — but only reject it for a
    player *inside* the draftable window; outside it, "unrostered, no bye" is the truth.
    This file has **no** junk spacer row (that belongs to the projections exports).

    Raises:
        ImportDataError: a bye week is unparseable for a player inside the draftable
            window. LEG-4 defaulted these to `0` and shipped "Bye: 0" for 527 players.
        ImportDataError: the file is not a superflex export — its first QB must sit inside
            the top `SUPERFLEX_FIRST_QB_MAX_RANK` overall. The 1QB variant puts him at 26
            and makes every QB decision wrong in the same direction.
    """
    rankings: list[RawRanking] = []

    for line_no, row in _read_rows(csv_path, _RANKING_COLUMN_COUNT, skip_blank_first_field=False):
        name = row[_RANK_NAME].strip()
        if not name:
            raise ImportDataError(f"{csv_path.name} line {line_no}: empty player name in {row!r}")

        overall_rank = _to_int(row[_RK], path=csv_path, line_no=line_no, column="RK")
        tier = _to_int(row[_TIERS], path=csv_path, line_no=line_no, column="TIERS")
        position, positional_rank = _split_positional_rank(
            row[_RANK_POS], path=csv_path, line_no=line_no
        )

        raw_bye = row[_RANK_BYE].strip()
        if raw_bye == MISSING_BYE:
            if overall_rank <= DRAFTABLE_PICKS:
                raise ImportDataError(
                    f"{csv_path.name} line {line_no}: {name!r} is RK {overall_rank}, inside the "
                    f"{DRAFTABLE_PICKS}-pick draftable window, but has no bye week "
                    f"({raw_bye!r}); a drafted player without a bye is a data defect"
                )
            bye_week = None
        else:
            bye_week = _to_int(raw_bye, path=csv_path, line_no=line_no, column="BYE")
            if not _MIN_BYE_WEEK <= bye_week <= _MAX_BYE_WEEK:
                raise ImportDataError(
                    f"{csv_path.name} line {line_no}: {name!r} has bye week {bye_week}, outside "
                    f"{_MIN_BYE_WEEK}..{_MAX_BYE_WEEK}"
                )

        rankings.append(
            RawRanking(
                name=name,
                team=_normalise_team(row[_RANK_TEAM]),
                position=position.value,
                overall_rank=overall_rank,
                positional_rank=positional_rank,
                tier=tier,
                bye_week=bye_week,
            )
        )

    _assert_dense_ranks([ranking.overall_rank for ranking in rankings], path=csv_path, column="RK")
    _assert_superflex_rankings(rankings, path=csv_path)
    return tuple(rankings)


def parse_adp(csv_path: Path) -> Mapping[str, AdpEstimate]:
    """Parse superflex ADP. Returns a mapping keyed by the raw FantasyPros name.

    > **Trap: `Overall` is the 1QB rank, sitting directly beside the superflex `OP` rank.**
    > Josh Allen is `OP` 1 and `Overall` 22. Both columns, same file, adjacent, neither
    > labelled "superflex". Reading the wrong one silently reintroduces the bug this
    > project has guarded against three times. **Key on `OP`.**

    Further verified facts:

    - Missing values are an **em dash `—` (U+2014)**, not `'-'` and not empty. The file is
      valid UTF-8; the console renders it as `?` because it is cp1252.
    - `Player (Bye)` is composite: `'Josh Allen   BUF (7)'`. Split on a **2-or-more-space
      run**, not a single space.
    - **Three rows carry a name only** (`Stefon Diggs`, `Tyreek Hill`, `Joe Mixon` — free
      agents). Accept a name-only field rather than raising.
    - `AVG == mean(Sleeper, FFPC)`, **excluding** `Real-Time`. Verified on all 278 rows.

    **This export carries no `Std Dev`** (BLK-1). Until a source arrives, `AdpEstimate`
    cannot be constructed and this function must raise rather than invent a dispersion —
    modelling `sd = f(adp)` means choosing a coefficient with no data behind it, which is
    how LEG-1 and LEG-5 happened.

    Raises:
        ImportDataError: no `Std Dev` source is configured; or the integrity check fails —
            **assert the top of `OP` is QB-heavy** (expected: 8 QBs in the top 24, 32 in
            the top 160). A file that is secretly 1QB must not load.
    """
    rows = parse_adp_rows(csv_path)

    if STANDARD_DEVIATION_SOURCE is None:
        raise ImportDataError(
            f"{csv_path.name} parsed cleanly ({len(rows)} rows, ADP "
            f"{rows[0].average}..{rows[-1].average}) but carries no 'Std Dev' column, so "
            "AdpEstimate cannot be built (BLK-1). Refusing to model sd = f(adp): choosing "
            "that coefficient with no data behind it is how LEG-1 and LEG-5 happened. "
            "Point fantasypros.STANDARD_DEVIATION_SOURCE at a real dispersion export."
        )

    estimates: dict[str, AdpEstimate] = {}
    for row in rows:
        sd = STANDARD_DEVIATION_SOURCE.get(row.name)
        if sd is None:
            raise ImportDataError(
                f"no ADP standard deviation for {row.name!r} (OP {row.superflex_rank}, "
                f"AVG {row.average}); the dispersion source does not cover this export"
            )
        estimates[row.name] = AdpEstimate(adp=row.average, sd=sd)
    return MappingProxyType(estimates)


def parse_adp_rows(csv_path: Path) -> Sequence[AdpRow]:
    """Parse and validate the ADP export's own values — everything except dispersion.

    Split out from `parse_adp` on purpose: the ADP numbers in this file are real and
    correct, and only the missing `Std Dev` blocks building an `AdpEstimate`. This is the
    part that keeps working when BLK-1 is resolved.

    Raises:
        ImportDataError: the column count is wrong; `OP` is not a dense 1..n sequence;
            `AVG` is missing on any row; `AVG` is not the mean of the present
            `Sleeper`/`FFPC` sources; ADP is not on the same scale as pick numbers; or the
            file fails the superflex signature check.
    """
    rows: list[AdpRow] = []

    for line_no, row in _read_rows(csv_path, _ADP_COLUMN_COUNT, skip_blank_first_field=False):
        name, team, bye_week = _split_adp_player(row[_ADP_PLAYER], path=csv_path, line_no=line_no)
        average = _to_float(row[_AVG], path=csv_path, line_no=line_no, column="AVG")
        if average <= 0:
            raise ImportDataError(
                f"{csv_path.name} line {line_no}: {name!r} has AVG {average}, which is not a "
                "usable draft position"
            )

        sleeper = _optional_float(row[_SLEEPER], path=csv_path, line_no=line_no, column="Sleeper")
        ffpc = _optional_float(row[_FFPC], path=csv_path, line_no=line_no, column="FFPC")
        sources = [value for value in (sleeper, ffpc) if value is not None]
        if not sources:
            raise ImportDataError(
                f"{csv_path.name} line {line_no}: {name!r} has AVG {average} but neither a "
                "Sleeper nor an FFPC source; the average is unsupported"
            )
        # Trap 5: AVG excludes Real-Time. Asserting it is the cheapest way to notice a
        # re-pull that quietly changed which sources are folded into the average.
        expected = sum(sources) / len(sources)
        if abs(average - expected) > _ADP_SOURCE_TOLERANCE:
            raise ImportDataError(
                f"{csv_path.name} line {line_no}: {name!r} has AVG {average} but "
                f"mean(Sleeper={sleeper}, FFPC={ffpc}) is {expected:.3f}; AVG is documented to "
                "be the mean of those two and to exclude Real-Time"
            )

        rows.append(
            AdpRow(
                superflex_rank=_to_int(row[_OP], path=csv_path, line_no=line_no, column="OP"),
                one_qb_rank=_optional_int(
                    row[_OVERALL], path=csv_path, line_no=line_no, column="Overall"
                ),
                name=name,
                team=team,
                bye_week=bye_week,
                sleeper=sleeper,
                ffpc=ffpc,
                average=average,
                real_time=_optional_float(
                    row[_REAL_TIME], path=csv_path, line_no=line_no, column="Real-Time"
                ),
            )
        )

    _assert_dense_ranks([row.superflex_rank for row in rows], path=csv_path, column="OP")
    _assert_adp_scale(rows, path=csv_path)
    _assert_superflex_adp(rows, path=csv_path)
    return tuple(rows)


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------


def _read_rows(
    path: Path, column_count: int, *, skip_blank_first_field: bool
) -> Sequence[tuple[int, list[str]]]:
    """Read a FantasyPros CSV into `(line number, fields)` pairs, shape-checked.

    `utf-8-sig` because every one of these files may carry a BOM. The header is validated
    on **width only** — the names repeat and cannot be trusted, which is the entire point
    of the positional layouts above.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:  # pragma: no cover - environment failure, not a data defect
        raise ImportDataError(f"could not read {path}: {exc}") from exc

    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        raise ImportDataError(f"{path.name} is empty")

    header = all_rows[0]
    if len(header) != column_count:
        raise ImportDataError(
            f"{path.name} has {len(header)} columns, expected {column_count}; the verified "
            f"layout no longer matches this export. Header: {header!r}"
        )

    rows: list[tuple[int, list[str]]] = []
    for line_no, row in enumerate(all_rows[1:], start=2):
        if not row:
            continue
        # The projections exports carry a junk spacer at row 2 (`" ","","",""`) and two
        # empty trailing rows. Every one of them has a blank first field.
        if skip_blank_first_field and not row[0].strip():
            continue
        if len(row) != column_count:
            raise ImportDataError(
                f"{path.name} line {line_no} has {len(row)} fields, expected {column_count}: "
                f"{row!r}"
            )
        rows.append((line_no, row))

    if not rows:
        raise ImportDataError(f"{path.name} contains a header but no data rows")
    return tuple(rows)


def _to_float(value: str, *, path: Path, line_no: int, column: str) -> float:
    """Parse a numeric cell. Thousands separators live inside the quotes: `"1,381.0"`."""
    text = value.strip().replace(",", "")
    if not text:
        raise ImportDataError(f"{path.name} line {line_no}: column {column!r} is empty")
    try:
        return float(text)
    except ValueError as exc:
        raise ImportDataError(
            f"{path.name} line {line_no}: column {column!r} is not a number: {value!r}"
        ) from exc


def _to_int(value: str, *, path: Path, line_no: int, column: str) -> int:
    text = value.strip().replace(",", "")
    if not text:
        raise ImportDataError(f"{path.name} line {line_no}: column {column!r} is empty")
    try:
        return int(text)
    except ValueError as exc:
        raise ImportDataError(
            f"{path.name} line {line_no}: column {column!r} is not an integer: {value!r}"
        ) from exc


def _optional_float(value: str, *, path: Path, line_no: int, column: str) -> float | None:
    """Same as `_to_float`, but the ADP export's em-dash marker means "absent"."""
    if value.strip() == EM_DASH:
        return None
    return _to_float(value, path=path, line_no=line_no, column=column)


def _optional_int(value: str, *, path: Path, line_no: int, column: str) -> int | None:
    if value.strip() == EM_DASH:
        return None
    return _to_int(value, path=path, line_no=line_no, column=column)


def _normalise_team(value: str) -> str | None:
    """FantasyPros writes an unrostered player's team as `FA`; the domain uses `None`."""
    team = value.strip()
    if not team or team == FREE_AGENT_TEAM:
        return None
    return team


def _split_positional_rank(value: str, *, path: Path, line_no: int) -> tuple[Position, int]:
    """`'RB1'` -> `(Position.RB, 1)`. Used by both the rankings `POS` and the `FLX` `POS`."""
    match = _POSITION_RANK_PATTERN.match(value.strip())
    if match is None:
        raise ImportDataError(
            f"{path.name} line {line_no}: POS {value!r} is not a position plus a positional rank"
        )
    try:
        position = Position(match.group(1).upper())
    except ValueError as exc:
        raise ImportDataError(
            f"{path.name} line {line_no}: unknown position {match.group(1)!r} in POS {value!r}"
        ) from exc
    return position, int(match.group(2))


def _split_adp_player(
    value: str, *, path: Path, line_no: int
) -> tuple[str, str | None, int | None]:
    """`'Josh Allen   BUF (7)'` -> `('Josh Allen', 'BUF', 7)`.

    Split on a **2-or-more-space** run: single spaces are inside the name. Three rows in
    the pinned export carry a name only (free agents) and must parse, not raise.
    """
    parts = _NAME_SPLIT_PATTERN.split(value.strip())
    name = parts[0].strip()
    if not name:
        raise ImportDataError(f"{path.name} line {line_no}: empty player name in {value!r}")

    if len(parts) == 1:
        return name, None, None
    if len(parts) > 2:
        raise ImportDataError(
            f"{path.name} line {line_no}: 'Player (Bye)' split into {len(parts)} parts: {value!r}"
        )

    match = _ADP_TEAM_BYE_PATTERN.match(parts[1].strip())
    if match is None:
        raise ImportDataError(
            f"{path.name} line {line_no}: expected 'TEAM (bye)' after the name, got "
            f"{parts[1]!r} in {value!r}"
        )
    bye_week = int(match.group(2))
    if not _MIN_BYE_WEEK <= bye_week <= _MAX_BYE_WEEK:
        raise ImportDataError(
            f"{path.name} line {line_no}: {name!r} has bye week {bye_week}, outside "
            f"{_MIN_BYE_WEEK}..{_MAX_BYE_WEEK}"
        )
    return name, _normalise_team(match.group(1)), bye_week


def _parse_projection_file(
    path: Path, columns: Sequence[str], *, fixed_position: Position | None
) -> Sequence[RawProjection]:
    """Parse one projections file against its **verified positional layout**.

    `columns[i]` names what column `i` of *this file* holds. Nothing here reads the header
    row's names, because `YDS` and `TDS` each appear twice and mean different things in
    different files.
    """
    projections: list[RawProjection] = []

    for line_no, row in _read_rows(path, len(columns), skip_blank_first_field=True):
        cells = dict(zip(columns, row, strict=True))

        name = cells[PLAYER_COLUMN].strip()
        if not name:
            raise ImportDataError(f"{path.name} line {line_no}: empty player name in {row!r}")

        if fixed_position is not None:
            position = fixed_position
        else:
            position, _ = _split_positional_rank(cells[POSITION_COLUMN], path=path, line_no=line_no)

        stats: dict[str, float] = {}
        for column, raw in cells.items():
            if column in _NON_STAT_COLUMNS:
                continue
            value = _to_float(raw, path=path, line_no=line_no, column=column)
            if column in UNSCORED_STATS:
                # Parsed and validated, then dropped by name — see UNSCORED_STATS.
                continue
            stats[column] = value

        projections.append(
            RawProjection(
                name=name,
                team=_normalise_team(cells[TEAM_COLUMN]),
                position=position.value,
                stats=MappingProxyType(stats),
            )
        )

    return tuple(projections)


def _assert_dense_ranks(ranks: Sequence[int], *, path: Path, column: str) -> None:
    """`RK` and `OP` are both dense 1..n. A gap means rows were dropped or reordered."""
    expected = list(range(1, len(ranks) + 1))
    if list(ranks) != expected:
        mismatch = next(
            (i for i, (got, want) in enumerate(zip(ranks, expected, strict=True)) if got != want),
            None,
        )
        raise ImportDataError(
            f"{path.name}: {column} is not a dense 1..{len(ranks)} sequence; first mismatch at "
            f"position {mismatch}, got {ranks[mismatch] if mismatch is not None else None}"
        )


def _assert_superflex_rankings(rankings: Sequence[RawRanking], *, path: Path) -> None:
    """Reject the 1QB variant of the rankings export.

    The two files share a header and differ only in ordering, so nothing about the shape
    gives it away. In the superflex file QBs hold overall 1-6; in the 1QB file the first
    QB is rank 26, and feeding that into this league makes every QB decision wrong in the
    same direction.
    """
    first_qb = next(
        (ranking for ranking in rankings if ranking.position == Position.QB.value), None
    )
    if first_qb is None:
        raise ImportDataError(f"{path.name}: no QB in {len(rankings)} ranked rows")
    if first_qb.overall_rank > SUPERFLEX_FIRST_QB_MAX_RANK:
        raise ImportDataError(
            f"{path.name}: first QB is {first_qb.name!r} at RK {first_qb.overall_rank}, outside "
            f"the top {SUPERFLEX_FIRST_QB_MAX_RANK}; this is the 1QB export, not the superflex "
            "('OP') one. Re-export with the superflex setting."
        )


def _assert_adp_scale(rows: Sequence[AdpRow], *, path: Path) -> None:
    """ADP must be on the same scale as pick numbers.

    Verified on the pinned export: the top-`DRAFTABLE_PICKS` `AVG` values run 1.5 to
    164.0. An offence-only or half-size board would compress well below that.
    """
    window = [row for row in rows if row.superflex_rank <= DRAFTABLE_PICKS]
    if len(window) < DRAFTABLE_PICKS:
        raise ImportDataError(
            f"{path.name}: only {len(window)} rows inside the {DRAFTABLE_PICKS}-pick draftable "
            "window; the export does not cover the draft"
        )
    deepest = max(row.average for row in window)
    if not 0.5 * DRAFTABLE_PICKS <= deepest <= 1.5 * DRAFTABLE_PICKS:
        raise ImportDataError(
            f"{path.name}: the deepest ADP inside the top {DRAFTABLE_PICKS} is {deepest}, which "
            f"is not on the same scale as pick numbers; expected roughly {DRAFTABLE_PICKS}"
        )


def _assert_superflex_adp(rows: Sequence[AdpRow], *, path: Path) -> None:
    """Reject an ADP export that is secretly 1QB — see `_SUPERFLEX_MIN_DISPLACED`."""
    displaced = [
        row
        for row in rows
        if row.superflex_rank <= _SUPERFLEX_TOP_N
        and row.one_qb_rank is not None
        and row.one_qb_rank - row.superflex_rank >= _SUPERFLEX_MIN_DISPLACEMENT
    ]
    if len(displaced) < _SUPERFLEX_MIN_DISPLACED:
        raise ImportDataError(
            f"{path.name}: only {len(displaced)} of the top {_SUPERFLEX_TOP_N} 'OP' rows sit at "
            f"least {_SUPERFLEX_MIN_DISPLACEMENT} places better than their 1QB 'Overall' rank; "
            f"expected at least {_SUPERFLEX_MIN_DISPLACED} (the superflex QB lift). This does "
            "not look like a superflex ADP export."
        )
