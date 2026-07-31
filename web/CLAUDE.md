# web/ — frontend rules + TypeScript style

React 19 + TypeScript + Vite 8 + Tailwind v4 + shadcn/ui. This is the **new** frontend; it shares
no code with `legacy/`.

**Status: scaffold only.** `src/App.tsx` is a placeholder. Phase 3 builds the real UI.

## Commands

| Task | Command (from `web/`) |
| --- | --- |
| Dev server | `npm run dev` |
| Build | `npm run build` |
| Typecheck | `npm run typecheck` |
| Lint | `npm run lint` |
| Format | `npm run format` / `npm run format:check` |
| Screenshot | `npm run screenshot [route] [--keep]` |

## Area rules

- **Never import from `legacy/`.**
- **Mobile-first, always.** The draft happens on a phone. Design at ~390px and let it widen;
  never build a desktop grid and hope it collapses. Verify with `npm run screenshot`, which
  captures mobile before desktop.
- **This is a slow draft** — a 1-hour pick timer over several days. Tap-speed is not a design
  constraint; **legibility of the reasoning is**. Show the pick-window math and the *why* behind
  a recommendation. Dense and deliberative beats glanceable.
- **State survives a refresh, and undo always works.** Both are draft-night requirements, not
  polish.
- **No API call sits in a blocking path.** A slow or failed Sleeper poll must never prevent the
  board from rendering what it already knows.
- **Never invent league settings.** Team count, roster slots and scoring arrive from the API.
  Do not hardcode `10` or `16` in a component.

## React

- **Define components at module scope.** A component declared inside another component's render
  body gets a new identity every render and remounts its whole subtree — LEG-10 did this with the
  board's `Column` and re-mounted the entire board on every state change.
- Function components with hooks. No class components.
- Keys are stable domain IDs (a player ID), never an array index.
- Derive state during render instead of syncing it in an effect. Effects are for subscriptions,
  timers, and imperative DOM work — not for computing values.
- Colocate: a component's types and helpers live beside it until a second consumer appears.

## TypeScript

ESLint (type-aware, see [`eslint.config.js`](eslint.config.js)) and Prettier are the enforcement
mechanism; their configs are the source of truth. Beyond what they check:

- **`any` is banned.** `unknown` plus a narrowing check is the honest version.
- **API response types are generated from or checked against the backend's Pydantic schemas** —
  never hand-duplicated. Hand-copied types are how client and server drifted apart in 2025
  (LEG-7). Until a generator exists, keep every response type in one `src/api/types.ts` so the
  drift surface is a single file.
- Prefer `type` aliases; use `interface` only when declaration merging is actually wanted.
- Discriminated unions over optional-field soup for anything with modes (loading / ready / error).
- `strict` is on and so are `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` —
  `arr[0]` is `T | undefined` and you must handle it. That is intentional; do not loosen the
  config to silence it.
- No non-null assertions (`!`) to dodge a real nullable. Narrow, or fail loudly.

## Tailwind v4 and shadcn/ui

- **There is no `tailwind.config.js`.** v4 is CSS-first: tokens live in `@theme inline` in
  [`src/index.css`](src/index.css), loaded via the `@tailwindcss/vite` plugin. Do not create a
  config file, and do not add a PostCSS pipeline.
- **Use the semantic tokens** — `bg-background`, `text-muted-foreground`, `border-border` — not
  raw palette values like `bg-zinc-900`. Both themes are already defined; raw colours break one
  of them.
- **Add shadcn components with `npx shadcn@latest add <name>`.** They land in
  `src/components/ui/` as editable source. Edit them in place; that is the point of shadcn.
  Do not wrap a component just to change a class — pass `className`, which `cn()` merges.
- Compose classes with `cn()` from [`src/lib/utils.ts`](src/lib/utils.ts) so later utilities win.
- Import via the `@/` alias, not deep relative paths.

## The design loop

`npm run screenshot` boots the dev server, captures `screenshots/mobile.png` and
`screenshots/desktop.png`, and **exits non-zero if the page logged any console or page error**.
A screenshot of a broken page still looks like a screenshot — check the exit code, not just the
image. `screenshots/` is gitignored and always regenerated.
