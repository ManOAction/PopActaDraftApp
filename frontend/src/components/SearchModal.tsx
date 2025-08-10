import { useEffect, useMemo, useRef, useState } from "react";

type RenderItemProps<T> = {
    item: T;
    active: boolean;
    onChoose: (item: T) => void;
};

export type SearchModalProps<T> = {
    /** Button text */
    triggerLabel?: string;
    /** Button style classes (DaisyUI) */
    triggerClassName?: string;
    /** Modal title */
    title?: string;
    /** Input placeholder */
    placeholder?: string;
    /** Items to search */
    items: T[];
    /** Convert an item to its unique key */
    getKey: (item: T) => string | number;
    /** Filter function (default: name/team/position style contains) */
    filter?: (item: T, query: string) => boolean;
    /** What to render for each result row */
    renderItem: (props: RenderItemProps<T>) => JSX.Element;
    /** Called when user chooses an item (click or Enter) */
    onSelect: (item: T) => void;
};

export default function SearchModal<T>({
    triggerLabel = "Search",
    triggerClassName = "btn btn-primary",
    title = "Search",
    placeholder = "Type to search…",
    items,
    getKey,
    filter,
    renderItem,
    onSelect,
}: SearchModalProps<T>) {
    const dialogRef = useRef<HTMLDialogElement | null>(null);
    const inputRef = useRef<HTMLInputElement | null>(null);
    const [q, setQ] = useState("");
    const [activeIdx, setActiveIdx] = useState(0);

    const results = useMemo(() => {
        const term = q.trim().toLowerCase();
        if (!term) return [];
        const matches = (filter
            ? items.filter((i) => filter(i, term))
            : items.filter((i) => JSON.stringify(i).toLowerCase().includes(term))
        );
        return matches.slice(0, 50);
    }, [q, items, filter]);

    const open = () => {
        setQ("");
        setActiveIdx(0);
        dialogRef.current?.showModal();
    };

    const close = () => {
        dialogRef.current?.close();
    };

    // Focus the input when modal opens
    useEffect(() => {
        const el = dialogRef.current;
        if (!el) return;
        const onOpen = () => setTimeout(() => inputRef.current?.focus(), 0);
        el.addEventListener("close", () => setQ(""));
        el.addEventListener("cancel", () => setQ(""));
        el.addEventListener("click", (e) => {
            // click outside to close
            if ((e.target as HTMLElement).classList.contains("modal-backdrop")) close();
        });
        el.addEventListener("animationend", onOpen, { once: true } as any);
        return () => { };
    }, []);

    const choose = (item: T) => {
        onSelect(item);
        close();
    };

    const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (!results.length) return;
        if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIdx((i) => (i + 1) % results.length);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIdx((i) => (i - 1 + results.length) % results.length);
        } else if (e.key === "Enter") {
            e.preventDefault();
            choose(results[activeIdx]);
        }
    };

    return (
        <>
            <button className={triggerClassName} onClick={open}>
                {triggerLabel}
            </button>

            <dialog ref={dialogRef} className="modal">
                <div className="modal-box">
                    <h3 className="font-bold text-lg">{title}</h3>
                    <div className="mt-3">
                        <input
                            ref={inputRef}
                            type="text"
                            value={q}
                            onChange={(e) => {
                                setQ(e.target.value);
                                setActiveIdx(0);
                            }}
                            onKeyDown={onKeyDown}
                            placeholder={placeholder}
                            className="input input-bordered w-full"
                        />
                        <div className="mt-3 max-h-80 overflow-auto divide-y rounded-box border">
                            {q.trim() && results.length === 0 && (
                                <div className="p-3 opacity-70">No matches</div>
                            )}
                            {results.map((item, i) => (
                                <div
                                    key={getKey(item)}
                                    className={`w-full ${i === activeIdx ? "bg-base-200" : ""}`}
                                >
                                    {renderItem({
                                        item,
                                        active: i === activeIdx,
                                        onChoose: () => choose(item),
                                    })}
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="modal-action">
                        <button className="btn" onClick={close}>Close</button>
                    </div>
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>
        </>
    );
}
