"""League configuration, derived from Sleeper — never hand-entered.

The 2025 app made the user type roster slots into a form as fixed per-position integer
columns, which could not express `SUPER_FLEX` at all (LEG-1). The settings were fudged
to `qb_slots=2, rb_slots=3, wr_slots=3, flex_slots=3` against a real roster of
`QB1 RB2 WR2 TE1 FLEX2 SUPER_FLEX1 DEF1`, and those numbers fed the VORP baseline
directly — so the engine solved a league that does not exist.

A slot here is a **set of eligible positions**. Sleeper's `roster_positions` already has
that shape; this module mirrors it rather than re-typing it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Self

from popacta.domain.errors import LeagueConfigError
from popacta.domain.positions import EXCLUDED_POSITIONS, Position

BENCH_SLOT: Final[str] = "BN"
SNAKE_DRAFT_TYPE: Final[str] = "snake"

SLOT_ELIGIBILITY: Final[Mapping[str, frozenset[Position]]] = {
    "QB": frozenset({Position.QB}),
    "RB": frozenset({Position.RB}),
    "WR": frozenset({Position.WR}),
    "TE": frozenset({Position.TE}),
    "DEF": frozenset({Position.DEF}),
    "K": frozenset({Position.K}),
    "FLEX": frozenset({Position.RB, Position.WR, Position.TE}),
    "SUPER_FLEX": frozenset({Position.QB, Position.RB, Position.WR, Position.TE}),
}
"""Which positions may fill each Sleeper starter slot name.

The only place this mapping is written down. `SUPER_FLEX` accepting `QB` is the whole
reason this league drafts differently from a standard one.

`K` is listed because it is a real Sleeper slot, not because this app supports one — it is
recognised here so that `from_sleeper` can reject it with a message explaining the
decision, rather than with a misleading "unrecognised slot" typo error.
"""


@dataclass(frozen=True, slots=True)
class SlotInstance:
    """One concrete starter slot.

    `roster_positions` lists `RB` twice; those become two instances with distinct ids
    (`RB.1`, `RB.2`) so a matching algorithm can assign a different player to each.
    """

    id: str
    name: str
    eligible: frozenset[Position]

    def accepts(self, position: Position) -> bool:
        """Whether a player at `position` may fill this slot."""
        return position in self.eligible


@dataclass(frozen=True, slots=True)
class LeagueConfig:
    """Everything the domain layer needs to know about the league.

    Built by `from_sleeper()`. Nothing here is ever hardcoded — `teams`, `rounds` and the
    slot layout all come from the API payloads.
    """

    teams: int
    rounds: int
    reversal_round: int
    starter_slots: tuple[SlotInstance, ...]
    bench_count: int
    excluded_positions: frozenset[Position] = EXCLUDED_POSITIONS

    @classmethod
    def from_sleeper(cls, league: Mapping[str, Any], draft: Mapping[str, Any]) -> Self:
        """Build a config from Sleeper's `/league/{id}` and `/draft/{id}` payloads.

        Both payloads are required, and the reason is a trap worth stating: the league
        object carries `settings.draft_rounds = 3`, which is stale and unused, while the
        draft object carries the authoritative `settings.rounds = 16`. Reading the league
        value produces a silently truncated draft in which nothing crashes and every
        downstream number is wrong.

        Every check here exists so that a league change surfaces days before the draft
        rather than as a wrong number during it.

        Raises:
            KeyError: a required field is absent from either payload.
            LeagueConfigError: the draft is not a snake, a `roster_positions` entry is not
                a recognised slot name, a structural value is out of range, or the two
                payloads disagree about the number of teams.
        """
        roster_positions = league["roster_positions"]
        if not isinstance(roster_positions, Sequence) or isinstance(roster_positions, str):
            raise LeagueConfigError(
                f"roster_positions must be a list, got {type(roster_positions).__name__}"
            )

        draft_type = draft["type"]
        if draft_type != SNAKE_DRAFT_TYPE:
            # Every seat, roster and survival estimate in this app assumes snake order.
            # An auction or linear draft would compute cleanly and be entirely wrong.
            raise LeagueConfigError(
                f"draft type is {draft_type!r}, expected {SNAKE_DRAFT_TYPE!r}; "
                "this app's pick maths assumes a snake draft"
            )

        draft_settings = draft["settings"]
        teams = int(draft_settings["teams"])
        rounds = int(draft_settings["rounds"])
        # Not `.get(..., 0)`. A missing reversal_round is a payload shape change, and
        # defaulting it would silently draft rounds 3-16 against a board that never existed.
        reversal_round = int(draft_settings["reversal_round"])

        if teams < 2:
            raise LeagueConfigError(f"teams must be at least 2, got {teams}")
        if rounds < 1:
            raise LeagueConfigError(f"rounds must be at least 1, got {rounds}")
        if not 0 <= reversal_round <= rounds:
            raise LeagueConfigError(f"reversal_round {reversal_round} outside 0..{rounds}")

        # Cross-checking the two payloads is the reason this method takes both. The league
        # object independently reports the roster count; if they ever disagree, one of them
        # is describing a different league and we must not pick a winner silently.
        rosters = league.get("total_rosters")
        if rosters is not None and int(rosters) != teams:
            raise LeagueConfigError(
                f"league reports {int(rosters)} rosters but draft reports {teams} teams; "
                "refusing to guess which is authoritative"
            )

        starter_slots, bench_count = _parse_roster_positions(roster_positions)

        if any(slot.name == "K" for slot in starter_slots):
            # The strategy assumes no kicker slot exists. If one appears, the league
            # changed and the roster model needs revisiting — do not silently absorb it.
            raise LeagueConfigError(
                "league now has a K slot; kickers are excluded from this app "
                "(see docs/plan_phase1_domain_core.md, decision 1)"
            )

        return cls(
            teams=teams,
            rounds=rounds,
            reversal_round=reversal_round,
            starter_slots=starter_slots,
            bench_count=bench_count,
        )

    @property
    def ranked_starter_slots(self) -> tuple[SlotInstance, ...]:
        """Starter slots this app ranks for — `DEF` removed.

        Defenses are streamed, so the `DEF` slot is never reported as an unfilled need and
        the app never recommends drafting one. It stays in `starter_slots` so the real
        roster shape remains inspectable.
        """
        return tuple(
            slot for slot in self.starter_slots if not (slot.eligible <= self.excluded_positions)
        )

    @property
    def total_picks(self) -> int:
        """Every pick in the draft — 160 for this league."""
        return self.teams * self.rounds


def _parse_roster_positions(
    roster_positions: Sequence[str],
) -> tuple[tuple[SlotInstance, ...], int]:
    """Split Sleeper's flat `roster_positions` list into starter slots and a bench count.

    Repeated names become distinct instances: `["RB", "RB"]` -> `RB.1`, `RB.2`.

    Raises:
        LeagueConfigError: on any slot name not in `SLOT_ELIGIBILITY` (and not `BN`).
            Failing loudly here is the point — an unrecognised slot silently dropped would
            corrupt the replacement baseline exactly the way LEG-1 did.
    """
    slots: list[SlotInstance] = []
    bench_count = 0
    seen: dict[str, int] = {}

    for index, raw_name in enumerate(roster_positions):
        name = str(raw_name)

        if name == BENCH_SLOT:
            bench_count += 1
            continue

        eligible = SLOT_ELIGIBILITY.get(name)
        if eligible is None:
            raise LeagueConfigError(
                f"unrecognised roster slot {name!r} at roster_positions[{index}]; "
                f"known slots are {sorted(SLOT_ELIGIBILITY)} plus {BENCH_SLOT!r}"
            )

        seen[name] = seen.get(name, 0) + 1
        slots.append(SlotInstance(id=f"{name}.{seen[name]}", name=name, eligible=eligible))

    return tuple(slots), bench_count
