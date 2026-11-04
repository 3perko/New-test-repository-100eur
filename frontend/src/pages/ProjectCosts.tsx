import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, fmtPct, fmtTime } from "@/lib/format";
import { PeriodPicker, type Period } from "@/components/PeriodPicker";
import { Badge, Empty, PageHeader, Spinner, Stat } from "@/components/ui";

interface CostRow {
  project_id: number; project_name: string; status: string; is_overhead: boolean; active: boolean;
  material_receipts: number; material_invoices: number; material: number; labor: number; transport: number; total: number;
  hours: number; km: number; unconfirmed: number; budget: number | null; remaining: number | null; budget_used_pct: number | null;
}

export function ProjectCosts() {
  const [period, setPeriod] = useState<Period>({ from: null, to: null });
  const [unconf, setUnconf] = useState(false);
  const [inactive, setInactive] = useState(false);
  const nav = useNavigate();
  const q = useQuery({
    queryKey: ["project-costs", period, unconf, inactive],
    queryFn: () => api.get<{ rows: CostRow[]; totals: Record<string, number>; basis: string; unassigned: Record<string, number> }>(
      "/api/reports/project-costs", { date_from: period.from, date_to: period.to, include_unconfirmed: unconf, include_inactive: inactive }),
  });
  return (
    <div className="space-y-4">
      <PageHeader title="Zákazky – náklady" sub={q.data ? `Materiál ${q.data.basis}. Započítané sú len potvrdené doklady${unconf ? " + nepotvrdené" : ""}.` : ""} />
      <div className="flex flex-wrap items-end gap-4">
        <PeriodPicker value={period} onChange={setPeriod} />
        <label className="flex items-center gap-1.5 pb-1 text-sm"><input type="checkbox" className="accent-brand-600" checked={unconf} onChange={(e) => setUnconf(e.target.checked)} /> vrátane nepotvrdených dokladov</label>
        <label className="flex items-center gap-1.5 pb-1 text-sm"><input type="checkbox" className="accent-brand-600" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> aj neaktívne zákazky</label>
      </div>
      {q.isLoading ? <Spinner /> : q.data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Náklady spolu" value={fmtMoney(q.data.totals.total)} />
            <Stat label="Práca" value={fmtMoney(q.data.totals.labor)} sub={`${fmtNum(q.data.totals.hours)} h`} />
            <Stat label="Materiál – bločky" value={fmtMoney(q.data.totals.material_receipts)} />
            <Stat label="Materiál – faktúry" value={fmtMoney(q.data.totals.material_invoices)} />
            <Stat label="Doprava" value={fmtMoney(q.data.totals.transport)} sub={`${fmtNum(q.data.totals.km)} km`} />
          </div>
          {(q.data.unassigned.labor > 0 || q.data.unassigned.transport > 0) && (
            <p className="text-sm text-amber-700">Bez zákazky: práca {fmtMoney(q.data.unassigned.labor)}, doprava {fmtMoney(q.data.unassigned.transport)} – doplňte zákazku v hodinách/jazdách.</p>
          )}
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr>
                <th className="th">Zákazka</th><th className="th text-right">Hodiny</th><th className="th text-right">Práca</th>
                <th className="th text-right">Mat. bločky</th><th className="th text-right">Mat. faktúry</th><th className="th text-right">Doprava</th>
                <th className="th text-right">Spolu</th><th className="th text-right">Rozpočet</th><th className="th text-right">Zostatok</th>
                <th className="th text-right">Čerpanie</th>
              </tr></thead>
              <tbody>
                {q.data.rows.map((r) => (
                  <tr key={r.project_id} className={`cursor-pointer hover:bg-brand-50/60 dark:hover:bg-slate-800/60 ${r.active ? "" : "text-slate-400"}`}
                    onClick={() => nav(`/zakazky-naklady/${r.project_id}`)}>
                    <td className="td font-medium">{r.project_name} {r.is_overhead && <Badge>réžia</Badge>}
                      {r.unconfirmed > 0 && !unconf && <span className="ml-1 text-xs text-amber-600">+{fmtMoney(r.unconfirmed)} nepotvrdené</span>}</td>
                    <td className="td num">{fmtNum(r.hours)}</td>
                    <td className="td num">{fmtMoney(r.labor)}</td>
                    <td className="td num">{fmtMoney(r.material_receipts)}</td>
                    <td className="td num">{fmtMoney(r.material_invoices)}</td>
                    <td className="td num">{fmtMoney(r.transport)}</td>
                    <td className="td num font-semibold">{fmtMoney(r.total)}</td>
                    <td className="td num">{fmtMoney(r.budget)}</td>
                    <td className={`td num ${r.remaining !== null && r.remaining < 0 ? "text-red-600" : ""}`}>{fmtMoney(r.remaining)}</td>
                    <td className="td num">{r.budget ? fmtPct(r.budget_used_pct) : "–"}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr className="font-semibold">
                <td className="td">Spolu</td><td className="td num">{fmtNum(q.data.totals.hours)}</td>
                <td className="td num">{fmtMoney(q.data.totals.labor)}</td><td className="td num">{fmtMoney(q.data.totals.material_receipts)}</td>
                <td className="td num">{fmtMoney(q.data.totals.material_invoices)}</td><td className="td num">{fmtMoney(q.data.totals.transport)}</td>
                <td className="td num">{fmtMoney(q.data.totals.total)}</td><td className="td" colSpan={3} />
              </tr></tfoot>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

interface Detail {
  project: { id: number; name: string; budget: number | null; contract_price: number | null; billing_type: string; status: string; is_overhead: boolean };
  material: { allocation_id: number; document_id: number; doc_type: string; status: string; date: string; partner: string; number: string; line: string | null; amount: number; billed: boolean }[];
  revenue: { document_id: number; status: string; date: string; partner: string; number: string; amount: number }[];
  hours: { id: number; date: string; worker: string; time_from: string; time_to: string; hours: number; description: string; cost: number; billable: boolean; billable_amount: number; billed: boolean }[];
  trips: { id: number; date: string; vehicle: string; driver: string; km: number; km_computed: boolean; rate: number; cost: number; billed: boolean }[];
  summary: { material: number; labor: number; transport: number; hours: number; km: number; revenue: number };
  monthly: { month: string; revenue: number; material: number; labor: number; transport: number; cost: number; profit: number }[];
}

export function ProjectDetail() {
  const { id } = useParams();
  const [period, setPeriod] = useState<Period>({ from: null, to: null });
  const [tab, setTab] = useState<"material" | "hours" | "trips" | "revenue" | "monthly">("material");
  const q = useQuery({
    queryKey: ["project-detail", id, period],
    queryFn: () => api.get<Detail>(`/api/reports/project/${id}`, { date_from: period.from, date_to: period.to }),
  });
  if (q.isLoading) return <Spinner />;
  if (!q.data) return <Empty>Zákazka neexistuje.</Empty>;
  const d = q.data;
  const total = d.summary.material + d.summary.labor + d.summary.transport;
  const tabs = [
    ["material", `Materiál (${d.material.length})`], ["hours", `Hodiny (${d.hours.length})`], ["trips", `Jazdy (${d.trips.length})`],
    ["revenue", `Výnosy (${d.revenue.length})`], ["monthly", "Po mesiacoch"],
  ] as const;
  return (
    <div className="space-y-4">
      <Link to="/zakazky-naklady" className="link inline-flex items-center gap-1 text-sm"><ArrowLeft className="h-3 w-3" /> Späť na zákazky</Link>
      <PageHeader title={d.project.name} sub={d.project.budget ? `Rozpočet ${fmtMoney(d.project.budget)}` : undefined} />
      <PeriodPicker value={period} onChange={setPeriod} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Náklady spolu" value={fmtMoney(total)} />
        <Stat label="Práca" value={fmtMoney(d.summary.labor)} sub={`${fmtNum(d.summary.hours)} h`} />
        <Stat label="Materiál" value={fmtMoney(d.summary.material)} />
        <Stat label="Doprava" value={fmtMoney(d.summary.transport)} sub={`${fmtNum(d.summary.km)} km`} />
        <Stat label={d.project.budget ? "Zostatok rozpočtu" : "Výnosy"} value={fmtMoney(d.project.budget ? d.project.budget - total : d.summary.revenue)}
          tone={d.project.budget && d.project.budget - total < 0 ? "red" : undefined} />
      </div>
      <div className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
        {tabs.map(([k, l]) => (
          <button key={k} className={`px-3 py-1.5 text-sm ${tab === k ? "border-b-2 border-brand-600 font-medium" : "text-slate-500"}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <div className="card overflow-x-auto">
        {tab === "material" && (
          <table className="w-full text-sm">
            <thead><tr><th className="th">Dátum</th><th className="th">Doklad</th><th className="th">Dodávateľ</th><th className="th">Položka</th><th className="th">Stav</th><th className="th text-right">Suma</th></tr></thead>
            <tbody>{d.material.map((m) => (
              <tr key={m.allocation_id}>
                <td className="td">{fmtDate(m.date)}</td>
                <td className="td"><Link className="link" to={`/doklady/${m.document_id}`}>{m.doc_type === "receipt" ? "Bloček" : "Faktúra"} {m.number ?? `#${m.document_id}`}</Link></td>
                <td className="td">{m.partner}</td><td className="td">{m.line ?? "celý doklad"}</td>
                <td className="td"><Badge color={m.status === "confirmed" ? "green" : "amber"}>{m.status === "confirmed" ? "potvrdený" : "na kontrolu"}</Badge>{m.billed && <Badge color="blue">vyfakturované</Badge>}</td>
                <td className="td num">{fmtMoney(m.amount)}</td>
              </tr>))}
            </tbody>
          </table>
        )}
        {tab === "hours" && (
          <table className="w-full text-sm">
            <thead><tr><th className="th">Dátum</th><th className="th">Pracovník</th><th className="th">Od–do</th><th className="th text-right">Hodiny</th><th className="th">Popis</th><th className="th text-right">Náklad</th><th className="th text-right">Fakturovateľné</th></tr></thead>
            <tbody>{d.hours.map((h) => (
              <tr key={h.id}>
                <td className="td">{fmtDate(h.date)}</td><td className="td">{h.worker}</td>
                <td className="td">{fmtTime(h.time_from)}{h.time_to && `–${fmtTime(h.time_to)}`}</td>
                <td className="td num">{fmtNum(h.hours)}</td><td className="td">{h.description}</td>
                <td className="td num">{fmtMoney(h.cost)}</td>
                <td className="td num">{h.billable ? fmtMoney(h.billable_amount) : <span className="text-slate-400">nefakturuje sa</span>}{h.billed && " ✓"}</td>
              </tr>))}
            </tbody>
          </table>
        )}
        {tab === "trips" && (
          <table className="w-full text-sm">
            <thead><tr><th className="th">Dátum</th><th className="th">Vozidlo</th><th className="th">Vodič</th><th className="th text-right">Km</th><th className="th text-right">Sadzba</th><th className="th text-right">Náklad</th></tr></thead>
            <tbody>{d.trips.map((t) => (
              <tr key={t.id}>
                <td className="td">{fmtDate(t.date)}</td><td className="td">{t.vehicle}</td><td className="td">{t.driver}</td>
                <td className="td num">{fmtNum(t.km)}{t.km_computed && <span className="text-xs text-slate-400" title="dopočítané"> *</span>}</td>
                <td className="td num">{fmtMoney(t.rate)}</td><td className="td num">{fmtMoney(t.cost)}</td>
              </tr>))}
            </tbody>
          </table>
        )}
        {tab === "revenue" && (
          <table className="w-full text-sm">
            <thead><tr><th className="th">Dátum</th><th className="th">Faktúra</th><th className="th">Odberateľ</th><th className="th">Stav</th><th className="th text-right">Suma</th></tr></thead>
            <tbody>{d.revenue.map((r, i) => (
              <tr key={i}>
                <td className="td">{fmtDate(r.date)}</td><td className="td"><Link className="link" to={`/doklady/${r.document_id}`}>{r.number ?? `#${r.document_id}`}</Link></td>
                <td className="td">{r.partner}</td><td className="td">{r.status === "confirmed" ? "potvrdená" : "na kontrolu"}</td><td className="td num">{fmtMoney(r.amount)}</td>
              </tr>))}
            </tbody>
          </table>
        )}
        {tab === "monthly" && (
          <table className="w-full text-sm">
            <thead><tr><th className="th">Mesiac</th><th className="th text-right">Výnosy</th><th className="th text-right">Materiál</th><th className="th text-right">Práca</th><th className="th text-right">Doprava</th><th className="th text-right">Náklady</th><th className="th text-right">Zisk</th></tr></thead>
            <tbody>{d.monthly.map((m) => (
              <tr key={m.month}>
                <td className="td">{m.month.slice(5)}/{m.month.slice(0, 4)}</td><td className="td num">{fmtMoney(m.revenue)}</td>
                <td className="td num">{fmtMoney(m.material)}</td><td className="td num">{fmtMoney(m.labor)}</td><td className="td num">{fmtMoney(m.transport)}</td>
                <td className="td num">{fmtMoney(m.cost)}</td><td className={`td num ${m.profit < 0 ? "text-red-600" : ""}`}>{fmtMoney(m.profit)}</td>
              </tr>))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
