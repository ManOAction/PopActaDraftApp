"""Pure draft domain logic — no database, no HTTP, no I/O.

Everything in this package is a pure function or an immutable value over plain data,
so it can be unit-tested without a session, a network, or a fixture server. This is
the part that has to be right on draft night.

See `docs/plan_phase1_domain_core.md` for the locked contracts.
"""
