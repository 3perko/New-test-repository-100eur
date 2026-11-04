import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct } from "@/lib/format";
import { PeriodPicker, type Period } from "@/components/PeriodPicker";
import { PageHeader, Spinner, Stat } from "@/components/ui";

interface PRow {
  project_id: number; project_name: string; status: string; billing_type: string; revenue: number; material: number;
  labor: number; transport: number; cost: number; profit: number; margin_pct: number | null; wip: number; hours: number;
  expected_profit: number; contract_price?: number; estimated_profit?: number; estimated_margin_pct?: number | null;
  overhead_share?: number; profit_after_overhead?: number;
}
interface Prof {
  rows: PRow[]; overhead_cost: number; basis: string;
  totals: { revenue: number; cost: number; project_profit: number; overhead: number; company_profit: number; margin_pct: number | null;
    wip: number; expected_profit: number; hours: number };
  monthly: { month: string; revenue: number; cost: number; profit: number; material: number; labor: number; transport: number }[];
}

export default function Profitability() {
  const [period, setPeriod] = useState<Period>({ from: null, to: null });
  const [split, setSplit] = useState("");
  const q = useQuery({
    queryKey: ["profitability", period, split],
    queryFn: () => api.get<Prof>("/api/reports/profitability", { date_from: period.from, date_to: period.to, overhead_split: split || undefined }),
  });
  const d = q.data;
  return (
    <div className="space-y-4">
      <PageHeader title="Ziskovosť" sub={d ? `Výnosy = vystavené faktúry priradené k zákazke (${d.basis}). Rozpracovanosť = vykonaná, ešte nevyfakturovaná práca, materiál a doprava.` : ""} />
      <div className="flex flex-wrap items-end gap-4">
        <PeriodPicker value={period} onChange={setPeriod} />
        <div>
          <label className="label">Réžia</label>
          <select className="input w-auto" value={split} onChange={(e) => setSplit(e.target.value)}>
            <option value="">nerozpočítavať</option>
            <option value="hours">rozpočítať podľa hodín</option>
            <option value="cost">rozpočítať podľa nákladov</option>
          </select>
        </div>
      </div>
      {q.isLoading || !d ? <Spinner /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Výnosy" value={fmtMoney(d.totals.revenue)} />
            <Stat label="Náklady zákaziek" value={fmtMoney(d.totals.cost)} />
            <Stat label="Zisk zákaziek" value={fmtMoney(d.totals.project_profit)} tone={d.totals.project_profit < 0 ? "red" : "green"} />
            <Stat label="Réžia" value={fmtMoney(d.totals.overhead)} />
            <Stat label="Zisk firmy" value={fmtMoney(d.totals.company_profit)} sub={`marža ${fmtPct(d.totals.margin_pct)}`}
              tone={d.totals.company_profit < 0 ? "red" : "green"} />
            <Stat label="Rozpracovanosť" value={fmtMoney(d.totals.wip)} sub={`očakávaný zisk ${fmtMoney(d.totals.expected_profit)}`} />
          </div>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr>
                <th className="th">Zákazka</th><th className="th text-right">Výnosy</th><th className="th text-right">Materiál</th>
                <th className="th text-right">Práca</th><th className="th text-right">Doprava</th><th className="th text-right">Náklady</th>
                <th className="th text-right">Hrubý zisk</th><th className="th text-right">Marža</th><th className="th text-right">Rozpracovanosť</th>
                <th className="th text-right">Očakávaný zisk</th><th className="th text-right">Pevná cena / odhad</th>
                {split && <><th className="th text-right">Podiel réžie</th><th className="th text-right">Zisk po réžii</th></>}
              </tr></thead>
              <tbody>
                {d.rows.map((r) => (
                  <tr key={r.project_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="td"><Link className="link" to={`/zakazky-naklady/${r.project_id}`}>{r.project_name}</Link></td>
                    <td className="td num">{fmtMoney(r.revenue)}</td><td className="td num">{fmtMoney(r.material)}</td>
                    <td className="td num">{fmtMoney(r.labor)}</td><td className="td num">{fmtMoney(r.transport)}</td>
                    <td className="td num">{fmtMoney(r.cost)}</td>
                    <td className={`td num font-semibold ${r.profit < 0 ? "text-red-600" : ""}`}>{fmtMoney(r.profit)}</td>
                    <td className="td num">{fmtPct(r.margin_pct)}</td>
                    <td className="td num">{fmtMoney(r.wip)}</td>
                    <td className={`td num ${r.expected_profit < 0 ? "text-red-600" : ""}`}>{fmtMoney(r.expected_profit)}</td>
                    <td className="td num">{r.contract_price != null ? <>{fmtMoney(r.contract_price)}<div className="text-xs text-slate-500">odhad {fmtMoney(r.estimated_profit)} ({fmtPct(r.estimated_margin_pct)})</div></> : "–"}</td>
                    {split && <><td className="td num">{fmtMoney(r.overhead_share)}</td><td className="td num">{fmtMoney(r.profit_after_overhead)}</td></>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card overflow-x-auto">
            <div className="border-b border-slate-200 px-4 py-2 text-sm font-semibold dark:border-slate-800">Po mesiacoch (celá firma vrátane réžie)</div>
            <table className="w-full text-sm">
              <thead><tr><th className="th">Mesiac</th><th className="th text-right">Výnosy</th><th className="th text-right">Materiál</th><th className="th text-right">Práca</th><th className="th text-right">Doprava</th><th className="th text-right">Náklady</th><th className="th text-right">Zisk</th></tr></thead>
              <tbody>{d.monthly.map((m) => (
                <tr key={m.month}><td className="td">{m.month.slice(5)}/{m.month.slice(0, 4)}</td>
                  <td className="td num">{fmtMoney(m.revenue)}</td><td className="td num">{fmtMoney(m.material)}</td><td className="td num">{fmtMoney(m.labor)}</td>
                  <td className="td num">{fmtMoney(m.transport)}</td><td className="td num">{fmtMoney(m.cost)}</td>
                  <td className={`td num font-semibold ${m.profit < 0 ? "text-red-600" : ""}`}>{fmtMoney(m.profit)}</td></tr>))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-500">Hodiny spolu: {fmtNum(d.totals.hours)} h. Rozpočítanie réžie je len zobrazenie, nič sa nezapisuje.</p>
        </>
      )}
    </div>
  );
}
