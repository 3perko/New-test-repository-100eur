import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { DataTable } from "@/components/DataTable";
import { Card, PageHeader, Spinner, useToast } from "@/components/ui";

interface UploadResult {
  stored: { file: string; new: boolean; document_id: number | null }[];
  results: { file: string; status: string; document_id?: number; info?: string; source?: string }[];
}

const STATUS: Record<string, string> = { processed: "spracované", duplicate: "duplicita", error: "chyba" };

export function UploadBox({ kind = "auto", compact = false, onDone }: { kind?: string; compact?: boolean; onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [k, setK] = useState(kind);
  const [physical, setPhysical] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const send = async (files: FileList | File[]) => {
    if (!files.length) return;
    setBusy(true);
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    fd.append("kind", k);
    fd.append("physical", String(physical));
    fd.append("note", note);
    try {
      const r = await api.upload<UploadResult>("/api/inbox/upload", fd);
      setResult(r);
      const dup = r.stored.filter((s) => !s.new).length;
      toast.ok(`Nahraté: ${r.stored.length}${dup ? `, už existujúce súbory: ${dup}` : ""}`);
      onDone?.();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };
  return (
    <div className={`card ${compact ? "p-3" : "p-4"}`}>
      <div
        className={`flex flex-wrap items-center gap-3 rounded-md border-2 border-dashed p-3 ${drag ? "border-brand-500 bg-brand-50 dark:bg-slate-800" : "border-slate-300 dark:border-slate-700"}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void send(e.dataTransfer.files);
        }}>
        <button className="btn-primary btn-sm" onClick={() => input.current?.click()} disabled={busy}>
          {busy ? <Spinner /> : <Upload className="h-4 w-4" />} Nahrať doklady
        </button>
        <input ref={input} type="file" multiple hidden accept="image/*,application/pdf,.xml,.csv,.xlsx"
          onChange={(e) => e.target.files && send(e.target.files)} />
        <span className="text-xs text-slate-500">alebo sem potiahnite súbory (fotky, skeny, PDF)</span>
        <select className="input w-auto py-1 text-sm" value={k} onChange={(e) => setK(e.target.value)}>
          <option value="auto">Rozpoznať automaticky</option>
          <option value="receipt">Bloček</option>
          <option value="invoice_in">Prijatá faktúra</option>
          <option value="invoice_out">Vystavená faktúra</option>
          <option value="bank">Bankový výpis</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" className="accent-brand-600" checked={physical} onChange={(e) => setPhysical(e.target.checked)} /> sken fyzického originálu</label>
        {!compact && <input className="input w-56 py-1 text-sm" placeholder="Poznámka (napr. zákazka)" value={note} onChange={(e) => setNote(e.target.value)} />}
      </div>
      {result && result.results.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm">
          {result.results.map((r, i) => (
            <li key={i}>
              <span className="font-medium">{r.file}</span>: {STATUS[r.status] ?? r.status}
              {r.document_id && <> – <Link className="link" to={`/doklady/${r.document_id}`}>otvoriť doklad #{r.document_id}</Link></>}
              {r.info && <span className="text-slate-500"> ({r.info})</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Inbox() {
  const qc = useQueryClient();
  const toast = useToast();
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    try {
      const r = await api.post<{ processed: unknown[]; errors: string[]; drive: unknown; gmail: unknown }>("/api/inbox/run");
      toast.ok(`Spracované súbory: ${r.processed.length}${r.errors.length ? ` – chyby: ${r.errors.join("; ")}` : ""}`);
      await qc.invalidateQueries({ queryKey: ["data"] });
    } catch (e) {
      toast.error(e);
    } finally {
      setRunning(false);
    }
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Inbox a súbory" sub="Súbory z Google Drive inboxu, e-mailu a ručného nahratia. Rovnaký súbor (podľa hashu) sa spracuje len raz."
        actions={<button className="btn-primary" onClick={run} disabled={running}>{running ? <Spinner /> : <Play className="h-4 w-4" />} Spracovať inbox teraz</button>} />
      <UploadBox onDone={() => qc.invalidateQueries({ queryKey: ["data", "source_files"] })} />
      <Card title="Prijaté súbory">
        <DataTable entity="source_files" hideCreate onOpen={(r) => r.document_id && window.open(`/doklady/${r.document_id}`, "_self")} />
      </Card>
    </div>
  );
}
