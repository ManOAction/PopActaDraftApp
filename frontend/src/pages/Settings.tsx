import { useEffect, useRef, useState } from "react";

type DraftSettings = {
    id: number;
    total_teams: number;
    rounds: number;
    qb_slots: number;
    rb_slots: number;
    wr_slots: number;
    te_slots: number;
    flex_slots: number;

    // You can keep these locally if you still want to show them in the UI,
    // but they are NOT persisted by the backend anymore:
    current_pick?: number;
    is_active?: boolean;
};

type ResetResult = {
    message: string;
    inserted: number;
};

export default function Settings() {
    const [settings, setSettings] = useState<DraftSettings | null>(null);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

    // Edit form state
    const [saving, setSaving] = useState(false);
    const [saveErr, setSaveErr] = useState<string | null>(null);
    const [saveOk, setSaveOk] = useState<string | null>(null);

    // Upload modal state
    const dialogRef = useRef<HTMLDialogElement | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [uploadErr, setUploadErr] = useState<string | null>(null);
    const [result, setResult] = useState<ResetResult | null>(null);

    // Reset drafted status modal state
    const resetDialogRef = useRef<HTMLDialogElement | null>(null);
    const [resetting, setResetting] = useState(false);
    const [resetErr, setResetErr] = useState<string | null>(null);
    const [resetCount, setResetCount] = useState<number | null>(null);

    // Load settings
    useEffect(() => {
        (async () => {
            try {
                setLoading(true);
                setErr(null);
                const r = await fetch("/api/draft-settings");
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const data = await r.json();
                // ensure sensible defaults if backend adds columns later
                setSettings({
                    qb_slots: 1,
                    rb_slots: 2,
                    wr_slots: 2,
                    te_slots: 1,
                    flex_slots: 2,
                    ...data,
                });
            } catch (e: any) {
                setErr(e?.message || "Failed to load settings");
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    // Helpers
    const setField = <K extends keyof DraftSettings>(key: K, val: DraftSettings[K]) => {
        setSettings((s) => (s ? { ...s, [key]: val } : s));
    };

    const parseIntClamp = (v: string, min: number, max: number) => {
        const n = Number.parseInt(v, 10);
        if (Number.isNaN(n)) return min;
        return Math.min(max, Math.max(min, n));
    };

    // Save settings (PATCH /api/draft-settings)
    const onSaveSettings = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!settings) return;
        setSaveErr(null);
        setSaveOk(null);
        try {
            setSaving(true);
            const r = await fetch("/api/draft-settings", {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    total_teams: settings.total_teams,
                    rounds: settings.rounds,
                    // NOTE: do NOT send current_pick or is_active — they are not persisted on the backend
                    qb_slots: settings.qb_slots,
                    rb_slots: settings.rb_slots,
                    wr_slots: settings.wr_slots,
                    te_slots: settings.te_slots,
                    flex_slots: settings.flex_slots,
                }),
            });
            const data = await r.json().catch(() => null);
            if (!r.ok) {
                const detail = (data && (data.detail || JSON.stringify(data))) || `Save failed (HTTP ${r.status})`;
                throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
            }
            setSettings(data);
            setSaveOk("Settings saved");
        } catch (e: any) {
            setSaveErr(e?.message || "Failed to save settings");
        } finally {
            setSaving(false);
        }
    };

    // Upload CSV modal controls
    const openModal = () => {
        setFile(null);
        setUploadErr(null);
        setResult(null);
        dialogRef.current?.showModal();
    };
    const closeModal = () => dialogRef.current?.close();

    // Reset drafted modal controls
    const openResetModal = () => {
        setResetErr(null);
        setResetCount(null);
        resetDialogRef.current?.showModal();
    };
    const closeResetModal = () => resetDialogRef.current?.close();

    // Submit CSV
    const onSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setUploadErr(null);
        setResult(null);
        if (!file) {
            setUploadErr("Please choose a CSV file first.");
            return;
        }
        const form = new FormData();
        form.append("file", file);
        try {
            setUploading(true);
            const r = await fetch("/api/reset-players", { method: "POST", body: form });
            const data = await r.json().catch(() => null);
            if (!r.ok) {
                const detail =
                    (data && (data.detail?.error || data.detail || JSON.stringify(data))) ||
                    `Upload failed (HTTP ${r.status})`;
                throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
            }
            setResult(data as ResetResult);
        } catch (e: any) {
            setUploadErr(e?.message || "Upload failed");
        } finally {
            setUploading(false);
        }
    };

    // Confirm reset drafted — FIXED ENDPOINT PATH
    const onConfirmReset = async () => {
        setResetErr(null);
        setResetCount(null);
        try {
            setResetting(true);
            const r = await fetch("/api/reset-drafted-status", { method: "POST" });
            const data = await r.json().catch(() => null);
            if (!r.ok) {
                const detail =
                    (data && (data.detail?.error || data.detail || JSON.stringify(data))) ||
                    `Reset failed (HTTP ${r.status})`;
                throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
            }
            setResetCount((data && data.updated) ?? 0);
        } catch (e: any) {
            setResetErr(e?.message || "Reset failed");
        } finally {
            setResetting(false);
        }
    };

    const startersSummary = (() => {
        if (!settings) return "";
        const t = settings.total_teams;
        const qb = t * settings.qb_slots;
        const rb = t * settings.rb_slots;
        const wr = t * settings.wr_slots;
        const te = t * settings.te_slots;
        const flex = t * settings.flex_slots;
        return `League starters → QB ${qb}, RB ${rb}, WR ${wr}, TE ${te}, FLEX ${flex}`;
    })();

    return (
        <div className="max-w-5xl mx-auto p-4 space-y-6">
            {/* Draft Settings (editable) */}
            <div className="card bg-base-100 shadow">
                <div className="card-body">
                    <h2 className="card-title">Draft Settings</h2>
                    {loading && <span className="loading loading-spinner" />}
                    {err && (
                        <div className="alert alert-error">
                            <span>{err}</span>
                        </div>
                    )}

                    {!loading && !err && settings && (
                        <form className="space-y-4" onSubmit={onSaveSettings}>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label className="form-control">
                                    <span className="label-text">Total Teams</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.total_teams}
                                        onChange={(e) => setField("total_teams", parseIntClamp(e.target.value, 1, 24))}
                                    />
                                </label>

                                <label className="form-control">
                                    <span className="label-text">Rounds</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.rounds}
                                        onChange={(e) => setField("rounds", parseIntClamp(e.target.value, 1, 40))}
                                    />
                                </label>
                            </div>

                            <div className="divider">Roster Slots (per team)</div>

                            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                                <label className="form-control">
                                    <span className="label-text">QB Slots</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.qb_slots}
                                        onChange={(e) => setField("qb_slots", parseIntClamp(e.target.value, 0, 3))}
                                    />
                                </label>
                                <label className="form-control">
                                    <span className="label-text">RB Slots</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.rb_slots}
                                        onChange={(e) => setField("rb_slots", parseIntClamp(e.target.value, 0, 6))}
                                    />
                                </label>
                                <label className="form-control">
                                    <span className="label-text">WR Slots</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.wr_slots}
                                        onChange={(e) => setField("wr_slots", parseIntClamp(e.target.value, 0, 6))}
                                    />
                                </label>
                                <label className="form-control">
                                    <span className="label-text">TE Slots</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.te_slots}
                                        onChange={(e) => setField("te_slots", parseIntClamp(e.target.value, 0, 3))}
                                    />
                                </label>
                                <label className="form-control">
                                    <span className="label-text">FLEX Slots</span>
                                    <input
                                        type="number"
                                        className="input input-bordered"
                                        value={settings.flex_slots}
                                        onChange={(e) => setField("flex_slots", parseIntClamp(e.target.value, 0, 3))}
                                    />
                                </label>
                            </div>

                            <p className="text-sm opacity-70">{startersSummary}</p>

                            {saveErr && (
                                <div className="alert alert-error">
                                    <span>{saveErr}</span>
                                </div>
                            )}
                            {saveOk && (
                                <div className="alert alert-success">
                                    <span>{saveOk}</span>
                                </div>
                            )}

                            <div className="mt-2">
                                <button className="btn btn-primary" type="submit" disabled={saving}>
                                    {saving ? <span className="loading loading-spinner" /> : "Save Settings"}
                                </button>
                            </div>
                        </form>
                    )}
                </div>
            </div>

            {/* Upload players CSV */}
            <div className="card bg-base-100 shadow">
                <div className="card-body">
                    <div className="flex items-center justify-between">
                        <h3 className="card-title">Player Data</h3>
                        <button className="btn btn-primary" onClick={openModal}>
                            Upload Players CSV
                        </button>
                    </div>
                    <p className="text-sm opacity-70">
                        Upload a CSV to replace all players. Expected columns (in order):{" "}
                        <code>name, position, team, projected_points, bye_week</code>
                    </p>

                    {result && (
                        <div className="alert alert-success mt-3">
                            <span>
                                {result.message} Inserted: <b>{result.inserted}</b>
                            </span>
                        </div>
                    )}
                    {uploadErr && (
                        <div className="alert alert-error mt-3">
                            <span>{uploadErr}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Draft actions */}
            <div className="card bg-base-100 shadow">
                <div className="card-body">
                    <div className="flex items-center justify-between">
                        <h3 className="card-title">Draft Actions</h3>
                        <button className="btn" onClick={openResetModal}>
                            Reset Drafted Status
                        </button>
                    </div>
                    <p className="text-sm opacity-70">
                        Clears <code>actual_pick_number</code> for <b>all</b> players.
                    </p>

                    {resetCount !== null && (
                        <div className="alert alert-success mt-3">
                            <span>
                                Drafted status reset (cleared picks) for <b>{resetCount}</b> players.
                            </span>
                        </div>
                    )}
                    {resetErr && (
                        <div className="alert alert-error mt-3">
                            <span>{resetErr}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Upload Modal */}
            <dialog ref={dialogRef} className="modal">
                <div className="modal-box">
                    <h3 className="font-bold text-lg">Upload Players CSV</h3>
                    <p className="py-2 text-sm opacity-70">This will replace all players in the database.</p>

                    <form className="mt-2 space-y-4" onSubmit={onSubmit}>
                        <input
                            type="file"
                            accept=".csv,text/csv"
                            className="file-input file-input-bordered w-full"
                            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                            disabled={uploading}
                        />

                        <div className="modal-action">
                            <button type="button" className="btn btn-ghost" onClick={closeModal} disabled={uploading}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={uploading}>
                                {uploading ? <span className="loading loading-spinner" /> : "Upload"}
                            </button>
                        </div>
                    </form>

                    {uploadErr && (
                        <div className="alert alert-error mt-3">
                            <span>{uploadErr}</span>
                        </div>
                    )}
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>

            {/* Reset Drafted Modal */}
            <dialog ref={resetDialogRef} className="modal">
                <div className="modal-box">
                    <h3 className="font-bold text-lg">Reset Drafted Status</h3>
                    <p className="py-2 text-sm opacity-70">
                        This will clear <code>actual_pick_number</code> (i.e., undraft) for <b>all</b> players.
                    </p>
                    <div className="modal-action">
                        <button className="btn btn-ghost" onClick={closeResetModal} disabled={resetting}>
                            Cancel
                        </button>
                        <button className="btn btn-primary" onClick={onConfirmReset} disabled={resetting}>
                            {resetting ? <span className="loading loading-spinner" /> : "Confirm"}
                        </button>
                    </div>

                    {resetErr && (
                        <div className="alert alert-error mt-3">
                            <span>{resetErr}</span>
                        </div>
                    )}
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>
        </div>
    );
}
