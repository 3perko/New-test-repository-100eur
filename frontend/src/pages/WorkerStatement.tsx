import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import { api, linkUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtMoney, fmtNum, fmtTime, monthRange } from "@/lib/format";
import { PeriodPicker, type Period } from "@/components/PeriodPicker";
import { RefSelect } from "@/components/inputs";
import { Card, Empty, PageHeader, Spinner, Stat } from "@/components/ui";

interface WS {
  worker: { id: number; name: string; relation_type: string; ico: string | null };
  rows: { id: number; date: string; time_from: string | null; time_to: string | null; hours: number; project: string; company: string; description: string | null; cost_rate: number | null; amount: number }[];
  by_project: { project: string; hours: number; amount: number }[];
  total_hours: number; total_amount: number; company: string;
}

export default function WorkerStatement() {
  const { isAdmin, me } = useAuth();
  const [worker, setWorker] = useState<number | null>(isAdmin ? null : me?.worker_id ?? null);
  const [all, setAll] = useState(false);
  const [p, setP] = useState<Period>(() => {
    const [f, t] = monthRange(-1);
    return { from: f, to: t };
  });
  const params = { worker_id: worker, date_from: p.from, date_to: p.to, all_companies: all };
  const q = useQuery({
    queryKey: ["worker-statement", params],
    queryFn: () => api.get<WS>("/api/worker-statement", params),
    enabled: (!!worker || !isAdmin) && !!p.from && !!p.to,
  });
  const d = q.data;
  const label = d?.worker.relation_type === "contractor" ? "Suma na fakturáciu firme" : "Suma podľa nákladovej sadzby (podklad k mzde)";
  return (
    <div className="space-y-4">
      <PageHeader title="Podklad pre pracovníka" sub="Odpracované hodiny po dňoch a zákazkách a suma podľa nákladovej sadzby – koľko hodín a akú sumu pracovník fakturuje firme (živnostník) alebo podklad k mzde."
        actions={d && <>
          <a className="btn-secondary" href={linkUrl("/api/worker-statement/export", { ...params, format: "pdf" })} target="_blank" rel="noreferrer"><FileDown className="h-4 w-4" /> PDF</a>
          <a className="btn-secondary" href={linkUrl("/api/worker-statement/export", { ...params, format: "xlsx" })}><FileDown className="h-4 w-4" /> XLSX</a>
        </>} />
      <div className="flex flex-wrap items-end gap-4">
        {isAdmin && <div className="w-64"><label className="label">Pracovník</label><RefSelect entity="workers" value={worker} onChange={setWorker} /></div>}
        <PeriodPicker value={p} onChange={setP} allowAll={false} />
        {isAdmin && <label className="flex items-center gap-1.5 pb-1 text-sm"><input type="checkbox" className="accent-brand-600" checked={all} onChange={(e) => setAll(e.target.checked)} /> všetky firmy</label>}
      </div>
      {!worker && isAdmin ? <Empty>Vyberte pracovníka.</Empty> : q.isLoading ? <Spinner /> : d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Stat label="Odpracované hodiny" value={fmtNum(d.total_hours)} />
            <Stat label={label} value={fmtMoney(d.total_amount)} />
            <Stat label="Firma" value={<span className="text-base">{d.company}</span>} />
          </div>
          <Card title="Po zákazkách">
            <table className="w-full text-sm"><tbody>{d.by_project.map((b) => (
              <tr key={b.project}><td className="td">{b.project}</td><td className="td num">{fmtNum(b.hours)} h</td><td className="td num">{fmtMoney(b.amount)}</td></tr>))}</tbody></table>
          </Card>
          <Card title="Po dňoch">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr><th className="th">Dátum</th><th className="th">Od–do</th><th className="th text-right">Hodiny</th><th className="th">Zákazka</th><th className="th">Popis práce</th><th className="th text-right">Suma</th></tr></thead>
                <tbody>{d.rows.map((r) => (
                  <tr key={r.id}><td className="td">{fmtDate(r.date)}</td><td className="td">{fmtTime(r.time_from)}{r.time_to && `–${fmtTime(r.time_to)}`}</td>
                    <td className="td num">{fmtNum(r.hours)}</td><td className="td">{r.project}</td><td className="td">{r.description}</td><td className="td num">{fmtMoney(r.amount)}</td></tr>))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
