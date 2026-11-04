import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Camera, CheckCircle2, Search, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";
import { Card, PageHeader, Spinner, useToast } from "@/components/ui";

interface Res {
  found: boolean; ekasa_id: string | null; document_id?: number; partner_name?: string; total_gross?: number; issue_date?: string;
  received_at?: string; received_from?: string; received_file?: string; physical_original?: boolean; marked_physical?: boolean;
  message: string; created?: { document_id?: number }[];
}
const FROM: Record<string, string> = { upload: "nahratý ručne", drive: "Google Drive", email: "e-mail", whatsapp: "WhatsApp" };

export default function QuickCheck() {
  const [busy, setBusy] = useState(false);
  const [id, setId] = useState("");
  const [mark, setMark] = useState(true);
  const [res, setRes] = useState<Res | null>(null);
  const cam = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const check = async (file?: File) => {
    setBusy(true);
    setRes(null);
    const fd = new FormData();
    if (file) fd.append("file", file);
    fd.append("ekasa_id", id);
    fd.append("mark_physical", String(mark));
    try {
      setRes(await api.upload<Res>("/api/receipts/quick-check", fd));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
      if (cam.current) cam.current.value = "";
    }
  };
  return (
    <div className="mx-auto max-w-xl space-y-4">
      <PageHeader title="Rýchla kontrola bločku" sub="Odfoťte bloček (QR kód) alebo zadajte ID dokladu. Systém povie, či ho už máte, a označí ho ako fyzicky založený." />
      <Card>
        <div className="space-y-3">
          <button className="btn-primary w-full py-3 text-base" onClick={() => cam.current?.click()} disabled={busy}>
            {busy ? <Spinner /> : <Camera className="h-5 w-5" />} Odfotiť / vybrať fotku bločku
          </button>
          <input ref={cam} type="file" accept="image/*" capture="environment" hidden onChange={(e) => e.target.files?.[0] && check(e.target.files[0])} />
          <div className="flex gap-2">
            <input className="input font-mono text-xs" placeholder="alebo ID dokladu O-…" value={id} onChange={(e) => setId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && check()} />
            <button className="btn-secondary" onClick={() => check()} disabled={busy || !id.trim()}><Search className="h-4 w-4" /></button>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-600" checked={mark} onChange={(e) => setMark(e.target.checked)} /> ak existuje, označiť ako fyzicky založený</label>
        </div>
      </Card>
      {res && (
        <Card>
          <div className="flex gap-3">
            {res.found ? <CheckCircle2 className="h-8 w-8 shrink-0 text-emerald-600" /> : <XCircle className="h-8 w-8 shrink-0 text-amber-500" />}
            <div className="space-y-1 text-sm">
              <p className="text-base font-semibold">{res.message}</p>
              {res.ekasa_id && <p className="font-mono text-xs text-slate-500">{res.ekasa_id}</p>}
              {res.found && (
                <>
                  <p>{res.partner_name} · {fmtDate(res.issue_date)} · <b>{fmtMoney(res.total_gross)}</b></p>
                  <p>Prišiel {fmtDateTime(res.received_at)} {res.received_from && `(${FROM[res.received_from] ?? res.received_from}${res.received_file ? `, ${res.received_file}` : ""})`}</p>
                  <p>{res.physical_original || res.marked_physical ? "✓ Fyzický originál je založený." : "Fyzický originál zatiaľ nie je označený."}</p>
                  <Link className="link" to={`/doklady/${res.document_id}`}>Otvoriť doklad</Link>
                </>
              )}
              {res.created?.[0]?.document_id && <Link className="link" to={`/doklady/${res.created[0].document_id}`}>Otvoriť nový záznam</Link>}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
