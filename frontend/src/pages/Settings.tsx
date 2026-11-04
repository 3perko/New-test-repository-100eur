import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Link2, Play, Save, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { Card, PageHeader, Spinner, useToast } from "@/components/ui";
import { Link } from "react-router-dom";

interface Param { key: string; label: string; type: string; help: string; company_level: boolean; default: unknown; global_value: unknown; company_value: unknown; effective: unknown }

function toText(v: unknown, type: string) {
  if (v === null || v === undefined) return "";
  if (type === "list") return (v as string[]).join(", ");
  if (type === "bool") return v ? "true" : "false";
  return String(v).replace(".", ",");
}
function fromText(s: string, type: string): unknown {
  if (s.trim() === "") return null;
  if (type === "list") return s.split(",").map((x) => x.trim()).filter(Boolean);
  if (type === "bool") return s === "true";
  if (type === "number") return s.replace(",", ".");
  return s;
}

export function Parameters() {
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Param[]>("/api/settings") });
  const { company } = useAuth();
  const [vals, setVals] = useState<Record<string, { global: string; company: string }>>({});
  const qc = useQueryClient();
  const toast = useToast();
  useEffect(() => {
    if (!q.data) return;
    const v: Record<string, { global: string; company: string }> = {};
    for (const p of q.data) v[p.key] = { global: toText(p.global_value, p.type), company: toText(p.company_value, p.type) };
    setVals(v);
  }, [q.data]);
  const save = async () => {
    const body: Record<string, { scope: string; value: unknown }> = {};
    for (const p of q.data ?? []) {
      const v = vals[p.key];
      if (!v) continue;
      if (v.global !== toText(p.global_value, p.type)) body[p.key] = { scope: "global", value: fromText(v.global, p.type) };
      if (p.company_level && v.company !== toText(p.company_value, p.type)) {
        await api.put("/api/settings", { [p.key]: { scope: "company", value: fromText(v.company, p.type) } }).catch((e) => toast.error(e));
      }
    }
    try {
      if (Object.keys(body).length) await api.put("/api/settings", body);
      toast.ok("Parametre uložené");
      await qc.invalidateQueries({ queryKey: ["settings"] });
    } catch (e) {
      toast.error(e);
    }
  };
  if (q.isLoading) return <Spinner />;
  return (
    <div className="space-y-4">
      <PageHeader title="Parametre" sub={`Globálna hodnota platí pre všetky firmy; hodnota pre firmu (${company?.name}) ju prepíše. Prázdne = default.`}
        actions={<button className="btn-primary" onClick={save}><Save className="h-4 w-4" /> Uložiť</button>} />
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr><th className="th">Parameter</th><th className="th">Default</th><th className="th">Globálne</th><th className="th">Pre aktívnu firmu</th><th className="th">Platí</th></tr></thead>
          <tbody>{q.data?.map((p) => (
            <tr key={p.key}>
              <td className="td"><div className="font-medium">{p.label}</div>{p.help && <div className="text-xs text-slate-500">{p.help}</div>}</td>
              <td className="td text-slate-500">{toText(p.default, p.type)}</td>
              <td className="td">{p.type === "bool" ? (
                <select className="input" value={vals[p.key]?.global ?? ""} onChange={(e) => setVals({ ...vals, [p.key]: { ...vals[p.key], global: e.target.value } })}>
                  <option value="">—</option><option value="true">áno</option><option value="false">nie</option></select>
              ) : <input className="input" value={vals[p.key]?.global ?? ""} placeholder={p.type === "time" ? "HH:MM" : ""}
                onChange={(e) => setVals({ ...vals, [p.key]: { ...vals[p.key], global: e.target.value } })} />}</td>
              <td className="td">{p.company_level ? (p.type === "bool" ? (
                <select className="input" value={vals[p.key]?.company ?? ""} onChange={(e) => setVals({ ...vals, [p.key]: { ...vals[p.key], company: e.target.value } })}>
                  <option value="">—</option><option value="true">áno</option><option value="false">nie</option></select>
              ) : <input className="input" value={vals[p.key]?.company ?? ""} onChange={(e) => setVals({ ...vals, [p.key]: { ...vals[p.key], company: e.target.value } })} />)
                : <span className="text-xs text-slate-400">len globálne</span>}</td>
              <td className="td font-medium">{toText(p.effective, p.type)}</td>
            </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface Integ {
  google: { configured: boolean; connected: boolean; email: string | null; connected_at: string | null; redirect_uri: string; last_sync: string | null };
  claude: { configured: boolean; model: string };
  ekasa: { enabled: boolean; url: string };
  inbox_last_run: string | null;
  company: { name: string; drive_inbox_folder_id: string | null; drive_processed_folder_id: string | null; drive_bank_inbox_folder_id: string | null; email_tag_invoices: string | null; email_tag_bank: string | null };
  vehicle_checks: { service: string; label: string; url: string; has_api: boolean }[];
}

function Ok({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <span className="flex items-center gap-1.5">{ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-slate-400" />}{children}</span>;
}

export function Integrations() {
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<Integ>("/api/integrations") });
  const toast = useToast();
  const qc = useQueryClient();
  const [rid, setRid] = useState("");
  const [running, setRunning] = useState(false);
  if (q.isLoading || !q.data) return <Spinner />;
  const d = q.data;
  const local = d.google.email?.split("@")[0];
  return (
    <div className="space-y-4">
      <PageHeader title="Integrácie" sub="Google Drive a Gmail, eKasa, Claude API, banky a overenie vozidiel." />
      <Card title="Google Drive + Gmail" actions={d.google.connected ? (
        <button className="btn-secondary btn-sm" onClick={async () => { await api.post("/api/integrations/google/disconnect"); await qc.invalidateQueries({ queryKey: ["integrations"] }); }}>Odpojiť</button>
      ) : (
        <button className="btn-primary btn-sm" disabled={!d.google.configured} onClick={async () => {
          try { const r = await api.get<{ url: string }>("/api/integrations/google/auth-url"); location.href = r.url; } catch (e) { toast.error(e); }
        }}><Link2 className="h-3.5 w-3.5" /> Pripojiť Google účet</button>
      )}>
        <div className="space-y-2 text-sm">
          <Ok ok={d.google.configured}>OAuth klient {d.google.configured ? "nakonfigurovaný" : "chýba – nastavte GOOGLE_CLIENT_ID a GOOGLE_CLIENT_SECRET v .env (pozri README)"}</Ok>
          <Ok ok={d.google.connected}>{d.google.connected ? `Pripojený účet ${d.google.email} (${fmtDateTime(d.google.connected_at)})` : "Google účet nie je pripojený"}</Ok>
          <p className="text-xs text-slate-500">Redirect URI pre Google Cloud Console: <code>{d.google.redirect_uri}</code></p>
          <div className="rounded-md bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="mb-1 font-medium">Aktívna firma: {d.company.name}</div>
            <Ok ok={!!d.company.drive_inbox_folder_id}>Drive inbox „na spracovanie“: {d.company.drive_inbox_folder_id ?? "nenastavený"}</Ok>
            <Ok ok={!!d.company.drive_processed_folder_id}>Drive „spracované“: {d.company.drive_processed_folder_id ?? "nenastavený"}</Ok>
            <Ok ok={!!d.company.drive_bank_inbox_folder_id}>Drive bankový inbox: {d.company.drive_bank_inbox_folder_id ?? "nenastavený"}</Ok>
            <Ok ok={!!d.company.email_tag_invoices}>E-mail pre faktúry: {d.company.email_tag_invoices ? `${local ?? "meno"}+${d.company.email_tag_invoices}@gmail.com` : "nenastavený"}</Ok>
            <Ok ok={!!d.company.email_tag_bank}>E-mail pre výpisy: {d.company.email_tag_bank ? `${local ?? "meno"}+${d.company.email_tag_bank}@gmail.com` : "nenastavený"}</Ok>
            <p className="mt-1 text-xs text-slate-500">Priečinky a e-mailové tagy nastavíte v <Link className="link" to="/ciselniky/firmy">Číselníky → Firmy</Link>.</p>
          </div>
          <div className="flex items-center gap-3">
            <button className="btn-secondary btn-sm" disabled={running} onClick={async () => {
              setRunning(true);
              try {
                const r = await api.post<{ processed: unknown[]; errors: string[] }>("/api/inbox/run");
                toast.ok(`Spracované súbory: ${r.processed.length}${r.errors.length ? ` · ${r.errors.join("; ")}` : ""}`);
                await qc.invalidateQueries({ queryKey: ["integrations"] });
              } catch (e) { toast.error(e); } finally { setRunning(false); }
            }}>{running ? <Spinner /> : <Play className="h-3.5 w-3.5" />} Spracovať inbox teraz</button>
            <span className="text-xs text-slate-500">Posledné spracovanie: {fmtDateTime(d.inbox_last_run) || "–"}. Automaticky denne podľa parametra „Čas automatického spracovania inboxu“.</span>
          </div>
        </div>
      </Card>
      <Card title="Claude API (čítanie dokladov)">
        <Ok ok={d.claude.configured}>{d.claude.configured ? `Nakonfigurované, model ${d.claude.model}` : "Nenakonfigurované – nastavte ANTHROPIC_API_KEY v .env. Bez neho sa doklady bez eKasa zadávajú ručne."}</Ok>
      </Card>
      <Card title="eKasa (Finančná správa SR)">
        <div className="space-y-2 text-sm">
          <Ok ok={d.ekasa.enabled}>{d.ekasa.enabled ? "Zapnuté" : "Vypnuté"} – {d.ekasa.url}</Ok>
          <div className="flex gap-2">
            <input className="input max-w-md font-mono text-xs" placeholder="ID dokladu O-… na test" value={rid} onChange={(e) => setRid(e.target.value)} />
            <button className="btn-secondary btn-sm" disabled={!rid} onClick={async () => {
              const r = await api.post<{ ok: boolean; error?: string; partner_name?: string; total_gross?: number }>("/api/integrations/ekasa/test", { receipt_id: rid });
              if (r.ok) toast.ok(`eKasa OK: ${r.partner_name}, ${r.total_gross} €`); else toast.error(r.error ?? "chyba");
            }}>Otestovať</button>
          </div>
        </div>
      </Card>
      <Card title="Banky">
        <p className="text-sm">Výpisy importujte v <Link className="link" to="/financie/banka">Financie → Banka</Link> alebo cez e-mail / Drive bankový inbox. Podporované: CAMT.053 (XML), CSV, XLSX, PDF (cez Claude API). Priame napojenie na banky cez API je v neskoršej fáze.</p>
      </Card>
      <Card title="Overenie vozidiel">
        <ul className="space-y-1 text-sm">{d.vehicle_checks.map((v) => (
          <li key={v.service}><Ok ok={v.has_api}>{v.label}: {v.has_api ? "automaticky (API)" : <>odkaz na <a className="link" href={v.url} target="_blank" rel="noreferrer">{v.url}</a></>}</Ok></li>))}</ul>
      </Card>
    </div>
  );
}
