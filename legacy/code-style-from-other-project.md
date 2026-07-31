---
paths:
  - "**/*.py"
---

# Python conventions

- Target **Python 3.11+** — `X | None`, `list[str]`, `dict[str, T]` are fine.
- **No linter/formatter is configured** in this repo. Match the surrounding file's style; do
  not bulk-reformat unrelated lines (no stray whitespace/quote churn in diffs). 4-space indent.
  Lines are allowed to run long here — don't rewrap existing code to fit a column limit.
- **Imports** grouped stdlib → third-party → local (`flurry.*`), explicit (no wildcard) — the
  one exception is the existing `from .scheduler import *` in `flurry/__init__.py`. Mind import
  order: `flurry/__init__.py` re-exports eagerly and some modules run side effects on import
  (AWS secret loading, scheduler registration), so moving imports can break startup. Circular
  imports are avoided with function-local imports (see `suppression.py`) — keep that pattern.
- **Logging:** one module logger per file — `logger = logging.getLogger(__name__)`. f-strings in
  log messages are the norm.
- **Type hints** on public function signatures. Docstrings are triple-quoted, with Args/Returns/
  Raises where it helps.
- **Pydantic v2:** `model_config = ConfigDict(...)`, `@field_validator`, `.model_validate()`,
  `.model_dump()`. Request models use `extra="forbid"`; keep new fields `Optional` with defaults
  for backward compatibility.
- **Dates/times:** use `pendulum` (already a dependency) and keep results **naive UTC** — see the
  timezone footgun in [CLAUDE.md](../../CLAUDE.md).

## Structure & readability
- **Readability over brevity.** Prefer verbose, named steps over clever one-liners (e.g. two
  filtered assignments over one stacked boolean mask). Single-letter names only in tight loops or
  well-known conventions (`i`, `df`, `n`).
- **Comments explain *why*, not *what*.** If code needs a comment to say what it does, rewrite the
  code instead. Reserve comments for non-obvious business rules, hidden constraints, or workarounds.
- **Helper functions over monoliths.** Break complex logic into small `_helper`-prefixed functions,
  each doing one thing summarizable in a sentence (see the pattern in `services/migrations.py`).
- **Functions over classes.** Use modules of plain functions; reach for a class only when there's
  genuinely mutable state multiple methods must coordinate — not as a namespace.
- **Dataclasses only when they earn their keep** — right for structured incoming data (API
  responses, parsed payloads) where validation/type hints help; a plain dict is fine for a handful
  of internal settings.
- **Constants at the top of the module** they belong to; only extract to a shared config module when
  multiple modules truly need the same values.
