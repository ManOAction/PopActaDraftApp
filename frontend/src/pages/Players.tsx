import { useEffect, useState } from "react";

type Player = {
    id: number;
    name: string;
    position: string;
    team: string;
    projected_points: number;
    bye_week: number;
    drafted_status: boolean;
    target_status: "default" | "target" | "avoid";
    created_at: string;
};

export default function Players() {
    const [players, setPlayers] = useState<Player[]>([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

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

    return (
        <div className="max-w-5xl mx-auto p-4">
            <div className="card bg-base-100 shadow">
                <div className="card-body">
                    <h2 className="card-title">Players</h2>
                    {loading && <span className="loading loading-spinner" />}
                    {err && <div className="alert alert-error"><span>{err}</span></div>}
                    {!loading && !err && (
                        <div className="overflow-x-auto">
                            <table className="table">
                                <thead>
                                    <tr>
                                        <th>Name</th><th>Pos</th><th>Team</th><th>Proj</th><th>Bye</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {players.map(p => (
                                        <tr key={p.id}>
                                            <td>{p.name}</td>
                                            <td>{p.position}</td>
                                            <td>{p.team}</td>
                                            <td>{p.projected_points}</td>
                                            <td>{p.bye_week}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
