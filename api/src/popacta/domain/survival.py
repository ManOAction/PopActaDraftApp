"""Survival probability: will this player still be there when I pick again?

NOT YET IMPLEMENTED — blocked on BLK-1 (`Std Dev`).
See `docs/plan_phase2_decision_engine.md`, decision 8.

The model is a **conditional** normal survival ratio, floored by a constant hazard:

    S(x)      = 0.5 * erfc((x - adp) / (sd * sqrt(2)))      # P(lasts past pick x)
    p_survive = max( S(m + k) / S(m),  exp(-k / (sd * sqrt(3)/pi)) )

Conditioning on `S(m)` — the player being observably still on the board *now* — is the
whole point. The unconditional form answers "what was the chance before the draft began",
which for a player who has fallen past his ADP assigns a near-zero probability to a state
you are currently looking at: ~0.1% unconditional versus ~2.8% conditional for ADP 20,
sd 6, still available at pick 30. Mid-draft the unconditional number destroys trust.

The floor exists because the normal's hazard rate grows without bound, so a deep faller
would otherwise score absurdly confident. A player 40 picks past ADP has fallen *for a
reason* and the market has already repriced him; ADP is stale rather than merely surprising.
"""

from popacta.domain.players import AdpEstimate

__all__ = ["survival"]


def survival(adp: AdpEstimate, picks_made: int, picks_until_turn: int) -> float:
    """Probability the player is still available at your next pick.

    "Still available" means: not taken during picks `picks_made + 1 … picks_made + k`.
    Your own next pick, `picks_made + k + 1`, never enters — you are the one making it.

    Args:
        adp: superflex ADP and its dispersion. **Must** come from a superflex source;
            1QB ADP places elite QBs ~20 picks too late and makes every QB call wrong in
            the same direction.
        picks_made: completed picks, i.e. `DraftState.picks_made`.
        picks_until_turn: `k` from `snake.picks_until_next_turn(seat, picks_made + 1, …)`.
            Note the `+ 1`: the baseline asks what survives between *your* pick and the
            next one, so the pick you are about to make is already counted.

    Returns:
        A probability in `[0, 1]`. Exactly `1.0` when `k == 0` — at the turn a seat picks
        back-to-back, so nobody picks in between and the whole board survives.

    Implementation notes that are not optional:
        - Use `math.erfc`, **never** `1 - NormalDist().cdf(z)`. Verified: `1 - cdf`
          returns *exactly* `0.0` for `z >= 10`, so the ratio becomes `0/0 -> nan`. That
          fires in rounds 13-16 when most remaining players are deep in the tail. `erfc`
          stays accurate to `z ~ 37`. It is stdlib — do not add scipy for this.
        - Guard `S(m) < 1e-12` by returning the floor: ADP is stale and the normal has no
          usable opinion left.

    Raises:
        DraftRangeError: `picks_made` or `picks_until_turn` negative.
    """
    raise NotImplementedError


def expected_max(candidates: "list[tuple[float, float]]") -> float:
    """`E[max value among survivors]` for `(value, survival_probability)` pairs.

    Exact under independence, one `O(n)` pass after sorting descending by value: a value
    is the maximum exactly when it survives and every better candidate did not.

        acc, none_yet = 0, 1
        for value, s in sorted_desc:
            acc      += value * s * none_yet
            none_yet *= (1 - s)

    This is **not** the max of the expectations, nor the mean of the survivors. Measured
    on the real board, mean-of-survivors is off by 150+ points and the deterministic
    "value at rank m+k+1" — the shape LEG-5 actually used — by 47-81, always pessimistic.
    The point-estimate shortcuts land within ~2 points but discard the variance that is
    the entire reason `sd` exists, and save nothing: this *is* the cheap form.

    Callers may truncate to the top `k + 1 + 10` by value — at most `k` players can leave,
    so the best survivor is provably among the top `k + 1`. Assert the residual `none_yet`
    is negligible on a full pool.

    Returns:
        `0.0` for an empty candidate list — an empty window has expectation zero, which is
        also exactly what makes the final pick of the draft need no special case.
    """
    raise NotImplementedError
