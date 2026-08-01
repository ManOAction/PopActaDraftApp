"""Parsing the FantasyPros CSV exports.

SIGNATURES ONLY — wave 1.

**Read `docs/reference_fantasypros_exports.md` before writing a line of this.** Every
trap below is documented and verified there; several would produce wrong numbers rather
than a crash.

Three files, three different shapes:

1. **Projections** (`QB.csv`, `FLX.csv`) — raw stats. Their union is the complete
   518-player set, so parsing just those two is sufficient and halves the surface.
2. **Rankings** (`..._OP_Rankings.csv`) — consensus rank, tiers, bye weeks.
3. **ADP** (`..._Superflex_ADP_Rankings.csv`) — superflex ADP from real drafts.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from popacta.domain.players import AdpEstimate

__all__ = [
    "RawProjection",
    "RawRanking",
    "parse_adp",
    "parse_projections",
    "parse_rankings",
]


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
            check the shape, do not trust the header.
    """
    raise NotImplementedError


def parse_rankings(csv_path: Path) -> Sequence[RawRanking]:
    """Parse the superflex consensus rankings export: `RK`, `TIERS`, `BYE`, positional rank.

    Traps: `BYE` is the literal `'-'` on 125 rows from `RK 200` (free agents), so
    `int(row["BYE"])` raises there. That is correct behaviour — but only reject it for a
    player *inside* the draftable window; outside it, "unrostered, no bye" is the truth.
    This file has **no** junk spacer row (that belongs to the projections exports).

    Raises:
        ImportDataError: a bye week is unparseable for a player inside the draftable
            window. LEG-4 defaulted these to `0` and shipped "Bye: 0" for 527 players.
    """
    raise NotImplementedError


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
    raise NotImplementedError
