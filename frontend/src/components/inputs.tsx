import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronDown, X } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate, fmtNum, parseDate, parseNum, parseTime } from "@/lib/format";
import type { FieldMeta, Option } from "@/lib/types";

// ----------------------------------------------------------------------------- Date (DD.MM.RRRR)
export function DateInput({ value, onChange, id, disabled, placeholder = "DD.MM.RRRR", autoFocus }: {
  value: string | null | undefined; onChange: (v: string | null) => void; id?: string; disabled?: boolean;
  placeholder?: string; autoFocus?: boolean;
}) {
  const [text, setText] = useState(fmtDate(value));
  const [bad, setBad] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setText(fmtDate(value));
    setBad(false);
  }, [value]);
  const commit = () => {
    if (!text.trim()) {
      setBad(false);
      if (value) onChange(null);
      return;
    }
    const iso = parseDate(text);
    if (iso) {
      setBad(false);
      setText(fmtDate(iso));
      if (iso !== value) onChange(iso);
    } else setBad(true);
  };
  return (
    <div className="relative">
      <input
        id={id}
        className={`input pr-8 ${bad ? "border-red-500" : ""}`}
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        inputMode="numeric"
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        title="Formát DD.MM.RRRR, napr. 5.11. alebo „dnes“"
      />
      <button
        type="button"
        tabIndex={-1}
        className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
        onClick={() => {
          const el = picker.current;
          if (el && "showPicker" in el) (el as HTMLInputElement & { showPicker: () => void }).showPicker();
        }}
        disabled={disabled}
        aria-label="Kalendár"
      >
        <CalendarDays className="h-4 w-4" />
      </button>
      <input
        ref={picker}
        type="date"
        tabIndex={-1}
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-0 w-0 opacity-0"
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
      />
    </div>
  );
}

// ----------------------------------------------------------------------------- Time (24h, no AM/PM)
const TIMES = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

export function TimeInput({ value, onChange, id, disabled }: {
  value: string | null | undefined; onChange: (v: string | null) => void; id?: string; disabled?: boolean;
}) {
  const [text, setText] = useState(value ? String(value).slice(0, 5) : "");
  const [bad, setBad] = useState(false);
  const [open, setOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setText(value ? String(value).slice(0, 5) : "");
    setBad(false);
  }, [value]);
  const commit = (t = text) => {
    if (!t.trim()) {
      setBad(false);
      if (value) onChange(null);
      return;
    }
    const v = parseTime(t);
    if (v) {
      setBad(false);
      setText(v);
      if (v !== value) onChange(v);
    } else setBad(true);
  };
  useEffect(() => {
    if (open && listRef.current) {
      const target = listRef.current.querySelector(`[data-t="${(text || "07:00").slice(0, 2)}:00"]`);
      target?.scrollIntoView({ block: "center" });
    }
  }, [open, text]);
  return (
    <div className="relative">
      <input
        id={id}
        className={`input pl-2 pr-6 tabular-nums ${bad ? "border-red-500" : ""}`}
        value={text}
        disabled={disabled}
        placeholder="hh:mm"
        inputMode="numeric"
        maxLength={5}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          setTimeout(() => setOpen(false), 150);
          commit();
        }}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        title="24-hodinový čas, napr. 7:30 alebo 1630"
      />
      <button type="button" tabIndex={-1} disabled={disabled}
        className="absolute right-0.5 top-1/2 -translate-y-1/2 text-slate-400" onClick={() => setOpen((o) => !o)}
        aria-label="Výber času">
        <ChevronDown className="h-4 w-4" />
      </button>
      {open && (
        <div ref={listRef} className="card absolute z-30 mt-1 max-h-56 w-28 overflow-y-auto py-1 shadow-lg">
          {TIMES.map((t) => (
            <button type="button" key={t} data-t={t}
              className="block w-full px-3 py-1 text-left text-sm tabular-nums hover:bg-slate-100 dark:hover:bg-slate-800"
              onMouseDown={(e) => {
                e.preventDefault();
                setText(t);
                commit(t);
                setOpen(false);
              }}>
              {t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------- Number (decimal comma)
export function NumberInput({ value, onChange, id, disabled, decimals, suffix, placeholder }: {
  value: number | null | undefined; onChange: (v: number | null) => void; id?: string; disabled?: boolean;
  decimals?: number; suffix?: string; placeholder?: string;
}) {
  const show = (v: number | null | undefined) =>
    v === null || v === undefined ? "" : fmtNum(v, decimals).replace(/ /g, " ");
  const [text, setText] = useState(show(value));
  const [focus, setFocus] = useState(false);
  useEffect(() => {
    if (!focus) setText(show(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const commit = () => {
    const n = parseNum(text);
    if (n === null && text.trim()) return;
    if (n !== value) onChange(n);
    setText(show(n));
  };
  return (
    <div className="relative">
      <input
        id={id}
        className={`input text-right tabular-nums ${suffix ? "pr-8" : ""}`}
        value={text}
        disabled={disabled}
        inputMode="decimal"
        placeholder={placeholder}
        onFocus={() => setFocus(true)}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          setFocus(false);
          commit();
        }}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
      {suffix && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400">{suffix}</span>}
    </div>
  );
}

// ----------------------------------------------------------------------------- Ref select (async combobox)
function useOptions(entity: string, q: string, enabled: boolean, includeInactive = false) {
  return useQuery({
    queryKey: ["options", entity, q, includeInactive],
    queryFn: () => api.get<Option[]>(`/api/options/${entity}`, { q, include_inactive: includeInactive, limit: 50 }),
    enabled,
    staleTime: 30_000,
  });
}

function useLabels(entity: string, ids: number[]) {
  const key = ids.slice().sort().join(",");
  return useQuery({
    queryKey: ["options-ids", entity, key],
    queryFn: () => api.get<Option[]>(`/api/options/${entity}`, { ids: key }),
    enabled: ids.length > 0,
    staleTime: 60_000,
  });
}

export function RefSelect({ entity, value, onChange, id, disabled, placeholder = "Vyberte…", label, autoFocus }: {
  entity: string; value: number | null | undefined; onChange: (v: number | null, opt?: Option) => void; id?: string;
  disabled?: boolean; placeholder?: string; label?: string | null; autoFocus?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const opts = useOptions(entity, q, open);
  const known = useLabels(entity, value ? [value] : []);
  const current = label ?? known.data?.find((o) => o.value === value)?.label ?? (value ? `#${value}` : "");
  const items = opts.data ?? [];
  const pick = (o: Option | null) => {
    onChange(o ? o.value : null, o ?? undefined);
    setOpen(false);
    setQ("");
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHi((h) => Math.min(h + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHi((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (items[hi]) pick(items[hi]);
    } else if (e.key === "Escape") setOpen(false);
  };
  return (
    <div className="relative">
      <input
        id={id}
        className="input pr-12"
        disabled={disabled}
        autoFocus={autoFocus}
        value={open ? q : current}
        placeholder={open ? "Hľadať…" : placeholder}
        onFocus={() => {
          setOpen(true);
          setHi(0);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setQ(e.target.value);
          setHi(0);
          setOpen(true);
        }}
        onKeyDown={onKey}
        autoComplete="off"
      />
      {value && !disabled && (
        <button type="button" tabIndex={-1} className="absolute right-7 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          onMouseDown={(e) => {
            e.preventDefault();
            pick(null);
          }} aria-label="Vymazať">
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      {open && (
        <div className="card absolute z-30 mt-1 max-h-64 w-full min-w-48 overflow-y-auto py-1 shadow-lg">
          {opts.isLoading && <div className="px-3 py-1.5 text-sm text-slate-500">Načítavam…</div>}
          {!opts.isLoading && items.length === 0 && <div className="px-3 py-1.5 text-sm text-slate-500">Nič sa nenašlo</div>}
          {items.map((o, i) => (
            <button type="button" key={o.value}
              className={`block w-full px-3 py-1.5 text-left text-sm ${i === hi ? "bg-brand-50 dark:bg-slate-800" : ""} ${o.value === value ? "font-semibold" : ""}`}
              onMouseEnter={() => setHi(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(o);
              }}>
              {o.label}
              {o.overhead && <span className="ml-1 text-xs text-slate-500">(réžia)</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function MultiRefSelect({ entity, value, onChange, disabled }: {
  entity: string; value: number[]; onChange: (v: number[]) => void; disabled?: boolean;
}) {
  const labels = useLabels(entity, value);
  const map = useMemo(() => new Map((labels.data ?? []).map((o) => [o.value, o.label])), [labels.data]);
  return (
    <div className="space-y-1.5">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((v) => (
            <span key={v} className="chip">
              {map.get(v) ?? `#${v}`}
              {!disabled && (
                <button type="button" onClick={() => onChange(value.filter((x) => x !== v))} aria-label="Odobrať">
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {!disabled && (
        <RefSelect entity={entity} value={null} placeholder="Pridať…" label=""
          onChange={(v) => v && !value.includes(v) && onChange([...value, v])} />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------- generic field input by meta
export function FieldInput({ field, value, onChange, id, disabled, autoFocus }: {
  field: FieldMeta; value: unknown; onChange: (v: unknown) => void; id?: string; disabled?: boolean; autoFocus?: boolean;
}) {
  const dis = disabled || !field.editable;
  switch (field.type) {
    case "date":
      return <DateInput id={id} value={value as string} onChange={onChange} disabled={dis} autoFocus={autoFocus} />;
    case "time":
      return <TimeInput id={id} value={value as string} onChange={onChange} disabled={dis} />;
    case "number":
    case "hours":
      return <NumberInput id={id} value={value as number} onChange={onChange} disabled={dis} />;
    case "money":
      return <NumberInput id={id} value={value as number} onChange={onChange} disabled={dis} decimals={2} suffix="€" />;
    case "bool":
      return (
        <label className="inline-flex items-center gap-2 py-1.5 text-sm">
          <input id={id} type="checkbox" className="h-4 w-4 accent-brand-600" checked={Boolean(value)} disabled={dis}
            onChange={(e) => onChange(e.target.checked)} />
          {value ? "áno" : "nie"}
        </label>
      );
    case "select":
      return (
        <select id={id} className="input" value={(value as string) ?? ""} disabled={dis}
          onChange={(e) => onChange(e.target.value || null)}>
          {!field.required && <option value="">—</option>}
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      );
    case "ref":
      return <RefSelect id={id} entity={field.ref!} value={value as number} onChange={(v) => onChange(v)} disabled={dis}
        autoFocus={autoFocus} />;
    case "multiref":
      return <MultiRefSelect entity={field.ref!} value={(value as number[]) ?? []} onChange={onChange} disabled={dis} />;
    case "longtext":
      return <textarea id={id} className="input min-h-20" value={(value as string) ?? ""} disabled={dis}
        onChange={(e) => onChange(e.target.value)} />;
    default:
      return <input id={id} className="input" value={(value as string) ?? ""} disabled={dis} autoFocus={autoFocus}
        type={field.key === "password" ? "password" : "text"} autoComplete={field.key === "password" ? "new-password" : undefined}
        onChange={(e) => onChange(e.target.value)} />;
  }
}
