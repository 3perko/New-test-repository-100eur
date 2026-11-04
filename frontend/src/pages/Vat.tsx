import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/format";
import { MonthPicker } from "@/components/PeriodPicker";
import { Badge, Card, PageHeader, Spinner, Stat } from "@/components/ui";

interface VatRow { rate: string; base: number; vat: number }
interface VatDoc { id: number; doc_type: string; status: string; date: string; partner: string; partner_ic_dph: string | null; number: string | null; total_net: number; total_vat: number; total_gross: number }
interface VatRes { company: string; vat_payer: boolean; period: string; input: VatRow[]; output: VatRow[]; input_vat: number; output_vat: number; vat_due: number; pending_review: number; documents: { input: VatDoc[]; output: VatDoc[] } }

export default function Vat() {
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const q = useQuery({ queryKey: ["vat", ym], queryFn: () => api.get<VatRes>("/api/reports/vat", { year: ym.y, month: ym.m }) });
  const d = q.data;
  return (
    <div className="space-y-4">
      <PageHeader title="DPH – mesačný prehľad" sub="Podľa dátumu DPH (ak chýba, dátum dokladu). Do súčtov idú len potvrdené doklady aktívnej firmy." actions={<MonthPicker year={ym.y} month={ym.m} onChange={(y, m) => setYm({ y, m })} />} />
      {q.isLoading || !d ? <Spinner /> : (
        <>
          {!d.vat_payer && <p className="rounded-md bg-amber-50 p-3 text-sm dark:bg-amber-950/30">Firma {d.company} nie je platiteľ DPH – prehľad je len informatívny.</p>}
          {d.pending_review > 0 && <p className="text-sm text-amber-700">Pozor: {d.pending_review} dokladov z obdobia čaká na kontrolu a nie je v súčtoch.</p>}
          <div className="grid grid-cols-3 gap-3">
            <Stat label="DPH na výstupe" value={fmtMoney(d.output_vat)} />
            <Stat label="DPH na vstupe (odpočet)" value={fmtMoney(d.input_vat)} />
            <Stat label={d.vat_due >= 0 ? "Daňová povinnosť" : "Nadmerný odpočet"} value={fmtMoney(Math.abs(d.vat_due))} tone={d.vat_due >= 0 ? "red" : "green"} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {(["output", "input"] as const).map((side) => (
              <Card key={side} title={side === "output" ? "Výstup (vystavené faktúry)" : "Vstup (prijaté faktúry a bločky)"}>
                <table className="w-full text-sm">
                  <thead><tr><th className="th">Sadzba</th><th className="th text-right">Základ</th><th className="th text-right">DPH</th></tr></thead>
                  <tbody>{d[side].map((r) => <tr key={r.rate}><td className="td">{r.rate} %</td><td className="td num">{fmtMoney(r.base)}</td><td className="td num">{fmtMoney(r.vat)}</td></tr>)}</tbody>
                </table>
              </Card>
            ))}
          </div>
          {(["output", "input"] as const).map((side) => (
            <Card key={side} title={`Doklady – ${side === "output" ? "výstup" : "vstup"} (${d.documents[side].length})`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr><th className="th">Dátum</th><th className="th">Doklad</th><th className="th">Partner</th><th className="th">IČ DPH</th><th className="th">Stav</th><th className="th text-right">Základ</th><th className="th text-right">DPH</th><th className="th text-right">Spolu</th></tr></thead>
                  <tbody>{d.documents[side].map((x) => (
                    <tr key={x.id}>
                      <td className="td">{fmtDate(x.date)}</td><td className="td"><Link className="link" to={`/doklady/${x.id}`}>{x.number ?? `#${x.id}`}</Link></td>
                      <td className="td">{x.partner}</td><td className="td">{x.partner_ic_dph}</td>
                      <td className="td"><Badge color={x.status === "confirmed" ? "green" : "amber"}>{x.status === "confirmed" ? "potvrdený" : "na kontrolu"}</Badge></td>
                      <td className="td num">{fmtMoney(x.total_net)}</td><td className="td num">{fmtMoney(x.total_vat)}</td><td className="td num">{fmtMoney(x.total_gross)}</td>
                    </tr>))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
