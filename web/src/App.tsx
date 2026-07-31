import { cn } from '@/lib/utils'

/**
 * Placeholder shell. Phase 3 replaces this entirely — it exists so the scaffold
 * has something to render, typecheck, lint, and screenshot.
 */
export default function App() {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col gap-6 px-4 py-10">
      <header className="flex flex-col gap-1">
        <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
          Pop Acta Premier League
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance">Draft Copilot</h1>
        <p className="text-sm text-muted-foreground">
          Superflex &middot; 10 teams &middot; 16 rounds &middot; Half&#8209;PPR
        </p>
      </header>

      <section
        className={cn(
          'rounded-xl border bg-card p-5 text-card-foreground',
          'flex flex-col gap-2 shadow-sm',
        )}
      >
        <h2 className="font-medium">Scaffold only</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          No draft logic exists yet. Phase 1 builds the domain core (seat, snake order, picks until
          your next turn); Phase 2 builds the recommendation engine.
        </p>
      </section>
    </main>
  )
}
