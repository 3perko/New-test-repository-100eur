import { useState } from "react";
import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { linkUrl } from "@/lib/api";
import { monthRange } from "@/lib/format";
import { PeriodPicker, type Period } from "@/components/PeriodPicker";
import { Card, PageHeader } from "@/components/ui";

const ENTITIES: [string, string, string][] = [
  ["timesheets", "Hodiny", "date"], ["trips", "Jazdy", "date"], ["documents", "Doklady", "issue_date"],
  ["allocations", "Priradenia nákladov a výnosov", "doc_date"], ["document_lines", "Položky dokladov", "doc_date"],
  ["bank_transactions", "Bankové pohyby", "booking_date"], ["projects", "Zákazky", ""], ["workers", "Pracovníci", ""],
  ["vehicles", "Vozidlá", ""], ["vehicle_services", "Servis vozidiel", "date"], ["audit_log", "Audit log", "ts"],
];

export default function Exports() {
  const [p, setP] = useState<Period>(() => {
    const [f, t] = monthRange(-1);
    return { from: f, to: t };
  });
  const url = (entity: string, dateField: string, format: string) => {
    const filter = dateField && (p.from || p.to) ? JSON.stringify([{ field: dateField, op: "between", value: [p.from, p.to] }]) : undefined;
    return linkUrl(`/api/data/${entity}/export`, { format, filter });
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Exporty" sub="Každá tabuľka v aplikácii sa dá exportovať tlačidlom XLSX/CSV podľa aktuálne nastavených stĺpcov a filtrov. Tu sú rýchle exporty za obdobie s predvolenými stĺpcami." />
      <PeriodPicker value={p} onChange={setP} />
      <Card title="Rýchle exporty">
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {ENTITIES.map(([e, label, df]) => (
            <li key={e} className="flex items-center justify-between py-2">
              <span>{label}{!df && <span className="text-xs text-slate-500"> (bez obmedzenia obdobia)</span>}</span>
              <span className="flex gap-2">
                <a className="btn-secondary btn-sm" href={url(e, df, "xlsx")}><Download className="h-3.5 w-3.5" /> XLSX</a>
                <a className="btn-secondary btn-sm" href={url(e, df, "csv")}>CSV</a>
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Ďalšie výstupy">
        <ul className="list-inside list-disc space-y-1 text-sm">
          <li><Link className="link" to="/vystupy/fakturacia">Podklad k fakturácii</Link> – PDF, XLSX, CSV</li>
          <li><Link className="link" to="/vystupy/pracovnik">Podklad pre pracovníka</Link> – PDF, XLSX</li>
          <li><Link className="link" to="/financie/dph">Mesačný súhrn DPH</Link></li>
          <li><Link className="link" to="/financie/mesacna-kontrola">Mesačná kontrola – čo chýba</Link> a <Link className="link" to="/financie/banka">banka – čo chýba</Link></li>
        </ul>
      </Card>
    </div>
  );
}
