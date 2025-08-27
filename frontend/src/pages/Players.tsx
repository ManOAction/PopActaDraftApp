import { useEffect, useMemo, useRef, useState } from "react";
import SearchModal from "@/components/SearchModal";
type Player = {
    id: number;
    name: string;
    position: string; // QB | RB | WR | ...
    team: string;
    projected_points: number;
    bye_week: number;
    drafted_status: boolean;
    target_status: "default" | "target" | "avoid";
    created_at: string;
};

const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

const cardClasses = (p: Player) =>
    cx(
        "card text-left transition shadow hover:shadow-lg border",
        // base background
        "bg-base-100 border-base-200",
        // target/avoid accents with a subtle ring
        p.target_status === "target" && "ring-2 ring-success/50",
        p.target_status === "avoid" && "ring-2 ring-error/50",
        // drafted look: darker, slightly muted
        p.drafted_status && "bg-base-200 border-base-300 opacity-75 grayscale brightness-90"
    );

export default function Players() {
    const [players, setPlayers] = useState<Player[]>([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

    // Modal/edit state
    const editDialogRef = useRef<HTMLDialogElement | null>(null);
    const [editing, setEditing] = useState<Player | null>(null);
    const [saving, setSaving] = useState(false);
    const [saveErr, setSaveErr] = useState<string | null>(null);

    useEffect(() => {
        (async () => {
            try {
                setLoading(true);
                setErr(null);
                const r = await fetch("/api/players");
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                setPlayers(await r.json());
            } catch (e: any) {
                setErr(e?.message || "Failed to load players");
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    const openEdit = (p: Player) => {
        setEditing({ ...p });
        setSaveErr(null);
        editDialogRef.current?.showModal();
    };
    const closeEdit = () => {
        editDialogRef.current?.close();
        setEditing(null);
        setSaveErr(null);
    };

    // Grouping
    const qbs = useMemo(() => players.filter(p => p.position === "QB"), [players]);
    const rbs = useMemo(() => players.filter(p => p.position === "RB"), [players]);
    const wrs = useMemo(() => players.filter(p => p.position === "WR"), [players]);
    const tes = useMemo(() => players.filter(p => p.position === "TE"), [players]);
    const flex = useMemo(() => players.filter(p => p.position === "RB" || p.position === "WR" || p.position === "TE" || p.position === "QB"), [players]);

    // Save edits (expects backend PATCH /api/players/:id)
    const onSave = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!editing) return;

        try {
            setSaving(true);
            setSaveErr(null);
            const r = await fetch(`/api/players/${editing.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: editing.name,
                    team: editing.team,
                    position: editing.position,
                    projected_points: editing.projected_points,
                    bye_week: editing.bye_week,
                    drafted_status: editing.drafted_status,
                    target_status: editing.target_status,
                }),
            });
            const data = await r.json().catch(() => null);
            if (!r.ok) {
                const detail = (data && (data.detail || JSON.stringify(data))) || `Save failed (HTTP ${r.status})`;
                throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
            }

            // Optimistic update
            setPlayers(prev => prev.map(p => (p.id === editing.id ? editing : p)));
            closeEdit();
        } catch (e: any) {
            setSaveErr(e?.message || "Save failed");
        } finally {
            setSaving(false);
        }
    };

    const Column = ({ title, items }: { title: string; items: Player[] }) => (
        <div className="space-y-3">
            <div className="sticky top-0 z-10 bg-base-200/80 backdrop-blur rounded-box px-3 py-2 shadow">
                <h3 className="font-semibold">{title} <span className="opacity-60 text-sm">({items.length})</span></h3>
            </div>
            <div className="grid gap-3">
                {items.map(p => (
                    <button key={`${title}-${p.id}`} className={cardClasses(p)} onClick={() => openEdit(p)}>
                        <div className="card-body p-4 relative">
                            {/* Drafted ribbon/flag */}
                            {p.drafted_status && (
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
                                <span>• Bye: {p.bye_week}</span>
                                {/* status badges */}
                                {p.target_status === "target" && <span className="badge badge-success">Target</span>}
                                {p.target_status === "avoid" && <span className="badge badge-error">Avoid</span>}
                            </div>
                        </div>
                    </button>
                ))}
            </div>
        </div>
    );

    return (
        <div className="max-w-8xl mx-auto p-4">
            <div className="mb-4 flex items-center justify-between">
                <h2 className="text-xl font-semibold">Players</h2>

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
                            className={`w-full text-left p-3 hover:bg-base-200 flex items-center justify-between ${active ? "bg-base-200" : ""}`}
                        >
                            <div>
                                <div className="font-medium">{p.name}</div>
                                <div className="text-sm opacity-70">
                                    {p.position} • {p.team}
                                </div>
                            </div>
                            <div className="text-sm opacity-80">Proj: {p.projected_points}</div>
                        </button>
                    )}
                    onSelect={(p) => openEdit(p)}
                />
            </div>

            {loading && <span className="loading loading-spinner" />}
            {err && <div className="alert alert-error"><span>{err}</span></div>}

            {!loading && !err && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                    <Column title="QB" items={qbs} />
                    <Column title="RB" items={rbs} />
                    <Column title="WR" items={wrs} />
                    <Column title="TE" items={tes} />
                    <Column title="FLEX (RB/WR/TE/QB)" items={flex} />
                </div>
            )}

            {/* Edit Modal */}
            <dialog ref={editDialogRef} className="modal">
                <div className="modal-box">
                    <h3 className="font-bold text-lg">Edit Player</h3>
                    {editing && (
                        <form className="mt-3 space-y-3" onSubmit={onSave}>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                <label className="form-control">
                                    <span className="label-text">Name</span>
                                    <input
                                        className="input input-bordered"
                                        value={editing.name}
                                        onChange={e => setEditing({ ...editing, name: e.target.value })}
                                    />
                                </label>
                                <label className="form-control">
                                    <span className="label-text">Team</span>
                                    <input
                                        className="input input-bordered"
                                        value={editing.team}
                                        onChange={e => setEditing({ ...editing, team: e.target.value })}
                                    />
                                </label>

                                <label className="form-control">
                                    <span className="label-text">Position</span>
                                    <select
                                        className="select select-bordered"
                                        value={editing.position}
                                        onChange={e => setEditing({ ...editing, position: e.target.value })}
                                    >
                                        <option value="QB">QB</option>
                                        <option value="RB">RB</option>
                                        <option value="WR">WR</option>
                                        {/* Intentionally omit K/DST */}
                                    </select>
                                </label>

                                <label className="form-control">
                                    <span className="label-text">Projected Points</span>
                                    <input
                                        type="number"
                                        step="0.01"
                                        className="input input-bordered"
                                        value={editing.projected_points}
                                        onChange={e => setEditing({ ...editing, projected_points: Number(e.target.value) })}
                                    />
                                </label>

                                <label className="form-control">
                                    <span className="label-text">Bye Week</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={editing.bye_week}
                                        onChange={e => setEditing({ ...editing, bye_week: Number(e.target.value) })}
                                    />
                                </label>

                                <label className="form-control">
                                    <span className="label-text">Target Status</span>
                                    <select
                                        className="select select-bordered"
                                        value={editing.target_status}
                                        onChange={e => setEditing({ ...editing, target_status: e.target.value as Player["target_status"] })}
                                    >
                                        <option value="default">default</option>
                                        <option value="target">target</option>
                                        <option value="avoid">avoid</option>
                                    </select>
                                </label>

                                <label className="label cursor-pointer gap-3">
                                    <span className="label-text">Drafted?</span>
                                    <input
                                        type="checkbox"
                                        className="toggle"
                                        checked={editing.drafted_status}
                                        onChange={e => setEditing({ ...editing, drafted_status: e.target.checked })}
                                    />
                                </label>
                            </div>

                            {saveErr && <div className="alert alert-error"><span>{saveErr}</span></div>}

                            <div className="modal-action">
                                <button type="button" className="btn btn-ghost" onClick={closeEdit} disabled={saving}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saving}>
                                    {saving ? <span className="loading loading-spinner" /> : "Save"}
                                </button>
                            </div>
                        </form>
                    )}
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>
        </div>
    );
}
