import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct } from "@/lib/format";
import { Badge, Card, Empty, PageHeader, Spinner, Stat } from "@/components/ui";

interface Dash {
  counts: Record<string, number>;
  fleet_alerts: { vehicle: string; message: string; severity: string }[];
  missing_recurring: { message: string }[];
  material_without_document: { message: string }[];
  projects?: { project_id: number; project_name: string; total: number; budget: number | null; remaining: number | null;
    budget_used_pct: number | null; labor: number; material: number; transport: number; hours: number; month_total: number;
    unconfirmed: number }[];
  new_files?: number;
}

const CHECKS: { key: string; label: string; to: string }[] = [
  { key: "documents_in_review", label: "Doklady na kontrolu", to: "/doklady/na-kontrolu" },
  { key: "missing_recurring", label: "Chýbajúce povinné faktúry", to: "/financie/mesacna-kontrola" },
  { key: "receipts_without_original", label: "Bločky bez fyzického originálu", to: "/financie/mesacna-kontrola" },
  { key: "material_without_document", label: "Nákup materiálu bez dokladu", to: "/financie/mesacna-kontrola" },
  { key: "incomplete_timesheets", label: "Neúplné záznamy hodín", to: "/financie/mesacna-kontrola" },
  { key: "bank_without_document", label: "Bankové pohyby bez dokladu", to: "/financie/banka" },
  { key: "documents_without_payment", label: "Faktúry po splatnosti", to: "/financie/banka" },
  { key: "fleet_alerts", label: "Upozornenia vozového parku", to: "/vozovy-park/overenie" },
  { key: "file_errors", label: "Chyby spracovania súborov", to: "/doklady/inbox" },
];

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dash>("/api/dashboard") });
  if (q.isLoading) return <Spinner />;
  const d = q.data!;
  const projects = d.projects ?? [];
  const totalCost = projects.reduce((s, p) => s + p.total, 0);
  const monthCost = projects.reduce((s, p) => s + p.month_total, 0);
  return (
    <div className="space-y-5">
      <PageHeader title="Dashboard" sub="Upozornenia a rozpracované zákazky aktívnej firmy" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Rozpracované zákazky" value={projects.length} />
        <Stat label="Náklady rozpracovaných zákaziek" value={fmtMoney(totalCost)} />
        <Stat label="Náklady tento mesiac" value={fmtMoney(monthCost)} />
        <Stat label="Nové súbory v inboxe" value={d.new_files ?? 0} sub={<Link className="link" to="/doklady/inbox">spracovať</Link>} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Kontrola (aktuálny mesiac)" className="lg:col-span-1">
          <ul className="space-y-1.5 text-sm">
            {CHECKS.map((c) => {
              const n = d.counts[c.key] ?? 0;
              return (
                <li key={c.key}>
                  <Link to={c.to} className="flex items-center justify-between rounded px-1 py-0.5 hover:bg-slate-50 dark:hover:bg-slate-800">
                    <span className={n ? "" : "text-slate-500"}>{c.label}</span>
                    <Badge color={n ? "amber" : "green"}>{n}</Badge>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
        <Card title="Upozornenia" className="lg:col-span-2">
          {d.fleet_alerts.length + d.missing_recurring.length + d.material_without_document.length === 0 && <Empty>Všetko v poriadku.</Empty>}
          <ul className="space-y-1.5 text-sm">
            {d.missing_recurring.map((m, i) => (
              <li key={`r${i}`} className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{m.message}</li>
            ))}
            {d.fleet_alerts.map((a, i) => (
              <li key={`f${i}`} className="flex gap-2">
                <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${a.severity === "error" ? "text-red-600" : "text-amber-500"}`} />
                <span><b>{a.vehicle}</b>: {a.message}</span>
              </li>
            ))}
            {d.material_without_document.map((m, i) => (
              <li key={`m${i}`} className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{m.message}</li>
            ))}
          </ul>
        </Card>
      </div>
      <Card title="Rozpracované zákazky" actions={<Link className="link text-sm" to="/zakazky-naklady">Všetky zákazky <ArrowRight className="inline h-3 w-3" /></Link>}>
        {projects.length === 0 ? <Empty>Žiadne rozpracované zákazky.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr>
                <th className="th">Zákazka</th><th className="th text-right">Hodiny</th><th className="th text-right">Práca</th>
                <th className="th text-right">Materiál</th><th className="th text-right">Doprava</th><th className="th text-right">Spolu</th>
                <th className="th text-right">Rozpočet</th><th className="th text-right">Čerpanie</th><th className="th text-right">Tento mesiac</th>
              </tr></thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.project_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="td"><Link className="link" to={`/zakazky-naklady/${p.project_id}`}>{p.project_name}</Link>
                      {p.unconfirmed > 0 && <span className="ml-1 text-xs text-amber-600" title="Nepotvrdené doklady">+{fmtMoney(p.unconfirmed)} na kontrolu</span>}</td>
                    <td className="td num">{fmtNum(p.hours)}</td>
                    <td className="td num">{fmtMoney(p.labor)}</td>
                    <td className="td num">{fmtMoney(p.material)}</td>
                    <td className="td num">{fmtMoney(p.transport)}</td>
                    <td className="td num font-semibold">{fmtMoney(p.total)}</td>
                    <td className="td num">{fmtMoney(p.budget)}</td>
                    <td className={`td num ${p.budget_used_pct && p.budget_used_pct > 100 ? "text-red-600" : ""}`}>{p.budget ? fmtPct(p.budget_used_pct) : "–"}</td>
                    <td className="td num">{fmtMoney(p.month_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
