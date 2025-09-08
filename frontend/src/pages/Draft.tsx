import { useEffect, useMemo, useRef, useState } from "react";
import SearchModal from "@/components/SearchModal";

type Player = {
    id: number;
    name: string;
    position: string; // QB | RB | WR | TE
    team: string;
    projected_points: number;
    bye_week: number;
    actual_pick_number: number | null; // server field
    drafted: boolean; // derived client-side
    target_status: "default" | "target" | "avoid";
    created_at: string;
};

type RecentPick = {
    id: number;
    pick_number?: number;
    round_number?: number;
    player: {
        id: number;
        name: string;
        team: string;
        position: string;
    };
};

type DraftSettings = {
    total_teams: number;
    rounds: number;
    qb_slots: number;
    rb_slots: number;
    wr_slots: number;
    te_slots: number;
    flex_slots: number;
};

const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

const urgencyRing = (drop?: number) =>
    drop == null ? "" : drop >= 20 ? "ring-2 ring-warning/60" : drop >= 10 ? "ring-2 ring-info/50" : "";

const cardClasses = (p: Player, drop?: number) =>
    cx(
        "card text-left transition shadow hover:shadow-lg border",
        "bg-base-100 border-base-200",
        "cursor-pointer hover:scale-[1.02]",
        p.target_status === "target" && "ring-2 ring-success/50",
        p.target_status === "avoid" && "ring-2 ring-error/50",
        p.drafted && "bg-base-200 border-base-300 opacity-60",
        urgencyRing(drop)
    );

/** Column rule:
 * Hide any leading drafted players. Once we hit the first UNDRAFTED, show that one AND everything after it.
 * If ALL drafted, return an empty list.
 */
function applyDraftVisibilityRule(sorted: Player[]): Player[] {
    const idx = sorted.findIndex((p) => !p.drafted);
    if (idx === -1) return [];
    return sorted.slice(idx);
}

const filterAndSortPlayers = (players: Player[], position: string | string[]) => {
    const posFilter = Array.isArray(position)
        ? (p: Player) => position.includes(p.position)
        : (p: Player) => p.position === position;

    return [...players.filter(posFilter)].sort((a, b) => b.projected_points - a.projected_points);
};

export default function Draft() {
    const [players, setPlayers] = useState<Player[]>([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

    const [recent, setRecent] = useState<RecentPick[] | null>(null);
    const [recentErr, setRecentErr] = useState<string | null>(null);

    // VORP drops (split views)
    const [dropsPos, setDropsPos] = useState<Record<number, number>>({});
    const [dropsFlex, setDropsFlex] = useState<Record<number, number>>({});

    // Draft settings (for "Starters Remaining")
    const [settings, setSettings] = useState<DraftSettings | null>(null);
    const [settingsErr, setSettingsErr] = useState<string | null>(null);

    // Optional edit dialog placeholder
    const editDialogRef = useRef<HTMLDialogElement | null>(null);
    const [editing, setEditing] = useState<Player | null>(null);

    // Load players
    useEffect(() => {
        (async () => {
            try {
                setLoading(true);
                setErr(null);
                const r = await fetch("/api/players");
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const data: Player[] = await r.json();
                setPlayers(data.map((p) => ({ ...p, drafted: p.actual_pick_number != null })));
            } catch (e: any) {
                setErr(e?.message || "Failed to load players");
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    // Load draft settings
    useEffect(() => {
        (async () => {
            try {
                setSettingsErr(null);
                const r = await fetch("/api/draft-settings");
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const s: DraftSettings = await r.json();
                setSettings(s);
            } catch (e: any) {
                setSettingsErr(e?.message || "Failed to load draft settings");
            }
        })();
    }, []);

    // Load recent picks
    const fetchRecent = async () => {
        try {
            setRecentErr(null);
            const r = await fetch("/api/draft-picks/recent?limit=12");
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data: RecentPick[] = await r.json();
            setRecent(data);
        } catch (e: any) {
            setRecentErr(e?.message || "Failed to load recent picks");
            setRecent([]);
        }
    };
    useEffect(() => {
        fetchRecent().catch(() => { });
    }, []);

    // Fetch VORP drops (position & flex) whenever players change
    const refreshVorp = async () => {
        try {
            const [rp, rf] = await Promise.all([
                fetch("/api/vorp-drop?view=pos"),
                fetch("/api/vorp-drop?view=flex"),
            ]);
            if (rp.ok) setDropsPos(await rp.json());
            if (rf.ok) setDropsFlex(await rf.json());
        } catch {
            // ignore
        }
    };
    useEffect(() => {
        refreshVorp().catch(() => { });
    }, [players]);

    // Sort players by projected_points desc
    const qbsAll = useMemo(() => filterAndSortPlayers(players, "QB"), [players]);
    const rbsAll = useMemo(() => filterAndSortPlayers(players, "RB"), [players]);
    const wrsAll = useMemo(() => filterAndSortPlayers(players, "WR"), [players]);
    const tesAll = useMemo(() => filterAndSortPlayers(players, "TE"), [players]);
    const flexAll = useMemo(() => filterAndSortPlayers(players, ["RB", "WR", "TE"]), [players]);

    // Apply rule
    const qbs = useMemo(() => applyDraftVisibilityRule(qbsAll), [qbsAll]);
    const rbs = useMemo(() => applyDraftVisibilityRule(rbsAll), [rbsAll]);
    const wrs = useMemo(() => applyDraftVisibilityRule(wrsAll), [wrsAll]);
    const tes = useMemo(() => applyDraftVisibilityRule(tesAll), [tesAll]);
    const flex = useMemo(() => applyDraftVisibilityRule(flexAll), [flexAll]);

    // Compute "Starters Remaining"
    const startersRemaining = useMemo(() => {
        if (!settings) {
            return { QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0 };
        }
        const teams = settings.total_teams;
        const needQB = teams * settings.qb_slots;
        const needRB = teams * settings.rb_slots;
        const needWR = teams * settings.wr_slots;
        const needTE = teams * settings.te_slots;
        const needFLEX = teams * settings.flex_slots;

        const draftedQB = players.filter((p) => p.position === "QB" && p.drafted).length;
        const draftedRB = players.filter((p) => p.position === "RB" && p.drafted).length;
        const draftedWR = players.filter((p) => p.position === "WR" && p.drafted).length;
        const draftedTE = players.filter((p) => p.position === "TE" && p.drafted).length;

        const remQB = Math.max(0, needQB - draftedQB);
        const remRB = Math.max(0, needRB - draftedRB);
        const remWR = Math.max(0, needWR - draftedWR);
        const remTE = Math.max(0, needTE - draftedTE);

        const surplusQB = Math.max(0, draftedQB - needQB);
        const surplusRB = Math.max(0, draftedRB - needRB);
        const surplusWR = Math.max(0, draftedWR - needWR);
        const surplusTE = Math.max(0, draftedTE - needTE);
        const remFLEX = Math.max(0, needFLEX - (surplusRB + surplusWR + surplusTE));

        return { QB: remQB, RB: remRB, WR: remWR, TE: remTE, FLEX: remFLEX };
    }, [players, settings]);

    // Toggle drafted (draft/undraft)
    const toggleDrafted = async (p: Player) => {
        try {
            const r = await fetch(`/api/players/${p.id}/toggle-drafted`, { method: "POST" });
            const data = await r.json().catch(() => null);
            if (!r.ok) {
                const detail = (data && (data.detail || JSON.stringify(data))) || `Toggle failed (HTTP ${r.status})`;
                throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
            }
            const updatedServer: Player = data.player as any;
            const updated: Player = { ...updatedServer, drafted: updatedServer.actual_pick_number != null };
            setPlayers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));

            // refresh UI side-data
            fetchRecent().catch(() => { });
            refreshVorp().catch(() => { });
        } catch (e) {
            console.error(e);
        }
    };

    const Column = ({
        title,
        items,
        remaining,
        useFlexDrops = false,
    }: {
        title: string;
        items: Player[];
        remaining: number;
        useFlexDrops?: boolean; // FLEX column uses flex drops; others use position drops
    }) => (
        <div className="space-y-3">
            <div className="sticky top-0 z-10 bg-base-200/80 backdrop-blur rounded-box px-3 py-2 shadow">
                <h3 className="font-semibold flex items-center justify-between">
                    <span>
                        {title} <span className="opacity-60 text-sm">({items.length})</span>
                    </span>
                    <span className="text-xs opacity-80">Starters Remaining: {remaining}</span>
                </h3>
            </div>
            <div className="grid gap-3">
                {items.map((p) => {
                    const drop = (useFlexDrops ? dropsFlex : dropsPos)[p.id];
                    return (
                        <div key={`${title}-${p.id}`} className={cardClasses(p, drop)} onClick={() => toggleDrafted(p)}>
                            <div className="card-body p-4 relative">
                                {p.drafted && (
                                    <div className="absolute right-2 top-2">
                                        <span className="badge badge-neutral">Drafted</span>
                                    </div>
                                )}
                                <div className="flex items-center justify-between">
                                    <div className="font-medium">{p.name}</div>
                                    <div className="badge">{p.team}</div>
                                </div>
                                <div className="flex items-center gap-2 text-sm opacity-80">
                                    <span>Proj: {p.projected_points}</span>
                                    {drop != null && <span className="badge badge-outline">Δ {drop.toFixed(1)}</span>}
                                    <span>• Bye: {p.bye_week}</span>
                                    {p.target_status === "target" && <span className="badge badge-success">Target</span>}
                                    {p.target_status === "avoid" && <span className="badge badge-error">Avoid</span>}
                                </div>
                            </div>
                        </div>
                    );
                })}
                {items.length === 0 && <div className="text-sm opacity-70 p-2">All players drafted so far in this position.</div>}
            </div>
        </div>
    );

    return (
        <div className="max-w-8xl mx-auto p-4 space-y-4">
            {/* Header row */}
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold">Draft</h2>

                <SearchModal<Player>
                    triggerLabel="Search"
                    title="Search Players"
                    placeholder="Type a name, team, or position…"
                    items={players}
                    getKey={(p) => p.id}
                    filter={(p, term) =>
                        p.name.toLowerCase().includes(term) ||
                        p.team.toLowerCase().includes(term) ||
                        p.position.toLowerCase().includes(term)
                    }
                    renderItem={({ item: p, active, onChoose }) => (
                        <button
                            type="button"
                            onClick={onChoose}
                            className={`w-full text-left p-3 hover:bg-base-200 flex items-center justify-between ${active ? "bg-base-200" : ""
                                }`}
                        >
                            <div>
                                <div className="font-medium">{p.name}</div>
                                <div className="text-sm opacity-70">
                                    {p.position} • {p.team}
                                </div>
                            </div>
                            <div className="text-sm opacity-80">
                                {p.drafted ? <span className="badge badge-neutral">Drafted</span> : <>Proj: {p.projected_points}</>}
                            </div>
                        </button>
                    )}
                    onSelect={(p) => toggleDrafted(p)}
                />
            </div>

            {/* Optionally show settings load error */}
            {settingsErr && (
                <div className="alert alert-warning">
                    <span>{settingsErr}</span>
                </div>
            )}

            {/* Recent Draft Picks Bar */}
            <div className="card bg-base-100 shadow">
                <div className="card-body py-3">
                    <div className="flex items-center justify-between">
                        <h3 className="card-title text-base">Recent Draft Picks</h3>
                        {recentErr && <div className="text-error text-sm">{recentErr}</div>}
                    </div>
                    <div className="overflow-x-auto no-scrollbar">
                        <div className="flex gap-3 py-1">
                            {recent && recent.length > 0 ? (
                                recent.map((pick) => (
                                    <div key={pick.id} className="badge badge-outline gap-2 px-3 py-3">
                                        <span className="font-medium">{pick.player.name}</span>
                                        <span className="opacity-70">
                                            {pick.player.position} • {pick.player.team}
                                        </span>
                                        {pick.round_number != null && pick.pick_number != null && (
                                            <span className="opacity-60">R{pick.round_number}P{pick.pick_number}</span>
                                        )}
                                    </div>
                                ))
                            ) : (
                                <div className="opacity-70 text-sm">No recent picks</div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {loading && <span className="loading loading-spinner" />}
            {err && (
                <div className="alert alert-error">
                    <span>{err}</span>
                </div>
            )}

            {/* Columns */}
            {!loading && !err && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                    <Column title="QB" items={qbs} remaining={startersRemaining.QB} />
                    <Column title="RB" items={rbs} remaining={startersRemaining.RB} />
                    <Column title="WR" items={wrs} remaining={startersRemaining.WR} />
                    <Column title="TE" items={tes} remaining={startersRemaining.TE} />
                    <Column
                        title="FLEX (RB/WR/TE)"
                        items={flex}
                        remaining={startersRemaining.FLEX}
                        useFlexDrops
                    />
                </div>
            )}

            {/* (Optional) Edit dialog placeholder */}
            <dialog ref={editDialogRef} className="modal">
                <div className="modal-box">
                    <h3 className="font-bold text-lg">Edit Player</h3>
                    <div className="modal-action">
                        <form method="dialog">
                            <button className="btn">Close</button>
                        </form>
                    </div>
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>
        </div>
    );
}
