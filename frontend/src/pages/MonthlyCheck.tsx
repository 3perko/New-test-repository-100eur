import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/format";
import { MonthPicker } from "@/components/PeriodPicker";
import { Badge, Card, PageHeader, Spinner } from "@/components/ui";

type Any = Record<string, unknown>;
interface MC {
  missing_recurring: Any[]; receipts_without_original: Any[]; documents_in_review: Any[]; material_without_document: Any[];
  incomplete_timesheets: Any[]; bank_without_document: Any[]; documents_without_payment: Any[]; amount_mismatches: Any[];
  fleet_alerts: Any[]; file_errors: Any[];
}

function Section({ title, items, render }: { title: string; items: Any[]; render: (x: Any) => ReactNode }) {
  return (
    <Card title={<span className="flex items-center gap-2">{title} <Badge color={items.length ? "amber" : "green"}>{items.length}</Badge></span>}>
      {items.length === 0 ? <p className="flex items-center gap-1.5 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" /> V poriadku</p> : (
        <ul className="max-h-72 space-y-1 overflow-y-auto text-sm">{items.map((x, i) => <li key={i}>{render(x)}</li>)}</ul>
      )}
    </Card>
  );
}

export default function MonthlyCheck() {
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const q = useQuery({ queryKey: ["monthly-check", ym], queryFn: () => api.get<MC>("/api/reports/monthly-check", { year: ym.y, month: ym.m }) });
  const d = q.data;
  const doc = (x: Any, label?: string) => <Link className="link" to={`/doklady/${x.id}`}>{label ?? `${fmtDate(x.date)} ${x.partner ?? ""}`}</Link>;
  return (
    <div className="space-y-4">
      <PageHeader title="Mesačná kontrola" sub="Čo treba dorobiť za mesiac v aktívnej firme." actions={<MonthPicker year={ym.y} month={ym.m} onChange={(y, m) => setYm({ y, m })} />} />
      {q.isLoading || !d ? <Spinner /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Section title="Chýbajúce povinné faktúry" items={d.missing_recurring} render={(x) => String(x.message)} />
          <Section title="Doklady čakajúce na kontrolu" items={d.documents_in_review} render={(x) => <>{doc(x)} – {fmtMoney(x.total_gross)}</>} />
          <Section title="Bločky bez fyzického originálu" items={d.receipts_without_original} render={(x) => <>{doc(x)} – {fmtMoney(x.total_gross)}</>} />
          <Section title="Hlásený nákup materiálu bez dokladu" items={d.material_without_document} render={(x) => String(x.message)} />
          <Section title="Neúplné záznamy hodín" items={d.incomplete_timesheets} render={(x) => <>{fmtDate(x.date)} {String(x.worker ?? "")} – chýba zákazka alebo čas</>} />
          <Section title="Bankové pohyby bez dokladu" items={d.bank_without_document} render={(x) => <Link className="link" to={`/financie/banka/pohyb/${x.id}`}>{fmtDate(x.date)} {String(x.counterparty ?? x.message ?? "")} {fmtMoney(x.amount)}</Link>} />
          <Section title="Faktúry po splatnosti bez úhrady" items={d.documents_without_payment} render={(x) => <>{doc(x, `${x.number ?? `#${x.id}`} ${x.partner ?? ""}`)} – splatnosť {fmtDate(x.due_date)}, {fmtMoney(x.total_gross)}</>} />
          <Section title="Nezhody v sume (banka)" items={d.amount_mismatches} render={(x) => <>{fmtDate(x.date)} {String(x.counterparty ?? "")}: {fmtMoney(x.amount)} vs. {fmtMoney(x.matched_amount)}</>} />
          <Section title="Upozornenia vozového parku" items={d.fleet_alerts} render={(x) => <><b>{String(x.vehicle)}</b>: {String(x.message)}</>} />
          <Section title="Chyby spracovania súborov" items={d.file_errors} render={(x) => <>{String(x.name)}: {String(x.error ?? "")}</>} />
        </div>
      )}
    </div>
  );
}
