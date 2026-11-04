import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { DateInput } from "@/components/inputs";
import { Badge, Card, Empty, Modal, PageHeader, Spinner, useToast } from "@/components/ui";

interface Svc {
  service: string; label: string; url: string; has_api: boolean; note: string; recorded_valid_to: string | null;
  last_check: null | { checked_at: string; result: string; valid_to: string | null; matches: boolean | null; method: string; note: string | null };
}
interface VRow { vehicle_id: number; name: string; plate: string | null; vin: string | null; services: Svc[] }
interface Alert { vehicle: string; kind: string; severity: string; message: string }

export default function VehicleCheck() {
  const q = useQuery({ queryKey: ["fleet-checks"], queryFn: () => api.get<VRow[]>("/api/fleet/checks") });
  const alerts = useQuery({ queryKey: ["fleet-alerts"], queryFn: () => api.get<Alert[]>("/api/fleet/alerts") });
  const [rec, setRec] = useState<{ vehicle: VRow; svc: Svc } | null>(null);
  const toast = useToast();
  return (
    <div className="space-y-4">
      <PageHeader title="Overenie vozidla" sub="Overenie údajov podľa ŠPZ na verejných overovacích službách. Ak služba nemá API, otvorte odkaz (ŠPZ sa skopíruje), overte a zapíšte výsledok – porovná sa s evidenciou." />
      <Card title="Upozornenia vozového parku">
        {alerts.isLoading ? <Spinner /> : alerts.data?.length === 0 ? <Empty>Žiadne blížiace sa ani prekročené platnosti.</Empty> : (
          <ul className="space-y-1 text-sm">
            {alerts.data?.map((a, i) => (
              <li key={i}><Badge color={a.severity === "error" ? "red" : a.severity === "missing" ? "gray" : "amber"}>{a.severity === "error" ? "prekročené" : a.severity === "missing" ? "chýba" : "blíži sa"}</Badge> <b>{a.vehicle}</b>: {a.message}</li>
            ))}
          </ul>
        )}
      </Card>
      {q.isLoading ? <Spinner /> : q.data?.length === 0 ? <Empty>Firma nemá aktívne vozidlá.</Empty> : q.data?.map((v) => (
        <Card key={v.vehicle_id} title={`${v.name} ${v.plate ? `(${v.plate})` : ""}`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr><th className="th">Služba</th><th className="th">Platnosť v evidencii</th><th className="th">Posledné overenie</th><th className="th">Výsledok</th><th className="th" /></tr></thead>
              <tbody>
                {v.services.map((s) => (
                  <tr key={s.service}>
                    <td className="td">{s.label}</td>
                    <td className="td">{fmtDate(s.recorded_valid_to) || <span className="text-amber-600">neevidované</span>}</td>
                    <td className="td">{s.last_check ? `${fmtDateTime(s.last_check.checked_at)} (${s.last_check.method === "api" ? "API" : "ručne"})` : "–"}</td>
                    <td className="td">{s.last_check && <>
                      <Badge color={s.last_check.result === "valid" ? "green" : s.last_check.result === "invalid" ? "red" : "gray"}>
                        {{ valid: "platné", invalid: "neplatné", unknown: "nezistené", error: "chyba" }[s.last_check.result] ?? s.last_check.result}</Badge>
                      {s.last_check.valid_to && ` do ${fmtDate(s.last_check.valid_to)}`}
                      {s.last_check.matches === false && <Badge color="red">nezhoda s evidenciou</Badge>}
                      {s.last_check.matches === true && <Badge color="green">zhoda</Badge>}
                    </>}</td>
                    <td className="td whitespace-nowrap text-right">
                      <a className="btn-secondary btn-sm" href={s.url} target="_blank" rel="noreferrer" title={s.note}
                        onClick={() => { if (v.plate) { void navigator.clipboard?.writeText(v.plate).catch(() => undefined); toast.info(`ŠPZ ${v.plate} skopírovaná`); } }}>
                        <ExternalLink className="h-3.5 w-3.5" /> Overiť
                      </a>{" "}
                      <button className="btn-secondary btn-sm" onClick={() => setRec({ vehicle: v, svc: s })}><Copy className="h-3.5 w-3.5" /> Zapísať výsledok</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
      {rec && <RecordModal v={rec.vehicle} s={rec.svc} onClose={() => setRec(null)} />}
    </div>
  );
}

function RecordModal({ v, s, onClose }: { v: VRow; s: Svc; onClose: () => void }) {
  const [result, setResult] = useState("valid");
  const [validTo, setValidTo] = useState<string | null>(s.recorded_valid_to);
  const [note, setNote] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const save = async () => {
    try {
      const r = await api.post<{ matches: boolean | null }>("/api/data/vehicle_checks", { vehicle_id: v.vehicle_id, service: s.service, result, valid_to: validTo, note });
      toast[r.matches === false ? "error" : "ok"](r.matches === false ? "Uložené – výsledok NESEDÍ s evidenciou, skontrolujte údaje." : "Uložené");
      await qc.invalidateQueries({ queryKey: ["fleet-checks"] });
      onClose();
    } catch (e) {
      toast.error(e);
    }
  };
  return (
    <Modal open onClose={onClose} title={`${s.label} – ${v.name} ${v.plate ?? ""}`}
      footer={<><button className="btn-secondary" onClick={onClose}>Zrušiť</button><button className="btn-primary" onClick={save}>Uložiť</button></>}>
      <div className="space-y-3">
        <div><label className="label">Výsledok overenia</label>
          <select className="input" value={result} onChange={(e) => setResult(e.target.value)}>
            <option value="valid">platné</option><option value="invalid">neplatné</option><option value="unknown">nezistené</option>
          </select></div>
        <div><label className="label">Zistená platnosť do</label><DateInput value={validTo} onChange={setValidTo} /></div>
        <div><label className="label">Poznámka</label><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      </div>
    </Modal>
  );
}
