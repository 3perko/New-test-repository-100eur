import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileDown, Lock, Trash2, Unlock } from "lucide-react";
import { api, linkUrl } from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, monthRange } from "@/lib/format";
import { DataTable } from "@/components/DataTable";
import { PeriodPicker, type Period } from "@/components/PeriodPicker";
import { RefSelect } from "@/components/inputs";
import { Badge, Card, Empty, PageHeader, Spinner, Stat, useToast } from "@/components/ui";

interface BLine { id?: number; line_type: string; date: string; description: string | null; worker_name?: string | null;
  quantity: number; unit: string; rate: number | null; markup_pct: number | null; amount: number }
interface Preview { project_name: string; billing_type: string; vat_rate: number; vat_payer: boolean; total_net: number; total_vat: number; total_gross: number; lines: BLine[] }
interface Statement extends Preview {
  id: number; project_id: number; status: string; period_from: string; period_to: string; group_by: string; note: string | null;
  invoice_document_id: number | null; invoice: { id: number; number: string | null; total_gross: number } | null;
  customer: { name: string } | null; closed_at: string | null;
}
const TYPE: Record<string, string> = { hours: "Práca", material: "Materiál", transport: "Doprava", other: "Iné" };

export function BillingList() {
  const [project, setProject] = useState<number | null>(null);
  const [period, setPeriod] = useState<Period>(() => {
    const [f, t] = monthRange(0);
    return { from: f, to: t };
  });
  const [groupBy, setGroupBy] = useState("worker");
  const nav = useNavigate();
  const toast = useToast();
  const prev = useQuery({
    queryKey: ["billing-preview", project, period],
    queryFn: () => api.post<Preview>("/api/billing/preview", { project_id: project, date_from: period.from, date_to: period.to }),
    enabled: !!project && !!period.from && !!period.to,
  });
  const create = async () => {
    try {
      const st = await api.post<Statement>("/api/billing", { project_id: project, date_from: period.from, date_to: period.to, group_by: groupBy });
      nav(`/vystupy/fakturacia/${st.id}`);
    } catch (e) {
      toast.error(e);
    }
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Podklad k fakturácii" sub="Nevyfakturované fakturovateľné hodiny, materiál (s prirážkou) a doprava zákazky za obdobie. Uzavretím sa položky označia ako vyfakturované." />
      <Card title="Nový podklad">
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-64"><label className="label">Zákazka</label><RefSelect entity="projects" value={project} onChange={setProject} /></div>
          <PeriodPicker value={period} onChange={setPeriod} allowAll={false} />
          <div><label className="label">Hodiny v PDF</label>
            <select className="input w-auto" value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
              <option value="worker">po pracovníkoch</option><option value="day">po dňoch</option>
            </select></div>
        </div>
        {prev.isFetching && <Spinner className="mt-3" />}
        {prev.data && (
          <div className="mt-4 space-y-3">
            {prev.data.lines.length === 0 ? <Empty>Za obdobie nie sú žiadne nevyfakturované položky.</Empty> : (
              <>
                <LinesTable lines={prev.data.lines} fixed={prev.data.billing_type === "fixed"} />
                <div className="flex flex-wrap items-center justify-end gap-4 text-sm">
                  <span>Bez DPH <b>{fmtMoney(prev.data.total_net)}</b></span>
                  {prev.data.vat_payer && <span>DPH {fmtNum(prev.data.vat_rate, 0)} % <b>{fmtMoney(prev.data.total_vat)}</b></span>}
                  <span>Spolu <b>{fmtMoney(prev.data.total_gross)}</b></span>
                  <button className="btn-primary" onClick={create}>Vytvoriť podklad</button>
                </div>
              </>
            )}
          </div>
        )}
      </Card>
      <Card title="Vytvorené podklady"><DataTable entity="billing_statements" hideCreate /></Card>
    </div>
  );
}

function LinesTable({ lines, fixed, onRemove }: { lines: BLine[]; fixed: boolean; onRemove?: (id: number) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr><th className="th">Typ</th><th className="th">Dátum</th><th className="th">Popis</th><th className="th text-right">Množstvo</th>
          <th className="th text-right">Sadzba / cena</th><th className="th text-right">Prirážka</th><th className="th text-right">Suma</th>{onRemove && <th className="th" />}</tr></thead>
        <tbody>{lines.map((l, i) => (
          <tr key={l.id ?? i}>
            <td className="td">{TYPE[l.line_type]}</td><td className="td">{fmtDate(l.date)}</td>
            <td className="td">{l.worker_name && <b>{l.worker_name}: </b>}{l.description}</td>
            <td className="td num">{fmtNum(l.quantity)} {l.unit}</td>
            <td className="td num">{fixed ? "–" : fmtMoney(l.rate)}</td>
            <td className="td num">{l.markup_pct ? `${fmtNum(l.markup_pct)} %` : ""}</td>
            <td className="td num">{fixed ? "–" : fmtMoney(l.amount)}</td>
            {onRemove && <td className="td"><button className="text-slate-400 hover:text-red-600" onClick={() => onRemove(l.id!)} aria-label="Odobrať"><Trash2 className="h-4 w-4" /></button></td>}
          </tr>))}
        </tbody>
      </table>
    </div>
  );
}

export function BillingDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["billing", id], queryFn: () => api.get<Statement>(`/api/billing/${id}`) });
  const [inv, setInv] = useState<number | null>(null);
  const act = async (fn: () => Promise<Statement>, msg: string) => {
    try {
      const r = await fn();
      qc.setQueryData(["billing", id], r);
      void qc.invalidateQueries({ queryKey: ["data"] });
      toast.ok(msg);
    } catch (e) {
      toast.error(e);
    }
  };
  if (q.isLoading) return <Spinner />;
  const s = q.data!;
  const draft = s.status === "draft";
  return (
    <div className="space-y-4">
      <Link to="/vystupy/fakturacia" className="link inline-flex items-center gap-1 text-sm"><ArrowLeft className="h-3 w-3" /> Späť</Link>
      <PageHeader title={<span className="flex items-center gap-2">Podklad č. {s.id} – {s.project_name} <Badge color={draft ? "amber" : "green"}>{draft ? "návrh" : "uzavretý"}</Badge></span>}
        sub={`Obdobie ${fmtDate(s.period_from)} – ${fmtDate(s.period_to)}${s.customer ? ` · odberateľ ${s.customer.name}` : ""}`}
        actions={<>
          <a className="btn-secondary" href={linkUrl(`/api/billing/${s.id}/export`, { format: "pdf" })} target="_blank" rel="noreferrer"><FileDown className="h-4 w-4" /> PDF</a>
          <a className="btn-secondary" href={linkUrl(`/api/billing/${s.id}/export`, { format: "xlsx" })}><FileDown className="h-4 w-4" /> XLSX</a>
          <a className="btn-secondary" href={linkUrl(`/api/billing/${s.id}/export`, { format: "csv" })}>CSV</a>
          {draft ? <>
            <button className="btn-ghost text-red-600" onClick={async () => {
              if (!confirm("Vymazať návrh podkladu?")) return;
              try { await api.del(`/api/data/billing_statements/${s.id}`); nav("/vystupy/fakturacia"); } catch (e) { toast.error(e); }
            }}><Trash2 className="h-4 w-4" /></button>
            <button className="btn-primary" onClick={() => act(() => api.post(`/api/billing/${s.id}/close`), "Podklad uzavretý – položky sú označené ako vyfakturované")}><Lock className="h-4 w-4" /> Uzavrieť</button>
          </> : <button className="btn-secondary" onClick={() => act(() => api.post(`/api/billing/${s.id}/reopen`), "Podklad otvorený")}><Unlock className="h-4 w-4" /> Otvoriť</button>}
        </>} />
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Bez DPH" value={fmtMoney(s.total_net)} />
        <Stat label={`DPH ${fmtNum(s.vat_rate, 0)} %`} value={fmtMoney(s.total_vat)} />
        <Stat label="S DPH" value={fmtMoney(s.total_gross)} />
      </div>
      <Card title="Položky">
        <LinesTable lines={s.lines} fixed={s.billing_type === "fixed"}
          onRemove={draft ? (lid) => act(() => api.patch(`/api/billing/${s.id}`, { remove_line_ids: [lid] }), "Položka odobratá") : undefined} />
      </Card>
      <Card title="Väzba na vystavenú faktúru">
        {s.invoice ? (
          <p className="text-sm">Faktúra <Link className="link" to={`/doklady/${s.invoice.id}`}>{s.invoice.number ?? `#${s.invoice.id}`}</Link> ({fmtMoney(s.invoice.total_gross)}){" "}
            <button className="link ml-2 text-xs" onClick={() => act(() => api.post(`/api/billing/${s.id}/invoice`, { document_id: null }), "Väzba zrušená")}>zrušiť väzbu</button></p>
        ) : (
          <div className="flex items-end gap-2">
            <div className="w-72"><label className="label">Vystavená faktúra</label><RefSelect entity="documents" value={inv} onChange={setInv} placeholder="číslo faktúry" /></div>
            <button className="btn-secondary" disabled={!inv} onClick={() => act(() => api.post(`/api/billing/${s.id}/invoice`, { document_id: inv }), "Faktúra naviazaná")}>Naviazať</button>
          </div>
        )}
      </Card>
    </div>
  );
}
