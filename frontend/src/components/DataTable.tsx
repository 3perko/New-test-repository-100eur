/**
 * Universal DataTable (master prompt 2.11): column chooser from all entity fields, drag & drop order, resizable
 * widths, multi-level sorting, typed filters, full-text search, saved views (per user, shareable), server-side
 * paging/sorting/filtering, totals of all filtered rows, grouping with group totals, active/inactive switch,
 * export of the current view, row detail, bulk actions and a card layout on mobile.
 */
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  flexRender, getCoreRowModel, useReactTable, type ColumnDef, type ColumnSizingState, type RowSelectionState,
} from "@tanstack/react-table";
import {
  ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Columns3, Download, GripVertical, Plus, RefreshCw, Search, Star,
} from "lucide-react";
import { api, linkUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EntityMeta, FieldMeta, Filter, ListResult, Row, SavedView, SortSpec, ViewConfig } from "@/lib/types";
import { Cell, cellText, defaultWidth, isNumeric } from "./cells";
import { EntityDrawer } from "./EntityDrawer";
import { FilterBar } from "./FilterBar";
import { RefSelect } from "./inputs";
import { Empty, Modal, Spinner, useToast } from "./ui";

export interface DataTableProps {
  entity: string;
  /** separates saved views / last state when the same entity is shown on several pages */
  viewKey?: string;
  /** always applied, not editable by user (e.g. doc_type = receipt) */
  fixedFilters?: Filter[];
  /** initial config when the user has no saved state */
  initial?: ViewConfig;
  toolbar?: ReactNode;
  onOpen?: (row: Row) => void;
  createDefaults?: Record<string, unknown>;
  hideCreate?: boolean;
  onCreate?: () => void;
  compact?: boolean;
}

function sortToParam(s: SortSpec[] | undefined) {
  return (s ?? []).map((x) => `${x.key}:${x.dir}`).join(",");
}

export function useEntityMeta(entity: string) {
  return useQuery({ queryKey: ["meta", entity], queryFn: () => api.get<EntityMeta>(`/api/meta/${entity}/fields`), staleTime: 300_000 });
}

export function DataTable(props: DataTableProps) {
  const { entity, fixedFilters = [], toolbar, initial } = props;
  const vk = props.viewKey ?? entity;
  const meta = useEntityMeta(entity);
  const views = useQuery({
    queryKey: ["views", vk],
    queryFn: () => api.get<{ views: SavedView[]; last: SavedView | null }>("/api/views", { entity: vk }),
    staleTime: 60_000,
  });
  const [cfg, setCfg] = useState<ViewConfig | null>(null);
  const [activeView, setActiveView] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [qInput, setQInput] = useState("");
  const [selection, setSelection] = useState<RowSelectionState>({});
  const [drawer, setDrawer] = useState<{ id: number | null } | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { isAdmin } = useAuth();

  const fields = meta.data?.fields ?? [];
  const fmap = useMemo(() => new Map(fields.map((f) => [f.key, f])), [fields]);

  // ---- initialise from default view / last state / initial / field defaults
  useEffect(() => {
    if (cfg || !meta.data || !views.data) return;
    const def = views.data.views.find((v) => v.is_default && v.own) ?? null;
    const base: ViewConfig = {
      columns: meta.data.fields.filter((f) => f.default_visible).map((f) => f.key),
      sort: meta.data.default_sort.split(",").filter(Boolean).map((s) => {
        const [key, dir] = s.split(":");
        return { key, dir: (dir as "asc" | "desc") || "asc" };
      }),
      filters: [], pageSize: 50, widths: {},
      ...initial,
    };
    const chosen = def?.config ?? views.data.last?.config ?? {};
    const merged = { ...base, ...chosen };
    merged.columns = (merged.columns ?? []).filter((c) => meta.data.fields.some((f) => f.key === c));
    if (!merged.columns.length) merged.columns = base.columns;
    setCfg(merged);
    setQInput(merged.q ?? "");
    if (def) setActiveView(def.id);
  }, [cfg, meta.data, views.data, initial]);

  // ---- remember last state on the server (debounced)
  const firstSave = useRef(true);
  useEffect(() => {
    if (!cfg) return;
    if (firstSave.current) {
      firstSave.current = false;
      return;
    }
    const t = setTimeout(() => {
      api.put(`/api/views/last/${encodeURIComponent(vk)}`, { config: cfg }).catch(() => undefined);
    }, 1000);
    return () => clearTimeout(t);
  }, [cfg, vk]);

  // ---- debounce fulltext
  useEffect(() => {
    if (!cfg) return;
    const t = setTimeout(() => {
      if ((cfg.q ?? "") !== qInput) {
        setCfg({ ...cfg, q: qInput });
        setPage(1);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [qInput, cfg]);

  const params = useMemo(() => {
    if (!cfg) return null;
    const cols = cfg.columns ?? [];
    return {
      columns: cols.join(","),
      sort: sortToParam(cfg.sort),
      filter: JSON.stringify([...fixedFilters, ...(cfg.filters ?? [])]),
      q: cfg.q || undefined,
      page,
      page_size: cfg.pageSize ?? 50,
      group_by: cfg.groupBy || undefined,
      include_inactive: cfg.includeInactive || undefined,
    };
  }, [cfg, page, fixedFilters]);

  const data = useQuery({
    queryKey: ["data", entity, params],
    queryFn: () => api.get<ListResult>(`/api/data/${entity}`, params!),
    enabled: !!params,
    placeholderData: (prev) => prev,
  });

  const update = (patch: Partial<ViewConfig>) => {
    setCfg((c) => ({ ...(c ?? {}), ...patch }));
    setPage(1);
    setActiveView(null);
  };

  // ---- columns for TanStack Table
  const visibleFields: FieldMeta[] = useMemo(
    () => (cfg?.columns ?? []).map((k) => fmap.get(k)).filter(Boolean) as FieldMeta[],
    [cfg?.columns, fmap],
  );
  const canSelect = (meta.data?.actions.length ?? 0) > 0;
  const columns = useMemo<ColumnDef<Row>[]>(() => {
    const cols: ColumnDef<Row>[] = visibleFields.map((f) => ({
      id: f.key,
      accessorFn: (r) => r[f.key],
      header: f.label,
      size: cfg?.widths?.[f.key] ?? defaultWidth(f),
      minSize: 50,
      cell: (c) => <Cell field={f} row={c.row.original} />,
    }));
    if (canSelect) {
      cols.unshift({
        id: "_sel", size: 34, enableResizing: false,
        header: ({ table }) => (
          <input type="checkbox" className="accent-brand-600" checked={table.getIsAllRowsSelected()}
            onChange={table.getToggleAllRowsSelectedHandler()} aria-label="Označiť všetko" />
        ),
        cell: ({ row }) => (
          <input type="checkbox" className="accent-brand-600" checked={row.getIsSelected()} onClick={(e) => e.stopPropagation()}
            onChange={row.getToggleSelectedHandler()} aria-label="Označiť riadok" />
        ),
      });
    }
    return cols;
  }, [visibleFields, cfg?.widths, canSelect]);

  const sizing: ColumnSizingState = cfg?.widths ?? {};
  const table = useReactTable({
    data: data.data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: "onChange",
    enableColumnResizing: true,
    getRowId: (r) => String(r.id),
    state: { columnSizing: sizing, rowSelection: selection },
    onRowSelectionChange: setSelection,
    onColumnSizingChange: (u) => {
      const next = typeof u === "function" ? u(sizing) : u;
      setCfg((c) => ({ ...(c ?? {}), widths: { ...(c?.widths ?? {}), ...next } }));
    },
  });

  const selectedIds = Object.keys(selection).filter((k) => selection[k]).map(Number);

  const toggleSort = (key: string, multi: boolean) => {
    const f = fmap.get(key);
    if (!f?.sortable) return;
    const cur = cfg?.sort ?? [];
    const ex = cur.find((s) => s.key === key);
    let next: SortSpec[];
    if (!ex) next = multi ? [...cur, { key, dir: "asc" }] : [{ key, dir: "asc" }];
    else if (ex.dir === "asc") next = cur.map((s) => (s.key === key ? { key, dir: "desc" } : s));
    else next = multi ? cur.filter((s) => s.key !== key) : [];
    if (!multi && ex) next = ex.dir === "asc" ? [{ key, dir: "desc" }] : [];
    update({ sort: next });
  };

  // drag & drop in header
  const dragCol = useRef<string | null>(null);
  const onDrop = (target: string) => {
    const src = dragCol.current;
    if (!src || src === target || !cfg?.columns) return;
    const cols = cfg.columns.filter((c) => c !== src);
    cols.splice(cols.indexOf(target), 0, src);
    update({ columns: cols });
  };

  const open = (row: Row) => {
    if (props.onOpen) return props.onOpen(row);
    if (meta.data?.detail_url) return navigate(meta.data.detail_url.replace("{id}", String(row.id)));
    setDrawer({ id: row.id });
  };

  const exportUrl = (format: string) =>
    linkUrl(`/api/data/${entity}/export`, { ...(params ?? {}), page: undefined, page_size: undefined, group_by: undefined, format });

  // ---- bulk actions
  const [payloadAction, setPayloadAction] = useState<string | null>(null);
  const [payloadProject, setPayloadProject] = useState<number | null>(null);
  const runAction = useMutation({
    mutationFn: ({ key, payload }: { key: string; payload?: Record<string, unknown> }) =>
      api.post<{ message: string }>(`/api/data/${entity}/actions/${key}`, { ids: selectedIds, payload }),
    onSuccess: (r) => {
      toast.ok(r.message ?? "Hotovo");
      setSelection({});
      void qc.invalidateQueries({ queryKey: ["data"] });
    },
    onError: (e) => toast.error(e),
  });
  const startAction = (a: EntityMeta["actions"][number]) => {
    if (a.payload === "project") {
      setPayloadAction(a.key);
      return;
    }
    if (a.confirm && !confirm(a.confirm)) return;
    runAction.mutate({ key: a.key });
  };

  if (meta.isError) return <Empty>{(meta.error as Error).message}</Empty>;
  if (!meta.data || !cfg) return <div className="p-6"><Spinner /></div>;

  const res = data.data;
  const totalPages = res ? Math.max(1, Math.ceil(res.total / (cfg.pageSize ?? 50))) : 1;
  const numericVisible = visibleFields.filter((f) => isNumeric(f) && f.aggregate);
  const groupField = cfg.groupBy ? fmap.get(cfg.groupBy) : undefined;
  const groupMap = new Map((res?.groups ?? []).map((g) => [JSON.stringify(g.value), g]));

  const rows = table.getRowModel().rows;

  return (
    <div className="space-y-2">
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <input className="input w-48 py-1 pl-7 text-sm" placeholder="Hľadať…" value={qInput} onChange={(e) => setQInput(e.target.value)} />
        </div>
        <FilterBar fields={fields} filters={cfg.filters ?? []} onChange={(f) => update({ filters: f })} />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {toolbar}
          {meta.data.has_active && (
            <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
              <input type="checkbox" className="accent-brand-600" checked={!!cfg.includeInactive}
                onChange={(e) => update({ includeInactive: e.target.checked })} />
              zobraziť aj neaktívne
            </label>
          )}
          <select className="input w-auto py-1 text-xs" value={cfg.groupBy ?? ""} onChange={(e) => update({ groupBy: e.target.value || null })}
            title="Zoskupiť podľa stĺpca">
            <option value="">Nezoskupovať</option>
            {fields.filter((f) => f.sortable && f.type !== "longtext" && f.type !== "multiref").map((f) => (
              <option key={f.key} value={f.key}>Zoskupiť: {f.label}</option>
            ))}
          </select>
          <ColumnChooser fields={fields} columns={cfg.columns ?? []} onChange={(c) => update({ columns: c })} />
          <ViewsMenu vk={vk} cfg={cfg} views={views.data?.views ?? []} active={activeView} isAdmin={isAdmin}
            onApply={(v) => {
              setCfg({ ...cfg, ...v.config });
              setQInput(v.config.q ?? "");
              setActiveView(v.id);
              setPage(1);
            }} />
          <div className="flex">
            <a className="btn-secondary btn-sm rounded-r-none" href={exportUrl("xlsx")} title="Export aktuálneho pohľadu do XLSX">
              <Download className="h-3.5 w-3.5" /> XLSX
            </a>
            <a className="btn-secondary btn-sm -ml-px rounded-l-none" href={exportUrl("csv")} title="Export do CSV">CSV</a>
          </div>
          <button className="btn-ghost btn-sm" onClick={() => data.refetch()} title="Obnoviť"><RefreshCw className={`h-3.5 w-3.5 ${data.isFetching ? "animate-spin" : ""}`} /></button>
          {meta.data.can_create && !props.hideCreate && (
            <button className="btn-primary btn-sm" onClick={() => (props.onCreate ? props.onCreate() : setDrawer({ id: null }))}>
              <Plus className="h-3.5 w-3.5" /> Nový
            </button>
          )}
        </div>
      </div>

      {selectedIds.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-brand-50 px-3 py-2 text-sm dark:bg-slate-800">
          <span className="font-medium">Označené: {selectedIds.length}</span>
          {meta.data.actions.map((a) => (
            <button key={a.key} className="btn-secondary btn-sm" disabled={runAction.isPending} onClick={() => startAction(a)}>{a.label}</button>
          ))}
          <button className="btn-ghost btn-sm" onClick={() => setSelection({})}>Zrušiť výber</button>
        </div>
      )}

      {/* desktop table */}
      <div className="card hidden overflow-x-auto md:block">
        <table className="w-full table-fixed border-collapse" style={{ minWidth: table.getTotalSize() }}>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const f = fmap.get(h.id);
                  const s = cfg.sort?.findIndex((x) => x.key === h.id) ?? -1;
                  const dir = s >= 0 ? cfg.sort![s].dir : null;
                  return (
                    <th key={h.id} className={`th relative ${f && isNumeric(f) ? "text-right" : ""}`} style={{ width: h.getSize() }}
                      draggable={!!f} onDragStart={() => (dragCol.current = h.id)} onDragOver={(e) => e.preventDefault()}
                      onDrop={() => onDrop(h.id)}>
                      <button className={`inline-flex max-w-full items-center gap-1 ${f?.sortable ? "cursor-pointer" : "cursor-default"}`}
                        onClick={(e) => f && toggleSort(h.id, e.shiftKey)} title={f?.sortable ? "Triediť (Shift = viacúrovňovo)" : undefined}>
                        <span className="truncate">{flexRender(h.column.columnDef.header, h.getContext())}</span>
                        {dir === "asc" && <ArrowUp className="h-3 w-3 shrink-0" />}
                        {dir === "desc" && <ArrowDown className="h-3 w-3 shrink-0" />}
                        {s >= 0 && (cfg.sort?.length ?? 0) > 1 && <sup className="text-[10px]">{s + 1}</sup>}
                      </button>
                      {h.column.getCanResize() && (
                        <div onMouseDown={h.getResizeHandler()} onTouchStart={h.getResizeHandler()}
                          className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-brand-500/40" />
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const gv = groupField ? r.original[groupField.key] : undefined;
              const prev = i > 0 ? rows[i - 1].original[groupField?.key ?? ""] : Symbol();
              const showGroup = groupField && (i === 0 || JSON.stringify(gv) !== JSON.stringify(prev));
              const g = showGroup ? groupMap.get(JSON.stringify(gv ?? null)) : undefined;
              return (
                <Fragment key={r.id}>
                  {showGroup && (
                    <tr className="bg-slate-100/70 dark:bg-slate-800/60">
                      {table.getVisibleLeafColumns().map((c, ci) => {
                        const f = fmap.get(c.id);
                        if (ci === (canSelect ? 1 : 0))
                          return <td key={c.id} className="td font-semibold">{cellText(groupField, r.original) || "—"} ({g?.count ?? ""})</td>;
                        if (f && isNumeric(f) && g && g.totals[f.key] != null)
                          return <td key={c.id} className="td num font-semibold">{cellText(f, { id: 0, [f.key]: g.totals[f.key] })}</td>;
                        return <td key={c.id} className="td" />;
                      })}
                    </tr>
                  )}
                  <tr className={`cursor-pointer hover:bg-brand-50/60 dark:hover:bg-slate-800/60 ${r.original.active === false ? "text-slate-400" : ""}`}
                    onClick={() => open(r.original)}>
                    {r.getVisibleCells().map((c) => (
                      <td key={c.id} className="td overflow-hidden" style={{ width: c.column.getSize() }}>
                        {flexRender(c.column.columnDef.cell, c.getContext())}
                      </td>
                    ))}
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
          {numericVisible.length > 0 && res && res.total > 0 && (
            <tfoot>
              <tr className="bg-slate-50 font-semibold dark:bg-slate-800/60">
                {table.getVisibleLeafColumns().map((c, ci) => {
                  const f = fmap.get(c.id);
                  if (ci === 0) return <td key={c.id} className="td text-xs text-slate-500">Spolu ({res.total})</td>;
                  return <td key={c.id} className="td num">
                    {f && res.totals[f.key] != null ? cellText(f, { id: 0, [f.key]: res.totals[f.key] }) : ""}
                  </td>;
                })}
              </tr>
            </tfoot>
          )}
        </table>
        {res && res.total === 0 && <Empty>Žiadne záznamy</Empty>}
      </div>

      {/* mobile cards */}
      <div className="space-y-2 md:hidden">
        {res?.rows.map((r) => {
          const main = visibleFields.slice(0, 4);
          return (
            <button key={r.id} className={`card block w-full p-3 text-left ${r.active === false ? "opacity-60" : ""}`} onClick={() => open(r)}>
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium">{main[0] ? cellText(main[0], r) || "—" : `#${r.id}`}</div>
                {canSelect && (
                  <input type="checkbox" className="mt-1 accent-brand-600" checked={!!selection[String(r.id)]}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setSelection((s) => ({ ...s, [String(r.id)]: e.target.checked }))} />
                )}
              </div>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 text-sm">
                {main.slice(1).map((f) => (
                  <div key={f.key} className="contents">
                    <dt className="text-slate-500">{f.label}</dt>
                    <dd className="text-right">{cellText(f, r)}</dd>
                  </div>
                ))}
              </dl>
            </button>
          );
        })}
        {res && numericVisible.length > 0 && res.total > 0 && (
          <div className="card p-3 text-sm">
            <div className="font-semibold">Spolu ({res.total})</div>
            {numericVisible.map((f) => (
              <div key={f.key} className="flex justify-between"><span className="text-slate-500">{f.label}</span>
                <span className="tabular-nums">{cellText(f, { id: 0, [f.key]: res.totals[f.key] })}</span></div>
            ))}
          </div>
        )}
        {res && res.total === 0 && <Empty>Žiadne záznamy</Empty>}
      </div>

      {/* pagination */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="text-slate-500">{res ? `${res.total} záznamov` : ""}{data.isFetching && <Spinner className="ml-2 inline" />}</span>
        <div className="flex items-center gap-2">
          <select className="input w-auto py-1 text-xs" value={cfg.pageSize ?? 50} onChange={(e) => update({ pageSize: Number(e.target.value) })}>
            {[25, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n} / strana</option>)}
          </select>
          <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Predchádzajúca"><ChevronLeft className="h-4 w-4" /></button>
          <span className="tabular-nums">{page} / {totalPages}</span>
          <button className="btn-secondary btn-sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)} aria-label="Ďalšia"><ChevronRight className="h-4 w-4" /></button>
        </div>
      </div>

      {drawer && (
        <EntityDrawer meta={meta.data} id={drawer.id} open={!!drawer} onClose={() => setDrawer(null)} defaults={props.createDefaults} />
      )}
      <Modal open={!!payloadAction} onClose={() => setPayloadAction(null)} title="Priradiť zákazku"
        footer={<>
          <button className="btn-secondary" onClick={() => setPayloadAction(null)}>Zrušiť</button>
          <button className="btn-primary" disabled={!payloadProject} onClick={() => {
            runAction.mutate({ key: payloadAction!, payload: { project_id: payloadProject } });
            setPayloadAction(null);
          }}>Priradiť</button>
        </>}>
        <label className="label">Zákazka</label>
        <RefSelect entity="projects" value={payloadProject} onChange={(v) => setPayloadProject(v)} />
        <p className="mt-2 text-xs text-slate-500">Celý doklad sa priradí na vybranú zákazku (existujúce rozdelenie sa nahradí).</p>
      </Modal>
    </div>
  );
}

// ----------------------------------------------------------------------------- column chooser
function ColumnChooser({ fields, columns, onChange }: { fields: FieldMeta[]; columns: string[]; onChange: (c: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [order, setOrder] = useState<string[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const drag = useRef<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const rest = fields.map((f) => f.key).filter((k) => !columns.includes(k));
    setOrder([...columns, ...rest]);
    setChecked(new Set(columns));
  }, [open, fields, columns]);
  const fmap = new Map(fields.map((f) => [f.key, f]));
  const move = (k: string, dir: -1 | 1) => {
    const i = order.indexOf(k);
    const j = i + dir;
    if (j < 0 || j >= order.length) return;
    const o = [...order];
    [o[i], o[j]] = [o[j], o[i]];
    setOrder(o);
  };
  return (
    <>
      <button className="btn-secondary btn-sm" onClick={() => setOpen(true)}><Columns3 className="h-3.5 w-3.5" /> Stĺpce</button>
      <Modal open={open} onClose={() => setOpen(false)} title="Výber a poradie stĺpcov"
        footer={<>
          <button className="btn-secondary" onClick={() => setChecked(new Set(fields.filter((f) => f.default_visible).map((f) => f.key)))}>Predvolené</button>
          <button className="btn-primary" onClick={() => {
            onChange(order.filter((k) => checked.has(k)));
            setOpen(false);
          }}>Použiť</button>
        </>}>
        <p className="mb-2 text-xs text-slate-500">Zaškrtnite stĺpce, poradie meňte potiahnutím alebo šípkami.</p>
        <ul className="space-y-0.5">
          {order.map((k) => {
            const f = fmap.get(k)!;
            return (
              <li key={k} draggable onDragStart={() => (drag.current = k)} onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  const src = drag.current;
                  if (!src || src === k) return;
                  const o = order.filter((x) => x !== src);
                  o.splice(o.indexOf(k), 0, src);
                  setOrder(o);
                }}
                className="flex items-center gap-2 rounded px-1 py-1 hover:bg-slate-50 dark:hover:bg-slate-800">
                <GripVertical className="h-4 w-4 cursor-grab text-slate-400" />
                <label className="flex flex-1 items-center gap-2 text-sm">
                  <input type="checkbox" className="accent-brand-600" checked={checked.has(k)}
                    onChange={(e) => {
                      const s = new Set(checked);
                      if (e.target.checked) s.add(k); else s.delete(k);
                      setChecked(s);
                    }} />
                  {f.label}
                  {f.computed && <span className="text-xs text-slate-400">(vypočítané)</span>}
                </label>
                <button className="btn-ghost btn-sm px-1" onClick={() => move(k, -1)} aria-label="Vyššie"><ArrowUp className="h-3 w-3" /></button>
                <button className="btn-ghost btn-sm px-1" onClick={() => move(k, 1)} aria-label="Nižšie"><ArrowDown className="h-3 w-3" /></button>
              </li>
            );
          })}
        </ul>
      </Modal>
    </>
  );
}

// ----------------------------------------------------------------------------- saved views
function ViewsMenu({ vk, cfg, views, active, isAdmin, onApply }: {
  vk: string; cfg: ViewConfig; views: SavedView[]; active: number | null; isAdmin: boolean; onApply: (v: SavedView) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [asDefault, setAsDefault] = useState(false);
  const [shared, setShared] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const refresh = () => qc.invalidateQueries({ queryKey: ["views", vk] });
  const save = async () => {
    try {
      await api.post("/api/views", { entity: vk, name, config: cfg, is_default: asDefault, shared });
      toast.ok("Pohľad uložený");
      setName("");
      await refresh();
    } catch (e) {
      toast.error(e);
    }
  };
  const current = views.find((v) => v.id === active);
  return (
    <>
      <button className="btn-secondary btn-sm" onClick={() => setOpen(true)}>
        <Star className={`h-3.5 w-3.5 ${current ? "fill-amber-400 text-amber-500" : ""}`} /> {current ? current.name : "Pohľady"}
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title="Uložené pohľady">
        <div className="space-y-4">
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {views.length === 0 && <li className="py-2 text-sm text-slate-500">Zatiaľ žiadne uložené pohľady.</li>}
            {views.map((v) => (
              <li key={v.id} className="flex items-center gap-2 py-1.5 text-sm">
                <button className="flex-1 text-left hover:underline" onClick={() => {
                  onApply(v);
                  setOpen(false);
                }}>
                  {v.name}
                  {v.is_default && <span className="ml-1 text-xs text-amber-600">(predvolený)</span>}
                  {v.shared && <span className="ml-1 text-xs text-brand-600">(zdieľaný)</span>}
                </button>
                {v.own && (
                  <>
                    <button className="btn-ghost btn-sm" title="Prepísať aktuálnym nastavením" onClick={async () => {
                      await api.patch(`/api/views/${v.id}`, { config: cfg });
                      toast.ok("Pohľad aktualizovaný");
                      await refresh();
                    }}>Prepísať</button>
                    <button className="btn-ghost btn-sm" onClick={async () => {
                      await api.patch(`/api/views/${v.id}`, { is_default: !v.is_default });
                      await refresh();
                    }}>{v.is_default ? "Zrušiť predvolený" : "Predvolený"}</button>
                    <button className="btn-ghost btn-sm text-red-600" onClick={async () => {
                      if (!confirm(`Vymazať pohľad „${v.name}“?`)) return;
                      await api.del(`/api/views/${v.id}`);
                      await refresh();
                    }}>Vymazať</button>
                  </>
                )}
              </li>
            ))}
          </ul>
          <div className="space-y-2 rounded-md bg-slate-50 p-3 dark:bg-slate-800/50">
            <label className="label">Uložiť aktuálne nastavenie (stĺpce, triedenie, filtre, zoskupenie) ako</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="napr. Sikorky – materiál tento mesiac" />
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-brand-600" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} /> predvolený</label>
              {isAdmin && <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-brand-600" checked={shared} onChange={(e) => setShared(e.target.checked)} /> zdieľať všetkým</label>}
            </div>
            <button className="btn-primary btn-sm" disabled={!name.trim()} onClick={save}>Uložiť pohľad</button>
          </div>
        </div>
      </Modal>
    </>
  );
}
