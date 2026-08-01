"""Cross-module integration tests for the Phase 1 domain core.

`snake.py`, `draft.py` and `roster.py` were written concurrently from a shared contract and
each is well tested in isolation. Nothing tested them *together*, and the seam between them
is where a contract mismatch would hide.

The seam that matters most: in production the `snake` **module object itself** is passed as
`DraftState.numbering` (it satisfies the `SnakeNumbering` Protocol structurally). Every
`DraftState` here is built that way — `DraftState(config=config, numbering=snake)` — so the
real pairing is what gets exercised, not `linear_numbering()`.

The strongest check in this file is that `snake.seat_picks` and the seats
`DraftState.picks()` derives via `snake.round_and_seat` agree on who owns what. Those are
two independently written functions; agreement is evidence, not a tautology.

Nothing here hardcodes 10, 16 or 160. Every number is derived from the pinned fixtures.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import pytest

from popacta.domain import snake
from popacta.domain.draft import DraftState, Pick
from popacta.domain.league import LeagueConfig, SlotInstance
from popacta.domain.positions import RANKED_POSITIONS, Position
from popacta.domain.roster import StarterAssignment, assign_starters

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_config() -> LeagueConfig:
    """Build the real league config from the pinned Sleeper payloads.

    Loaded at import time as well as via a fixture, because `parametrize` needs the seat
    range at collection time and writing `range(1, 11)` would hardcode the team count.
    """
    league: dict[str, Any] = json.loads(
        (FIXTURES / "sleeper_league.json").read_text(encoding="utf-8")
    )
    draft: dict[str, Any] = json.loads(
        (FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8")
    )
    return LeagueConfig.from_sleeper(league, draft)


CONFIG: Final[LeagueConfig] = _load_config()
SEATS: Final[tuple[int, ...]] = tuple(range(1, CONFIG.teams + 1))


# --- the simulated draft ---------------------------------------------------------------

POSITION_CYCLE: Final[tuple[Position, ...]] = (
    Position.QB,
    Position.RB,
    Position.WR,
    Position.RB,
    Position.WR,
    Position.TE,
    Position.QB,
    Position.WR,
    Position.RB,
    Position.WR,
    Position.TE,
    Position.RB,
    Position.WR,
)
"""Positions handed out by pick number, cycling.

Length 13 is deliberate: the snake order repeats every `2 * teams` picks, so a cycle length
sharing that period would hand every seat an identical roster. 13 is coprime with 20, which
gives each seat a different and realistic QB/RB/WR/TE mix.
"""


def player(pick_number: int) -> str:
    """A traceable player id: the pick number it was originally recorded at."""
    return f"P{pick_number:03d}"


def position_for_pick(pick_number: int, config: LeagueConfig) -> Position:
    """The position of the player taken at `pick_number`.

    The final round is all defenses — every team streams one late. `DEF` is never ranked,
    so those players must record normally and then land on the bench, never in a slot and
    never as an unfilled need.
    """
    if pick_number > config.teams * (config.rounds - 1):
        return Position.DEF
    return POSITION_CYCLE[(pick_number - 1) % len(POSITION_CYCLE)]


POSITIONS: Final[Mapping[str, Position]] = {
    player(n): position_for_pick(n, CONFIG) for n in range(1, CONFIG.total_picks + 1)
}


def record_picks(state: DraftState, count: int) -> DraftState:
    """Record the next `count` picks, ids matching their original pick numbers."""
    for pick_number in range(state.picks_made + 1, state.picks_made + count + 1):
        state = state.record(player(pick_number))
    return state


@pytest.fixture(scope="module")
def config() -> LeagueConfig:
    return CONFIG


@pytest.fixture(scope="module")
def empty(config: LeagueConfig) -> DraftState:
    """An empty draft wired to the real `snake` module — the production pairing."""
    return DraftState(config=config, numbering=snake)


@pytest.fixture(scope="module")
def full(empty: DraftState) -> DraftState:
    """A complete simulated draft. Safe to share: `DraftState` is immutable."""
    return record_picks(empty, empty.config.total_picks)


# --- shared assertions -----------------------------------------------------------------


def assert_contiguous(state: DraftState) -> None:
    """Pick numbers are exactly `1..picks_made`, once each, with seats that agree with snake.

    The seat check runs against `snake.seat_picks`, not against `round_and_seat` — the
    former is built from `pick_number` and the latter is its independently written inverse,
    so this is a genuine cross-check rather than a restatement.
    """
    picks = state.picks()
    numbers = [pick.pick_number for pick in picks]
    expected = list(range(1, state.picks_made + 1))

    assert numbers == expected, (
        f"pick sequence is not contiguous 1..{state.picks_made}: "
        f"missing {sorted(set(expected) - set(numbers))}, "
        f"unexpected {sorted(set(numbers) - set(expected))}"
    )
    assert len(set(numbers)) == len(numbers), (
        f"duplicate pick numbers: {sorted({n for n in numbers if numbers.count(n) > 1})}"
    )

    config = state.config
    for seat in range(1, config.teams + 1):
        owned = {pick.pick_number for pick in picks if pick.seat == seat}
        from_snake = {
            n
            for n in snake.seat_picks(seat, config.teams, config.rounds, config.reversal_round)
            if n <= state.picks_made
        }
        assert owned == from_snake, (
            f"seat {seat}: DraftState says it owns {sorted(owned)}, "
            f"snake.seat_picks says {sorted(from_snake)}"
        )


def roster_map(state: DraftState, seat: int) -> dict[str, Position]:
    """That seat's roster as `assign_starters` wants it: player id -> position, in pick order."""
    return {player_id: POSITIONS[player_id] for player_id in state.roster_for_seat(seat)}


def maximum_matching_size(roster: Mapping[str, Position], slots: Sequence[SlotInstance]) -> int:
    """How many slots the best possible assignment fills, derived independently.

    Uses the deficiency form of Hall's theorem on the slot side —
    `max matching = |slots| - max(|T| - |eligible players for T|)` over all subsets `T` —
    rather than re-running an augmenting-path search, so this does not simply reimplement
    `assign_starters` and agree with its bugs. There are only ~9 ranked slots, so the
    2**9 subsets are free.
    """
    slot_list = tuple(slots)
    eligible = [
        frozenset(p for p, position in roster.items() if slot.accepts(position))
        for slot in slot_list
    ]

    worst = 0
    for mask in range(1 << len(slot_list)):
        chosen = [i for i in range(len(slot_list)) if mask & (1 << i)]
        neighbours: set[str] = set()
        for i in chosen:
            neighbours |= eligible[i]
        worst = max(worst, len(chosen) - len(neighbours))
    return len(slot_list) - worst


def assert_assignment_is_coherent(
    assignment: StarterAssignment,
    roster: Mapping[str, Position],
    slots: Sequence[SlotInstance],
    context: str,
) -> None:
    """Every legality invariant a starter assignment must satisfy, whoever produced it."""
    slot_by_id = {slot.id: slot for slot in slots}
    placed = list(assignment.filled.values())

    unknown = set(assignment.filled) - set(slot_by_id)
    assert not unknown, (
        f"{context}: filled references slots that were not offered: {sorted(unknown)}"
    )

    duplicated = sorted({p for p in placed if placed.count(p) > 1})
    assert not duplicated, f"{context}: player(s) assigned to two slots at once: {duplicated}"

    for slot_id, player_id in assignment.filled.items():
        assert player_id in roster, f"{context}: {player_id!r} in {slot_id} is not on the roster"
        position = roster[player_id]
        assert slot_by_id[slot_id].accepts(position), (
            f"{context}: {player_id!r} ({position}) placed in {slot_id}, "
            f"which accepts only {sorted(slot_by_id[slot_id].eligible)}"
        )

    partition = set(assignment.filled) | {slot.id for slot in assignment.unfilled}
    assert partition == set(slot_by_id), (
        f"{context}: filled + unfilled is not the slot list; "
        f"missing {sorted(set(slot_by_id) - partition)}, "
        f"extra {sorted(partition - set(slot_by_id))}"
    )
    assert len(assignment.filled) + len(assignment.unfilled) == len(slots), (
        f"{context}: {len(assignment.filled)} filled + {len(assignment.unfilled)} unfilled "
        f"!= {len(slots)} slots"
    )

    accounted = sorted([*placed, *assignment.bench])
    assert accounted == sorted(roster), (
        f"{context}: starters + bench does not equal the roster; "
        f"unaccounted {sorted(set(roster) - set(accounted))}, "
        f"invented {sorted(set(accounted) - set(roster))}"
    )

    # Necessary condition of a maximum matching: no open slot has an idle eligible player.
    for slot in assignment.unfilled:
        stranded = [p for p in assignment.bench if slot.accepts(roster[p])]
        assert not stranded, (
            f"{context}: {slot.id} is unfilled but {stranded} on the bench are eligible for it"
        )

    # The stronger claim: no *other* assignment fills more slots either.
    best = maximum_matching_size(roster, slots)
    assert len(assignment.filled) == best, (
        f"{context}: filled {len(assignment.filled)} slots, but {best} can be filled — "
        f"open slots {[s.id for s in assignment.unfilled]}, bench {list(assignment.bench)}"
    )


# --- 1. a full simulated draft ---------------------------------------------------------


def test_a_full_draft_is_contiguous_with_snake_seats(full: DraftState) -> None:
    """The headline integration case: record every pick, then check the whole board."""
    assert full.picks_made == full.config.total_picks
    assert_contiguous(full)
    assert full.next_pick_number is None
    assert full.seat_on_the_clock is None


def test_every_seat_owns_exactly_one_pick_per_round(full: DraftState) -> None:
    config = full.config
    seen: list[str] = []

    for seat in range(1, config.teams + 1):
        roster = full.roster_for_seat(seat)
        assert len(roster) == config.rounds, (
            f"seat {seat} owns {len(roster)} picks, expected {config.rounds}"
        )
        seen.extend(roster)

    assert sorted(seen) == sorted(full.player_ids), "every pick must belong to exactly one seat"


@pytest.mark.parametrize("seat", SEATS)
def test_seat_ownership_matches_snake_seat_picks(full: DraftState, seat: int) -> None:
    """Two independently written modules agreeing on who owns which pick."""
    config = full.config
    from_draft = tuple(p.pick_number for p in full.picks() if p.seat == seat)
    from_snake = snake.seat_picks(seat, config.teams, config.rounds, config.reversal_round)

    assert from_draft == from_snake, (
        f"seat {seat}: DraftState derived {from_draft}, snake.seat_picks says {from_snake}"
    )
    # And the players match, so the roster view is built off the same ownership.
    assert full.roster_for_seat(seat) == tuple(player(n) for n in from_snake)


def test_rounds_advance_one_per_teams_picks(full: DraftState) -> None:
    config = full.config
    for pick in full.picks():
        expected_round = (pick.pick_number - 1) // config.teams + 1
        assert pick.round == expected_round, (
            f"pick {pick.pick_number} reported round {pick.round}, expected {expected_round}"
        )


def test_seat_on_the_clock_agrees_with_seat_picks_at_every_prefix(empty: DraftState) -> None:
    """Walk the whole draft, checking who is up against `snake.seat_picks` each time."""
    config = empty.config
    owner = {
        pick_number: seat
        for seat in range(1, config.teams + 1)
        for pick_number in snake.seat_picks(
            seat, config.teams, config.rounds, config.reversal_round
        )
    }

    state = empty
    for pick_number in range(1, config.total_picks + 1):
        assert state.next_pick_number == pick_number
        assert state.seat_on_the_clock == owner[pick_number], (
            f"before pick {pick_number}: state says seat {state.seat_on_the_clock} is up, "
            f"snake.seat_picks says seat {owner[pick_number]}"
        )
        state = state.record(player(pick_number))
        assert state.picks()[-1].seat == owner[pick_number], (
            f"pick {pick_number} was recorded to seat {state.picks()[-1].seat}, "
            f"but seat {owner[pick_number]} was on the clock"
        )


# --- 2. picks_until_next_turn against actual draft progress ----------------------------


def intervening_pick_count(picks: Sequence[Pick], seat: int, picks_made: int) -> int | None:
    """Picks by *other* seats that actually occur before `seat` picks again.

    Read off the recorded draft, deliberately not recomputed from the snake formula.
    """
    later = [p.pick_number for p in picks if p.seat == seat and p.pick_number > picks_made]
    if not later:
        return None

    next_mine = min(later)
    between = [p for p in picks if picks_made < p.pick_number < next_mine]
    assert all(p.seat != seat for p in between), (
        f"seat {seat}: picks {[p.pick_number for p in between if p.seat == seat]} between "
        f"{picks_made} and {next_mine} were its own, so {next_mine} was not its next pick"
    )
    return len(between)


@pytest.mark.parametrize("seat", SEATS)
def test_picks_until_next_turn_matches_the_simulated_draft(full: DraftState, seat: int) -> None:
    """The keystone, checked against reality at every point in a real 160-pick draft."""
    config = full.config
    picks = full.picks()

    for picks_made in range(config.total_picks + 1):
        expected = intervening_pick_count(picks, seat, picks_made)
        actual = snake.picks_until_next_turn(
            seat, picks_made, config.teams, config.rounds, config.reversal_round
        )
        assert actual == expected, (
            f"seat {seat} after {picks_made} picks: picks_until_next_turn said {actual}, "
            f"but {expected} picks by other seats actually happen before its next turn"
        )


@pytest.mark.parametrize("seat", SEATS)
def test_next_pick_for_seat_matches_the_simulated_draft(full: DraftState, seat: int) -> None:
    config = full.config
    picks = full.picks()

    for picks_made in range(config.total_picks + 1):
        later = [p.pick_number for p in picks if p.seat == seat and p.pick_number > picks_made]
        expected = min(later) if later else None
        actual = snake.next_pick_for_seat(
            seat, picks_made, config.teams, config.rounds, config.reversal_round
        )
        assert actual == expected, (
            f"seat {seat} after {picks_made} picks: next_pick_for_seat said {actual}, "
            f"the draft's next pick for that seat is {expected}"
        )


@pytest.mark.parametrize("seat", SEATS)
def test_picks_until_next_turn_is_none_only_after_a_seats_last_pick(
    full: DraftState, seat: int
) -> None:
    config = full.config
    last_owned = max(p.pick_number for p in full.picks() if p.seat == seat)

    assert (
        snake.picks_until_next_turn(
            seat, last_owned - 1, config.teams, config.rounds, config.reversal_round
        )
        == 0
    ), f"seat {seat} should be on the clock at its final pick {last_owned}"
    assert (
        snake.picks_until_next_turn(
            seat, last_owned, config.teams, config.rounds, config.reversal_round
        )
        is None
    ), f"seat {seat} has no picks left after {last_owned}"


def test_the_clock_seat_is_exactly_the_seat_with_zero_picks_until_its_turn(
    empty: DraftState,
) -> None:
    """`DraftState.seat_on_the_clock` and `picks_until_next_turn == 0` must never disagree."""
    config = empty.config
    state = empty

    for picks_made in range(config.total_picks):
        ready = [
            seat
            for seat in range(1, config.teams + 1)
            if snake.picks_until_next_turn(
                seat, picks_made, config.teams, config.rounds, config.reversal_round
            )
            == 0
        ]
        assert ready == [state.seat_on_the_clock], (
            f"after {picks_made} picks, seats with 0 picks until their turn are {ready}, "
            f"but seat_on_the_clock is {state.seat_on_the_clock}"
        )
        state = state.record(player(picks_made + 1))


# --- 3. undo mid-draft, then continue --------------------------------------------------


def undo_points(config: LeagueConfig, picks_made: int) -> list[int]:
    """Interesting places to undo: derived from the league, never hardcoded."""
    return [
        1,
        config.teams // 2,
        config.teams,  # last pick of round 1
        config.teams + 1,  # first pick of round 2 — the far side of the turn
        2 * config.teams,
        picks_made // 2,
        picks_made,
    ]


def test_undo_mid_draft_keeps_the_board_consistent_with_snake(empty: DraftState) -> None:
    """Undo partway through a realistic draft: every later pick shifts and re-seats."""
    config = empty.config
    partial = record_picks(empty, config.teams * (config.rounds // 2))

    for target in undo_points(config, partial.picks_made):
        after = partial.undo(target)

        assert after.picks_made == partial.picks_made - 1
        assert_contiguous(after)
        assert player(target) not in after.drafted_ids
        assert after.player_ids == tuple(
            player(n) for n in range(1, partial.picks_made + 1) if n != target
        ), f"undo({target}) did not simply remove that pick"

        # Everything after the hole moved down one and its seat was recomputed.
        for pick in after.picks():
            if pick.pick_number >= target:
                original = pick.pick_number + 1
                assert pick.player_id == player(original), (
                    f"after undo({target}), pick {pick.pick_number} holds "
                    f"{pick.player_id!r}, expected {player(original)!r}"
                )
            _round, seat = snake.round_and_seat(
                pick.pick_number, config.teams, config.reversal_round
            )
            assert pick.seat == seat

        assert partial.picks_made == config.teams * (config.rounds // 2), (
            "undo mutated the original"
        )


def test_undo_then_resume_picks_up_at_the_right_pick_and_seat(empty: DraftState) -> None:
    """Correcting a mis-recorded pick mid-draft, then carrying on."""
    config = empty.config
    partial = record_picks(empty, config.teams * 4 + 3)
    target = config.teams + 1  # the first pick of round 2, on the far side of the turn

    corrected = partial.undo(target)

    assert corrected.next_pick_number == partial.picks_made
    expected_seat = next(
        seat
        for seat in range(1, config.teams + 1)
        if corrected.next_pick_number
        in snake.seat_picks(seat, config.teams, config.rounds, config.reversal_round)
    )
    assert corrected.seat_on_the_clock == expected_seat

    resumed = corrected.record("REPLACEMENT")

    assert resumed.picks_made == partial.picks_made
    assert_contiguous(resumed)
    last = resumed.picks()[-1]
    assert last.pick_number == partial.picks_made
    assert last.seat == expected_seat
    assert last.player_id == "REPLACEMENT"

    # And the draft keeps going normally from there.
    continued = record_picks(resumed, config.teams)
    assert continued.picks_made == partial.picks_made + config.teams
    assert_contiguous(continued)
    assert corrected.picks_made == partial.picks_made - 1, "record mutated the original"


def test_undo_across_the_turn_hands_a_pick_to_a_different_seat(empty: DraftState) -> None:
    """Snake makes undo interesting: shifting by one flips which side of the turn a pick is on."""
    config = empty.config
    partial = record_picks(empty, config.teams * 3)
    turn = config.teams

    first_half = partial.picks()[turn - 1]  # pick `teams`, the last of round 1
    second_half = partial.picks()[turn]  # pick `teams + 1`, the first of round 2
    assert first_half.seat == second_half.seat == turn, "seat `teams` should pick back-to-back"
    assert partial.roster_for_seat(turn)[:2] == (first_half.player_id, second_half.player_id)

    after = partial.undo(1)
    moved_out = next(p for p in after.picks() if p.player_id == first_half.player_id)
    moved_in = next(p for p in after.picks() if p.player_id == second_half.player_id)

    assert moved_out.pick_number == first_half.pick_number - 1
    assert moved_out.seat == turn - 1, (
        f"{first_half.player_id!r} slid off the turn and should now belong to seat {turn - 1}, "
        f"not seat {moved_out.seat}"
    )
    assert moved_in.pick_number == second_half.pick_number - 1
    assert moved_in.seat == turn, "the pick that slid into the round boundary is still at the turn"
    assert after.roster_for_seat(turn)[0] == second_half.player_id
    assert after.roster_for_seat(turn - 1)[0] == first_half.player_id
    assert_contiguous(after)


# --- 4. roster legality throughout a real draft ----------------------------------------


@pytest.mark.parametrize("seat", SEATS)
def test_starter_assignment_stays_legal_at_every_round_boundary(
    empty: DraftState, full: DraftState, seat: int
) -> None:
    """Fit each seat's growing roster into the ranked slots after every round."""
    config = full.config
    slots = config.ranked_starter_slots

    for round_ in range(1, config.rounds + 1):
        state = DraftState(
            config=config,
            numbering=snake,
            player_ids=full.player_ids[: round_ * config.teams],
        )
        roster = roster_map(state, seat)
        assert len(roster) == round_, (
            f"seat {seat} should hold {round_} players after round {round_}"
        )

        assignment = assign_starters(roster, slots)
        assert_assignment_is_coherent(
            assignment, roster, slots, context=f"seat {seat}, after round {round_}"
        )
        assert len(assignment.filled) <= min(len(roster), len(slots))

    assert empty.picks_made == 0


@pytest.mark.parametrize("seat", SEATS)
def test_ranked_slots_never_report_a_defense_as_a_need(full: DraftState, seat: int) -> None:
    """Every team drafts a defense in the final round; it must bench, not fill or be needed."""
    config = full.config
    roster = roster_map(full, seat)
    defenses = [p for p, position in roster.items() if position == Position.DEF]
    assert defenses, "the simulation should give every seat a defense"

    assignment = assign_starters(roster, config.ranked_starter_slots)

    assert not any(slot.name == "DEF" for slot in assignment.unfilled)
    assert all(p not in assignment.filled.values() for p in defenses)
    assert all(p in assignment.bench for p in defenses)


def test_only_ranked_positions_ever_fill_a_ranked_slot(full: DraftState) -> None:
    config = full.config
    for seat in range(1, config.teams + 1):
        roster = roster_map(full, seat)
        assignment = assign_starters(roster, config.ranked_starter_slots)
        for slot_id, player_id in assignment.filled.items():
            assert roster[player_id] in RANKED_POSITIONS, (
                f"seat {seat}: {roster[player_id]} filled {slot_id}, "
                f"but only {sorted(RANKED_POSITIONS)} are ranked"
            )


def test_bench_never_exceeds_what_the_league_allows(full: DraftState) -> None:
    """Sanity on the shape: full starters + bench is the roster size the league sells."""
    config = full.config
    for seat in range(1, config.teams + 1):
        roster = roster_map(full, seat)
        assignment = assign_starters(roster, config.starter_slots)
        assert len(assignment.filled) + len(assignment.bench) == config.rounds
        assert len(assignment.bench) <= config.bench_count + len(assignment.unfilled), (
            f"seat {seat}: {len(assignment.bench)} benched with "
            f"{len(assignment.unfilled)} starter slots open"
        )


# --- 5. superflex: the case the 2025 schema could not express (LEG-1) -------------------


def test_a_seat_with_two_quarterbacks_starts_both(empty: DraftState) -> None:
    """Two QBs must land in `QB` and `SUPER_FLEX` — the whole reason this league drafts oddly.

    The roster is built through a real recorded draft, and is sized so that filling every
    ranked slot is only possible with both QBs starting. The QBs are drafted *last* so that
    a player-major greedy assignment would have already committed the flex-eligible players.
    """
    config = empty.config
    slots = config.ranked_starter_slots
    seat = 1

    # Exactly enough players to fill every ranked slot: 7 flex-eligible, then 2 QBs.
    wanted = [
        Position.RB,
        Position.WR,
        Position.RB,
        Position.WR,
        Position.TE,
        Position.RB,
        Position.WR,
        Position.QB,
        Position.QB,
    ]
    assert len(wanted) == len(slots), "the roster must exactly fill the ranked slots"

    positions: dict[str, Position] = {}
    state = empty
    mine = 0
    while mine < len(wanted):
        pick_number = state.next_pick_number
        assert pick_number is not None
        player_id = f"X{pick_number:03d}"
        if state.seat_on_the_clock == seat:
            positions[player_id] = wanted[mine]
            mine += 1
        else:
            positions[player_id] = Position.WR
        state = state.record(player_id)

    roster = {p: positions[p] for p in state.roster_for_seat(seat)}
    assert list(roster.values()) == wanted, "the seat did not end up with the intended roster"

    assignment = assign_starters(roster, slots)

    assert_assignment_is_coherent(assignment, roster, slots, context="the two-QB seat")
    assert assignment.is_complete, (
        f"every slot should be fillable; {[s.id for s in assignment.unfilled]} left open"
    )
    quarterbacks = {p for p, position in roster.items() if position == Position.QB}
    started_at = {slot_id for slot_id, p in assignment.filled.items() if p in quarterbacks}
    assert started_at == {"QB.1", "SUPER_FLEX.1"}, (
        f"the two QBs should occupy QB.1 and SUPER_FLEX.1, they occupy {sorted(started_at)}"
    )
    assert not assignment.bench


def test_a_quarterback_is_never_flex_eligible(full: DraftState) -> None:
    """`FLEX` must reject a QB in every seat's assignment, or superflex means nothing."""
    config = full.config
    for seat in range(1, config.teams + 1):
        roster = roster_map(full, seat)
        assignment = assign_starters(roster, config.ranked_starter_slots)
        for slot_id, player_id in assignment.filled.items():
            if slot_id.startswith("FLEX"):
                assert roster[player_id] != Position.QB, (
                    f"seat {seat}: QB {player_id!r} was placed in {slot_id}"
                )


# --- 6. the turn -----------------------------------------------------------------------


def test_the_last_seat_picks_back_to_back_across_the_round_boundary(empty: DraftState) -> None:
    """Seat `teams` picks at `teams` and `teams + 1`, and is on the clock for both."""
    config = empty.config
    turn = config.teams

    state = record_picks(empty, turn - 1)
    assert state.seat_on_the_clock == turn
    assert (
        snake.picks_until_next_turn(
            turn, state.picks_made, config.teams, config.rounds, config.reversal_round
        )
        == 0
    )

    state = state.record(player(turn))
    assert state.seat_on_the_clock == turn, "seat at the turn must still be up"
    assert (
        snake.picks_until_next_turn(
            turn, state.picks_made, config.teams, config.rounds, config.reversal_round
        )
        == 0
    ), "back-to-back at the turn means zero intervening picks, not one"

    state = state.record(player(turn + 1))
    picks = state.picks()
    assert picks[-1].round == picks[-2].round + 1, "the turn spans a round boundary"
    assert picks[-1].seat == picks[-2].seat == turn
    assert state.roster_for_seat(turn) == (player(turn), player(turn + 1))
    assert state.seat_on_the_clock == turn - 1

    # And the count from here is what the draft actually delivers.
    full_draft = record_picks(state, config.total_picks - state.picks_made)
    assert snake.picks_until_next_turn(
        turn, state.picks_made, config.teams, config.rounds, config.reversal_round
    ) == intervening_pick_count(full_draft.picks(), turn, state.picks_made)


def test_the_first_seat_picks_back_to_back_at_the_end_of_round_two(empty: DraftState) -> None:
    """Seat 1's mirror of the turn: picks 1, then `2 * teams` and `2 * teams + 1`."""
    config = empty.config
    full_draft = record_picks(empty, config.total_picks)

    after_one = record_picks(empty, 1)
    assert after_one.roster_for_seat(1) == (player(1),)
    expected = intervening_pick_count(full_draft.picks(), 1, 1)
    assert (
        snake.picks_until_next_turn(1, 1, config.teams, config.rounds, config.reversal_round)
        == expected
    ), f"seat 1 waits {expected} picks after its opener, per the simulated draft"

    state = record_picks(empty, 2 * config.teams - 1)
    assert state.seat_on_the_clock == 1
    state = state.record(player(2 * config.teams))
    assert state.seat_on_the_clock == 1, "seat 1 is on the clock twice at its turn"
    state = state.record(player(2 * config.teams + 1))

    picks = state.picks()
    assert picks[-1].seat == picks[-2].seat == 1
    assert picks[-1].round == picks[-2].round + 1
    assert state.roster_for_seat(1) == (
        player(1),
        player(2 * config.teams),
        player(2 * config.teams + 1),
    )
