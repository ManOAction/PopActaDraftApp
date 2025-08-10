import { useEffect, useRef, useState } from "react";

type DraftSettings = {
    id: number;
    total_teams: number;
    rounds: number;
    current_pick: number;
    is_active: boolean;
};

type ResetResult = {
    message: string;
    inserted: number;
};

export default function Settings() {
    const [settings, setSettings] = useState<DraftSettings | null>(null);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

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

    useEffect(() => {
        (async () => {
            try {
                setLoading(true);
                setErr(null);
                const r = await fetch("/api/draft-settings");
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                setSettings(await r.json());
            } catch (e: any) {
                setErr(e?.message || "Failed to load settings");
            } finally {
                setLoading(false);
            }
        })();
    }, []);

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

    // Confirm reset drafted
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

    return (
        <div className="max-w-5xl mx-auto p-4 space-y-6">
            {/* Settings summary */}
            <div className="card bg-base-100 shadow">
                <div className="card-body">
                    <h2 className="card-title">Settings</h2>
                    {loading && <span className="loading loading-spinner" />}
                    {err && <div className="alert alert-error"><span>{err}</span></div>}
                    {!loading && !err && settings && (
                        <ul className="list-disc pl-6">
                            <li>Total teams: {settings.total_teams}</li>
                            <li>Rounds: {settings.rounds}</li>
                            <li>Current pick: {settings.current_pick}</li>
                            <li>Active: {settings.is_active ? "Yes" : "No"}</li>
                        </ul>
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

            {/* Reset drafted status */}
            <div className="card bg-base-100 shadow">
                <div className="card-body">
                    <div className="flex items-center justify-between">
                        <h3 className="card-title">Draft Actions</h3>
                        <button className="btn" onClick={openResetModal}>
                            Reset Drafted Status
                        </button>
                    </div>
                    <p className="text-sm opacity-70">
                        Set <code>drafted_status</code> to <b>false</b> for all players.
                    </p>

                    {resetCount !== null && (
                        <div className="alert alert-success mt-3">
                            <span>Drafted status reset for <b>{resetCount}</b> players.</span>
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
                    <p className="py-2 text-sm opacity-70">
                        This will replace all players in the database.
                    </p>

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

                    {uploadErr && <div className="alert alert-error mt-3"><span>{uploadErr}</span></div>}
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
                        This will set <code>drafted_status = false</code> for <b>all</b> players.
                    </p>
                    <div className="modal-action">
                        <button className="btn btn-ghost" onClick={closeResetModal} disabled={resetting}>
                            Cancel
                        </button>
                        <button className="btn btn-primary" onClick={onConfirmReset} disabled={resetting}>
                            {resetting ? <span className="loading loading-spinner" /> : "Confirm"}
                        </button>
                    </div>

                    {resetErr && <div className="alert alert-error mt-3"><span>{resetErr}</span></div>}
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>
        </div>
    );
}
