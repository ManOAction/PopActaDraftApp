# Structuring Project Context for Claude Code

A guide for setting up project documentation so Claude Code loads the *right* context at the *right* time — instead of everything, all the time.

> **Revision note (2026-07-10).** Originally written 2026-05 and used to restructure the Cypress Grove docs. This revision updates it to match the strategy as actually adopted and refined in practice — nested `CLAUDE.md` files as the primary scoping mechanism, `.claude/rules/` for cross-repo file-type rules, an explicit section on auto-memory, and a version-control requirement — so the same strategy can be applied to a new project as-is.

---

## TL;DR

Stop telling Claude to "read the `docs/` folder." Instead, give it a small always-loaded `CLAUDE.md` that acts as a **map**, scope rules to the directories and file types they apply to, and let Claude open the deeper reference docs **on demand**. This makes Claude faster, cheaper, and more accurate, at the cost of keeping the map up to date.

This document explains why, then tells you exactly what to put where.

---

## Why we need this

Every Claude Code session starts with a fresh, finite context window. Whatever we load into it up front is paid for in two currencies:

- **Tokens** — a hard budget. Docs we load take space that could go to actual code and conversation.
- **Attention** — a softer but more important cost. The more unrelated material sits in context, the more diluted Claude's focus becomes. A large pile of "just in case" documentation makes the instructions that *do* matter harder to follow.

The naive habit — "read the `docs/` folder, then do XYZ" — is the worst case for both. It loads the roadmap, every feature description, the architecture deep-dive, the open-issues list, and the style guide on **every** task, even when the task touches one DAG or one API route. You pay full price for context you mostly don't use, every single time. (On Cypress Grove that was ~8,200 lines of docs per session before the restructure.)

There's a second, subtler problem. "Read the docs folder" treats every document as the same kind of thing. It isn't. Two distinctions matter:

**Rule vs. reference.** A *rule* is something Claude must obey — "4-space indentation," "never edit a shipped migration," "this repo is Airflow-only." A *reference* is something Claude consults to understand — how a subsystem is shaped, what a feature is supposed to do. Rules need to be reliably triggered and given priority; reference just needs to be available when relevant. Burying rules inside a doc that may or may not get read is the wrong home for them.

**Eager vs. lazy.** Anything loaded at session start (the root `CLAUDE.md`, anything it imports) is "eager" — paid for always. Anything Claude opens mid-session only when needed is "lazy" — paid for only when relevant. The goal of this whole setup is to keep the eager layer **small and high-signal**, while keeping the lazy layer **discoverable** so Claude knows what exists and when to reach for it.

---

## How it works: five homes for context

Sort each piece of project knowledge into one of five places, based on *when* Claude needs it and *what kind* of thing it is.

1. **Always-on → root `CLAUDE.md` (kept lean).** Build/test commands, project layout, the handful of genuinely universal rules, and a **map** pointing to everything else. Keep it under ~200 lines; longer files consume more context and Claude follows them less reliably.

2. **Rules scoped to a directory → nested `CLAUDE.md` files.** A `CLAUDE.md` inside a subdirectory doesn't load at launch — it auto-loads when Claude reads files in that directory. This is the workhorse of the whole setup, with two distinct uses:
   - **Repo/area rules** at the top of each code area (e.g. "this repo is Airflow-only — everything must be idempotent" vs. "this repo is human-triggered — interactive scripts are fine"). Directory identity is exactly the scope these rules want.
   - **Feature pointers** in each feature folder: a ~10-line file saying what the feature is, linking its full feature doc in `docs/`, and stating any feature-local gotchas. This makes feature context self-triggering — start working in the folder and the pointer loads; the deep doc is one read away.

3. **Rules scoped to a file type → `.claude/rules/*.md` with a `paths:` glob.** A rule file with `paths:` frontmatter loads only when Claude works on matching files, at instruction priority. Use this for rules that cut *across* directories — e.g. one shared Python style file with a `**/*.py` glob instead of copy-pasting the style section into every area's nested `CLAUDE.md` (that duplication **will** drift; it did for us). Nested `CLAUDE.md` = "rules of this place"; `.claude/rules` glob = "rules of this file type, everywhere."

4. **Reference, read on demand → stays in `docs/`,** pointed to from the map in `CLAUDE.md`. Claude opens these with its normal file tools when the task calls for them. This includes feature descriptions, architecture, roadmap/issues, and **plans and runbooks** for in-flight work (prefix them: `plan_*.md`, `runbook_*.md`, `report_*.md` for completed work). Repeatable procedures can alternatively become skills that load on invocation; in practice mapped runbooks work fine and keep everything in one folder — just prune or re-status map entries when work ships, since each map line is paid for eagerly.

5. **Session-spanning state → auto-memory.** Claude Code's persistent memory is a per-user store, invisible to teammates and to any other tooling — so route knowledge carefully:
   - **Belongs in memory:** state and preferences — what shipped when, what's blocked on whom, in-flight experiment status, user working preferences, feedback on how to work. Things that change too often to doc-ify or are about the collaboration rather than the system.
   - **Belongs in docs:** durable project facts — validated semantics, schemas, gotchas, designs. If a teammate (or a fresh agent with no memory) would need it, it's a doc, not a memory. When a memory turns out to be a durable fact, promote it to `docs/` and leave the map or a nested `CLAUDE.md` pointing at it.

The mechanism that makes lazy loading actually work is **discoverability**. Claude can only open a doc on demand if it knows the doc exists and knows *when* to open it. That's the map's entire job. Brute-force "read everything" buys discoverability by paying full context cost; the map buys discoverability for almost nothing — provided you write it well (see below).

---

## Target layout

Shown for a workspace with multiple repos/areas (single-repo projects: same shapes, one level shallower). The root `CLAUDE.md` sits at the top of the working directory Claude is launched from.

```text
workspace/
├── CLAUDE.md                     # lean: commands, layout, the map, universal rules
├── .claude/
│   └── rules/
│       └── code-style.md         # shared Python style, paths: "**/*.py"
├── repo_a/                       # e.g. Airflow-only ETL code
│   ├── CLAUDE.md                 # repo rules (idempotency, credentials, ...) + repo-specific style deltas
│   ├── feature_x/
│   │   └── CLAUDE.md             # ~10 lines: what it is → link to docs/FeatureDescription_X.md + gotchas
│   └── migrations/versions/
│       └── CLAUDE.md             # migration safety rules
├── repo_b/                       # e.g. human-triggered scripts
│   └── CLAUDE.md                 # different rules — interactive is fine here
└── docs/
    ├── architecture.md
    ├── roadmap.md
    ├── issues.md
    ├── FeatureDescription_X.md
    ├── reference_<topic>.md      # durable validated facts (promoted from memory when needed)
    ├── plan_<work>.md            # in-flight designs
    └── runbook_<procedure>.md    # repeatable procedures
```

The `docs/` folder keeps its reference material. What changes is that `CLAUDE.md` stops saying "read all of this" and starts saying "read *this one* when *that* is true."

**Version control is part of the strategy, not optional.** The map, the nested `CLAUDE.md` files, the rules, and `docs/` must be in git. Two reasons: the map-maintenance rule below is enforced through commit discipline, and un-versioned context files have no backup — on Cypress Grove the original of this very guide survived only because a chat transcript happened to retain it.

---

## What goes where

Use this as the routing guide when migrating an existing project's docs.

| Content | Home | Why |
| --- | --- | --- |
| Build/test/run commands, layout, universal rules | Root `CLAUDE.md` | Needed every session. This is the only always-eager file — keep it lean. |
| Rules that apply to one repo/area ("Airflow-only", "each subfolder is self-contained") | Nested `CLAUDE.md` at the top of that area | Auto-loads exactly when working there; different areas legitimately have different rules. |
| Rules that apply to a file type across areas (code style) | `.claude/rules/<topic>.md` with a `paths:` glob | One copy, auto-loads on matching files at instruction priority. Copy-pasting into each area's `CLAUDE.md` drifts. Keep per-area *deltas* in the nested files. |
| High-risk-zone rules (migrations, deploy configs) | Nested `CLAUDE.md` in that directory (or a tight glob) | Exactly the place you want strong, reliably-triggered guardrails. |
| Feature descriptions | `docs/`, + a ~10-line nested `CLAUDE.md` pointer in the feature's code folder | Reference, almost never needed two-at-once. The pointer makes it self-triggering when features map to folders; if a feature is cross-cutting, rely on the map + explicit prompt. |
| Architecture / data flow | `docs/`, mapped. Optionally inline a 4–5 line summary in root `CLAUDE.md`. | Reference. The high-level shape can be always-on; the detail is one read away. |
| Roadmap, open issues | `docs/`, mapped (planning-/triage-only triggers) | Reference. No reason to load them when fixing a DAG. |
| Plans, runbooks, completed-work reports | `docs/` with `plan_`/`runbook_`/`report_` prefixes, mapped | Reference for specific tasks. Skills are an alternative for procedures; mapped runbooks are simpler. Re-status or prune entries when work ships. |
| Validated durable facts (semantics, gotchas) | `docs/reference_<topic>.md`, pointed at from the relevant nested `CLAUDE.md` | Teammates and fresh agents need these; memory is per-user and invisible. |
| Shipped/blocked status, experiment state, user preferences | Auto-memory | Changes too often for docs; about the collaboration, not the system. |

---

## How to write the map

The map lives in the root `CLAUDE.md`. The single most important rule: **make each entry trigger-oriented, not a topic label.** Claude treats `CLAUDE.md` as context it tries to follow, not as enforced configuration, so you're nudging its judgment about *when* to open something. Phrasing each line as a condition ("read X when Y") is what reliably fires the read. A bare topic label is much weaker.

```markdown
# Project: <name>

## Commands
- Test:               pytest
- Lint + format:      ruff check . && ruff format .
- DB migrations:      alembic upgrade head

## Layout
- <area>:  <path>     (one line per repo/area, with its role)

## Documentation map — read on demand
- Working on feature A?  Read docs/FeatureDescription_A.md
- Need system structure / making a cross-cutting change?  Read docs/architecture.md
- Prioritizing or planning what to build?  Read docs/roadmap.md
- Triaging or fixing bugs?  Read docs/issues.md
- Running <procedure>?  Read docs/runbook_<procedure>.md

## Universal rules
- <a few genuinely universal rules>
- Per-area rules live in each area's CLAUDE.md; per-file-type rules in .claude/rules/.
```

Good entry: `Triaging or fixing bugs? Read docs/issues.md`
Weak entry: `issues.md — list of open issues`

As the project accumulates feature docs, group the map (system docs / feature descriptions / plans & runbooks) so it stays scannable. If a feature folder has a nested `CLAUDE.md` pointer, the map entry is a fallback for cross-cutting prompts — keep both; they're one line each.

---

## How to write the scoped rules

**Nested `CLAUDE.md` (directory scope).** Plain markdown, no frontmatter. Two shapes:

At the top of a code area — identity + rules:

```markdown
# <repo/area name> — role + rules

This repo is **<Airflow-only / human-triggered / ...>**. <One paragraph: what runs here, what must never happen here.>

## Repo-specific rules
- <rule with the reason baked in>
- ...

## <Language> style
Shared style lives in .claude/rules/code-style.md (auto-loads). Repo-specific additions below.
- <only the deltas>
```

In a feature folder — a pointer, not a doc:

```markdown
# feature_x/

<Two lines: what this feature does.>

**Feature doc:** [`../../docs/FeatureDescription_X.md`](../../docs/FeatureDescription_X.md)

<Any feature-local gotchas worth stating inline — one or two bullets max.>
```

**`.claude/rules/` (file-type scope).** One topic per file, `paths:` glob in YAML frontmatter:

```markdown
---
paths:
  - "**/*.py"
---

# Code style
- 4-space indentation (PEP 8); enforced by ruff
- Explicit imports only — no wildcard imports
```

A rule file with **no** `paths:` field loads on every session (same as putting it in `CLAUDE.md`) — so only omit `paths:` for genuinely universal rules. Keep rules concrete enough to verify: "4-space indentation, enforced by ruff" works far better than "format code properly."

**Precedence convention:** when a nested `CLAUDE.md` and a shared rule file overlap, the nested (more specific) file states the exception explicitly — e.g. "Textual screens are a legitimate exception to functions-over-classes." Don't rely on implicit priority; say it.

---

## Migration checklist (per project)

1. **Triage the `docs/` folder.** For each file, decide: is this a *rule* (must obey) or *reference* (consult)? And: is it needed *every session*, or only for *specific tasks/files/directories*?
2. **Route the rules.** Directory-shaped rules → nested `CLAUDE.md` in that directory. File-type-shaped rules (style) → `.claude/rules/<topic>.md` with a glob. Delete the old standalone style-guide doc once its content has a scoped home.
3. **Leave reference docs in `docs/`.** Don't move them; just stop loading them eagerly. Adopt the `FeatureDescription_` / `reference_` / `plan_` / `runbook_` / `report_` naming so the map groups naturally.
4. **Write the lean root `CLAUDE.md`:** commands, layout, the trigger-oriented map, and only the universal rules.
5. **Add feature-folder pointers.** For each feature that maps to a code folder, drop in the ~10-line nested `CLAUDE.md` pointing at its feature doc.
6. **Put it all in git** — root `CLAUDE.md`, nested `CLAUDE.md`s, `.claude/rules/`, `docs/` — before declaring the migration done.
7. **Delete the old "read the docs/ folder" instruction** from `CLAUDE.md` and from team habit.
8. **Verify.** In a fresh session, run `/memory` to confirm which files are loaded, then ask Claude to summarize what it knows about the project — it will tell you exactly what context it has and what it correctly left unloaded. Then open a file in a scoped directory and confirm the nested rules appear.

---

## The tradeoff (so we go in with eyes open)

This approach shifts effort from **runtime to authoring**. "Read the docs/ folder" is zero-maintenance but expensive and attention-diluting on every task. The map is cheap at runtime but only as good as we keep it: a stale or vague map causes Claude to *miss* context it would otherwise have gotten by brute force.

That's a great trade for a stable project. For docs that churn, the rules are simple:

- **Update the map in the same commit that adds or renames a doc.** Treat the map as part of the docs, not as an afterthought. (This is why version control is required — the rule is enforced through commit discipline.)
- **Re-status, don't just accumulate.** When a plan ships, mark its map entry SHIPPED or convert the doc to a `report_`; when a runbook is retired, remove the entry. The map should describe the present.

---

## Rules of thumb

- Keep the root `CLAUDE.md` lean. Every line is paid for every session.
- Directory-shaped rules → nested `CLAUDE.md`. File-type-shaped rules → `.claude/rules/` with a glob. Reference → `docs/`, reached via the map. State/preferences → memory.
- Never maintain two copies of the same rule text — one scoped home, deltas stated locally.
- Map entries are conditions ("read X when Y"), never bare labels.
- If a teammate or a fresh agent would need it, it's a doc, not a memory. Promote durable facts out of memory into `docs/reference_*.md`.
- Splitting files into `@imports` organizes but does **not** save context — imports still load at launch. Use the map (on-demand reads) and scoped rules for actual context savings.
- Context files go in git. An un-versioned map can't be kept honest, and an un-versioned doc has no backup.
- When in doubt, ask: *does Claude need this on every task?* If no, it shouldn't be eager.
