import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { EntityMeta, Row } from "@/lib/types";
import { cellText } from "./cells";
import { FieldInput } from "./inputs";
import { Drawer, Spinner, useToast } from "./ui";

interface Props {
  meta: EntityMeta;
  id: number | null; // null = new
  open: boolean;
  onClose: () => void;
  defaults?: Record<string, unknown>;
  onSaved?: (row: Row) => void;
}

export function EntityForm({ meta, values, setValues, onSubmit, autoFocusFirst }: {
  meta: EntityMeta; values: Record<string, unknown>; setValues: (f: (v: Record<string, unknown>) => Record<string, unknown>) => void;
  onSubmit?: () => void; autoFocusFirst?: boolean;
}) {
  const fields = meta.fields.filter((f) => f.in_form);
  const editable = fields.filter((f) => f.editable);
  const readonly = fields.filter((f) => !f.editable && values[f.key] !== undefined && values[f.key] !== null && values[f.key] !== "");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit?.();
      }}
      className="space-y-4"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {editable.map((f, i) => (
          <div key={f.key} className={f.type === "longtext" || f.type === "multiref" ? "sm:col-span-2" : ""}>
            <label className="label" htmlFor={`f-${f.key}`}>
              {f.label}
              {f.required && <span className="text-red-600"> *</span>}
            </label>
            <FieldInput field={f} id={`f-${f.key}`} value={values[f.key]} autoFocus={autoFocusFirst && i === 0}
              onChange={(v) => setValues((old) => ({ ...old, [f.key]: v }))} />
            {f.help && <p className="mt-0.5 text-xs text-slate-500">{f.help}</p>}
          </div>
        ))}
      </div>
      {readonly.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-800/50">
          {readonly.map((f) => (
            <div key={f.key} className="contents">
              <dt className="text-slate-500">{f.label}</dt>
              <dd className="text-right tabular-nums">{cellText(f, values as Row)}</dd>
            </div>
          ))}
        </dl>
      )}
      <button type="submit" className="hidden" />
    </form>
  );
}

export function EntityDrawer({ meta, id, open, onClose, defaults, onSaved }: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [orig, setOrig] = useState<Record<string, unknown>>({});
  const [tab, setTab] = useState<"form" | "history">("form");
  const [saving, setSaving] = useState(false);
  const row = useQuery({
    queryKey: ["row", meta.entity, id],
    queryFn: () => api.get<Row>(`/api/data/${meta.entity}/${id}`),
    enabled: open && id !== null,
  });
  const hist = useQuery({
    queryKey: ["history", meta.entity, id],
    queryFn: () => api.get<{ ts: string; user: string; action: string; changes: { field: string; old: unknown; new: unknown }[] }[]>(
      `/api/history/${meta.entity}/${id}`),
    enabled: open && id !== null && tab === "history",
  });

  useEffect(() => {
    if (!open) return;
    setTab("form");
    if (id === null) {
      const init: Record<string, unknown> = {};
      for (const f of meta.fields) {
        if (f.type === "bool" && f.key === "active") init[f.key] = true;
        if (f.type === "bool" && f.key === "billable") init[f.key] = true;
        if (f.type === "select" && f.required && f.options[0]) init[f.key] = f.options[0].value;
      }
      setValues({ ...init, ...(defaults || {}) });
      setOrig({});
    }
  }, [open, id, meta, defaults]);

  useEffect(() => {
    if (row.data) {
      setValues(row.data);
      setOrig(row.data);
    }
  }, [row.data]);

  const title = useMemo(() => {
    if (id === null) return `Nový záznam – ${meta.label}`;
    const t = values[meta.title_field];
    return `${meta.label}: ${t ?? `#${id}`}`;
  }, [id, meta, values]);

  const save = async () => {
    setSaving(true);
    try {
      const editable = meta.fields.filter((f) => f.editable);
      const payload: Record<string, unknown> = {};
      for (const f of editable) {
        const v = values[f.key];
        if (id === null ? v !== undefined : JSON.stringify(v ?? null) !== JSON.stringify(orig[f.key] ?? null)) payload[f.key] = v;
      }
      const res = id === null
        ? await api.post<Row>(`/api/data/${meta.entity}`, payload)
        : await api.patch<Row>(`/api/data/${meta.entity}/${id}`, payload);
      toast.ok("Uložené");
      await qc.invalidateQueries({ queryKey: ["data", meta.entity] });
      await qc.invalidateQueries({ queryKey: ["options"] });
      qc.removeQueries({ queryKey: ["row", meta.entity, id] });
      onSaved?.(res);
      onClose();
    } catch (e) {
      toast.error(e);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    const msg = meta.deletable ? "Naozaj vymazať tento záznam?" : "Deaktivovať záznam? (zostane v histórii, len sa skryje)";
    if (!confirm(msg)) return;
    try {
      await api.del(`/api/data/${meta.entity}/${id}`);
      toast.ok(meta.deletable ? "Vymazané" : "Deaktivované");
      await qc.invalidateQueries({ queryKey: ["data", meta.entity] });
      onClose();
    } catch (e) {
      toast.error(e);
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={title}
      actions={
        <>
          {id !== null && (meta.deletable || meta.has_active) && meta.can_write && (
            <button className="btn-ghost btn-sm text-red-600" onClick={remove} title={meta.deletable ? "Vymazať" : "Deaktivovať"}>
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          {meta.can_write && (
            <button className="btn-primary btn-sm" onClick={save} disabled={saving}>
              {saving ? <Spinner /> : <Save className="h-4 w-4" />} Uložiť
            </button>
          )}
        </>
      }
    >
      {id !== null && (
        <div className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
          <button className={`px-3 py-1.5 text-sm ${tab === "form" ? "border-b-2 border-brand-600 font-medium" : "text-slate-500"}`}
            onClick={() => setTab("form")}>Údaje</button>
          <button className={`flex items-center gap-1 px-3 py-1.5 text-sm ${tab === "history" ? "border-b-2 border-brand-600 font-medium" : "text-slate-500"}`}
            onClick={() => setTab("history")}><History className="h-3.5 w-3.5" /> História zmien</button>
        </div>
      )}
      {tab === "form" && (row.isLoading && id !== null ? <Spinner /> : (
        <EntityForm meta={meta} values={values} setValues={setValues} onSubmit={save} autoFocusFirst={id === null} />
      ))}
      {tab === "history" && (
        <div className="space-y-3">
          {hist.isLoading && <Spinner />}
          {hist.data?.length === 0 && <p className="text-sm text-slate-500">Bez záznamov.</p>}
          {hist.data?.map((h, i) => (
            <div key={i} className="rounded-md border border-slate-200 p-2 text-sm dark:border-slate-800">
              <div className="flex justify-between text-xs text-slate-500">
                <span>{fmtDateTime(h.ts)} · {h.user ?? "systém"}</span>
                <span>{ACTIONS[h.action] ?? h.action}</span>
              </div>
              {h.changes.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {h.changes.map((c, j) => (
                    <li key={j}>
                      <span className="font-medium">{c.field}:</span>{" "}
                      <span className="text-slate-500 line-through">{String(c.old ?? "–")}</span> → {String(c.new ?? "–")}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}

const ACTIONS: Record<string, string> = {
  create: "vytvorenie", update: "úprava", delete: "vymazanie", deactivate: "deaktivácia", recalculate: "prepočet sadzieb",
  confirm: "potvrdenie", unconfirm: "vrátenie na kontrolu", mark_physical: "fyzický originál", match: "spárovanie",
  unmatch: "zrušenie párovania", confirm_match: "potvrdenie párovania", no_document: "bez dokladu", close: "uzavretie",
  reopen: "otvorenie", link_invoice: "väzba na faktúru",
};
