import { useEffect, useState } from "react";

export default function WelcomeStrip() {
    const [text, setText] = useState<string>("");
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

    async function load() {
        try {
            setLoading(true);
            setErr(null);
            const r = await fetch("/api/welcome");
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            setText(data.message ?? "");
        } catch (e: any) {
            setErr(e?.message || "Failed to load welcome message");
            setText("");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => { load(); }, []);

    return (
        <div className="max-w-5xl mx-auto px-4 pt-4">
            <div className="alert bg-base-100 shadow">
                <span className="font-medium">
                    {loading ? "Loading welcome..." : (text || "Couldn't load welcome message...")}
                </span>
                <div className="ml-auto">
                    <button className="btn btn-sm" onClick={load} disabled={loading}>
                        {loading ? <span className="loading loading-spinner loading-sm" /> : "New message"}
                    </button>
                </div>
            </div>
            {err && <div className="alert alert-error mt-2"><span>{err}</span></div>}
        </div>
    );
}