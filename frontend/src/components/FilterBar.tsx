import { useState } from "react";
import { Filter as FilterIcon, Plus, X } from "lucide-react";
import { fmtDate, fmtMoney, fmtNum, monthRange, yearRange } from "@/lib/format";
import type { FieldMeta, Filter } from "@/lib/types";
import { DateInput, MultiRefSelect, NumberInput } from "./inputs";
import { Modal } from "./ui";

export function describeFilter(f: Filter, field?: FieldMeta): string {
  if (!field) return f.field;
  const v = f.value;
  if (f.op === "isnull") return `${field.label}: prázdne`;
  if (f.op === "notnull") return `${field.label}: vyplnené`;
  if (f.op === "between" && Array.isArray(v)) {
    const fmt = (x: unknown) =>
      x == null ? "…" : field.type === "date" || field.type === "datetime" ? fmtDate(x) : field.type === "money" ? fmtMoney(x) : fmtNum(x);
    return `${field.label}: ${fmt(v[0])} – ${fmt(v[1])}`;
  }
  if (f.op === "in" && Array.isArray(v)) {
    if (field.type === "select") return `${field.label}: ${v.map((x) => field.options.find((o) => o.value === x)?.label ?? x).join(", ")}`;
    return `${field.label}: ${v.length} vybrané`;
  }
  if (field.type === "bool") return `${field.label}: ${v ? "áno" : "nie"}`;
  const ops: Record<string, string> = { contains: "obsahuje", eq: "=", neq: "≠", gte: "≥", lte: "≤", not_contains: "neobsahuje" };
  return `${field.label} ${ops[f.op] ?? f.op} „${String(v)}“`;
}

export function FilterBar({ fields, filters, onChange }: {
  fields: FieldMeta[]; filters: Filter[]; onChange: (f: Filter[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const fmap = new Map(fields.map((f) => [f.key, f]));
  return (
    <>
      <button className="btn-secondary btn-sm" onClick={() => setOpen(true)}>
        <FilterIcon className="h-3.5 w-3.5" /> Filter{filters.length > 0 && ` (${filters.length})`}
      </button>
      {filters.map((f, i) => (
        <span key={i} className="chip">
          {describeFilter(f, fmap.get(f.field))}
          <button onClick={() => onChange(filters.filter((_, j) => j !== i))} aria-label="Zrušiť filter"><X className="h-3 w-3" /></button>
        </span>
      ))}
      {filters.length > 1 && <button className="text-xs text-slate-500 hover:underline" onClick={() => onChange([])}>zrušiť všetky</button>}
      <AddFilterModal open={open} onClose={() => setOpen(false)} fields={fields.filter((f) => f.filterable)}
        onAdd={(f) => {
          onChange([...filters.filter((x) => x.field !== f.field), f]);
          setOpen(false);
        }} />
    </>
  );
}

function AddFilterModal({ open, onClose, fields, onAdd }: {
  open: boolean; onClose: () => void; fields: FieldMeta[]; onAdd: (f: Filter) => void;
}) {
  const [key, setKey] = useState("");
  const [op, setOp] = useState("contains");
  const [v1, setV1] = useState<unknown>(null);
  const [v2, setV2] = useState<unknown>(null);
  const [multi, setMulti] = useState<unknown[]>([]);
  const field = fields.find((f) => f.key === key);
  const reset = (k: string) => {
    setKey(k);
    setV1(null);
    setV2(null);
    setMulti([]);
    setOp(fields.find((f) => f.key === k)?.type === "ref" ? "in" : "contains");
  };
  const submit = () => {
    if (!field) return;
    if (op === "isnull" || op === "notnull") return onAdd({ field: key, op });
    switch (field.type) {
      case "number": case "money": case "hours": case "date": case "datetime":
        if (v1 == null && v2 == null) return;
        return onAdd({ field: key, op: "between", value: [v1, v2] });
      case "select":
        if (!multi.length) return;
        return onAdd({ field: key, op: "in", value: multi });
      case "ref":
        if (op === "contains") return v1 ? onAdd({ field: key, op: "contains", value: v1 }) : undefined;
        if (!multi.length) return;
        return onAdd({ field: key, op: "in", value: multi });
      case "bool":
        return onAdd({ field: key, op: "eq", value: v1 === true });
      default:
        if (!v1) return;
        return onAdd({ field: key, op, value: v1 });
    }
  };
  const quick = (r: [string, string]) => {
    setV1(r[0]);
    setV2(r[1]);
  };
  return (
    <Modal open={open} onClose={onClose} title="Pridať filter"
      footer={<><button className="btn-secondary" onClick={onClose}>Zrušiť</button>
        <button className="btn-primary" onClick={submit} disabled={!field}><Plus className="h-4 w-4" /> Pridať</button></>}>
      <div className="space-y-3">
        <div>
          <label className="label">Stĺpec</label>
          <select className="input" value={key} onChange={(e) => reset(e.target.value)} autoFocus>
            <option value="">— vyberte —</option>
            {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
          </select>
        </div>
        {field && (field.type === "text" || field.type === "longtext") && (
          <div className="grid grid-cols-3 gap-2">
            <select className="input" value={op} onChange={(e) => setOp(e.target.value)}>
              <option value="contains">obsahuje</option>
              <option value="eq">rovná sa</option>
              <option value="not_contains">neobsahuje</option>
              <option value="isnull">je prázdne</option>
              <option value="notnull">je vyplnené</option>
            </select>
            {op !== "isnull" && op !== "notnull" && (
              <input className="input col-span-2" value={(v1 as string) ?? ""} onChange={(e) => setV1(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()} />
            )}
          </div>
        )}
        {field && (field.type === "number" || field.type === "money" || field.type === "hours") && (
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label">od</label><NumberInput value={v1 as number} onChange={setV1} /></div>
            <div><label className="label">do</label><NumberInput value={v2 as number} onChange={setV2} /></div>
          </div>
        )}
        {field && (field.type === "date" || field.type === "datetime") && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="label">od</label><DateInput value={v1 as string} onChange={setV1} /></div>
              <div><label className="label">do</label><DateInput value={v2 as string} onChange={setV2} /></div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary btn-sm" onClick={() => quick(monthRange(0))}>tento mesiac</button>
              <button className="btn-secondary btn-sm" onClick={() => quick(monthRange(-1))}>minulý mesiac</button>
              <button className="btn-secondary btn-sm" onClick={() => quick(yearRange())}>tento rok</button>
            </div>
          </>
        )}
        {field && field.type === "select" && (
          <div className="grid grid-cols-2 gap-1">
            {field.options.map((o) => (
              <label key={o.value} className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="accent-brand-600" checked={multi.includes(o.value)}
                  onChange={(e) => setMulti(e.target.checked ? [...multi, o.value] : multi.filter((x) => x !== o.value))} />
                {o.label}
              </label>
            ))}
          </div>
        )}
        {field && field.type === "ref" && (
          <>
            <select className="input" value={op === "contains" ? "contains" : "in"} onChange={(e) => setOp(e.target.value)}>
              <option value="in">vybrané hodnoty</option>
              <option value="contains">názov obsahuje</option>
              <option value="isnull">je prázdne</option>
            </select>
            {op === "contains" ? (
              <input className="input" value={(v1 as string) ?? ""} onChange={(e) => setV1(e.target.value)} />
            ) : op !== "isnull" && (
              <MultiRefSelect entity={field.ref!} value={multi as number[]} onChange={(v) => setMulti(v)} />
            )}
          </>
        )}
        {field && field.type === "multiref" && (
          <input className="input" placeholder="obsahuje text" value={(v1 as string) ?? ""}
            onChange={(e) => { setOp("contains"); setV1(e.target.value); }} />
        )}
        {field && field.type === "bool" && (
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="radio" checked={v1 === true} onChange={() => setV1(true)} /> áno</label>
            <label className="flex items-center gap-2"><input type="radio" checked={v1 === false} onChange={() => setV1(false)} /> nie</label>
          </div>
        )}
      </div>
    </Modal>
  );
}
