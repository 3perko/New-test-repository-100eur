import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";

export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={`h-4 w-4 animate-spin ${className}`} aria-label="Načítavam" />;
}

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2.5 dark:border-slate-800">
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const badgeColors: Record<string, string> = {
  gray: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  red: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  blue: "bg-brand-100 text-brand-700 dark:bg-brand-700/40 dark:text-brand-100",
};

export function Badge({ color = "gray", children }: { color?: keyof typeof badgeColors; children: ReactNode }) {
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${badgeColors[color]}`}>{children}</span>;
}

export function Modal({ open, onClose, title, children, footer, wide = false }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-[8vh]" onMouseDown={onClose}>
      <div
        className={`card w-full ${wide ? "max-w-3xl" : "max-w-lg"} shadow-xl`}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h2 className="font-semibold">{title}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Zavrieť"><X className="h-4 w-4" /></button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3 dark:border-slate-800">{footer}</footer>}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children, actions }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; actions?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onMouseDown={onClose}>
      <aside
        className="flex h-full w-full max-w-xl flex-col bg-white shadow-2xl dark:bg-slate-900"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h2 className="truncate font-semibold">{title}</h2>
          <div className="flex items-center gap-2">
            {actions}
            <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Zavrieť"><X className="h-4 w-4" /></button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  );
}

// ----------------------------------------------------------------------------- toasts
type Toast = { id: number; kind: "ok" | "error" | "info"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), kind === "error" ? 8000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex max-w-sm flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={`card flex items-start gap-2 px-3 py-2 text-sm shadow-lg ${t.kind === "error" ? "border-red-300" : ""}`}
            role="status"
          >
            {t.kind === "ok" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />}
            {t.kind === "error" && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />}
            {t.kind === "info" && <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastCtx);
  return {
    ok: (t: string) => push("ok", t),
    error: (t: unknown) => push("error", t instanceof Error ? t.message : String(t)),
    info: (t: string) => push("info", t),
  };
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-sm text-slate-500">{children}</div>;
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "red" | "green" }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-xl font-semibold tabular-nums ${tone === "red" ? "text-red-600" : tone === "green" ? "text-emerald-600" : ""}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function PageHeader({ title, actions, sub }: { title: ReactNode; actions?: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="page-title">{title}</h1>
        {sub && <p className="mt-0.5 text-sm text-slate-500">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
