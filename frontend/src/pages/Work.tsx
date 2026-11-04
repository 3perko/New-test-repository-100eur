import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Save } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { hoursBetween, isoDate } from "@/lib/format";
import { DataTable, useEntityMeta } from "@/components/DataTable";
import { DateInput, MultiRefSelect, NumberInput, RefSelect, TimeInput } from "@/components/inputs";
import { Card, PageHeader, Spinner, useToast } from "@/components/ui";

function useRounding() {
  const { isAdmin } = useAuth();
  const q = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<{ key: string; effective: unknown }[]>("/api/settings"),
    enabled: isAdmin,
    staleTime: 300_000,
  });
  const v = q.data?.find((s) => s.key === "hours_rounding")?.effective;
  return v === undefined ? 0.25 : Number(v);
}

// ----------------------------------------------------------------------------- Hours
export function HoursPage() {
  const { isAdmin, me } = useAuth();
  const [show, setShow] = useState(true);
  return (
    <div className="space-y-4">
      <PageHeader title="Hodiny" sub="Čas vo formáte 24 h. Hodiny sa vypočítajú z času od–do (môžete ich prepísať). Sadzby sa k záznamu zafixujú."
        actions={<button className="btn-secondary btn-sm md:hidden" onClick={() => setShow(!show)}>{show ? "Skryť formulár" : "Zadať hodiny"}</button>} />
      {show && <QuickHours isAdmin={isAdmin} workerId={me?.worker_id ?? null} />}
      <DataTable entity="timesheets" hideCreate
        initial={{ columns: isAdmin ? ["date", "worker_id", "project_id", "time_from", "time_to", "hours", "description", "material_bought", "cost_amount"]
          : ["date", "project_id", "time_from", "time_to", "hours", "description", "material_bought"] }} />
    </div>
  );
}

function QuickHours({ isAdmin, workerId }: { isAdmin: boolean; workerId: number | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const rounding = useRounding();
  const meta = useEntityMeta("timesheets");
  const blank = useMemo(() => ({ date: isoDate(new Date()), worker_id: workerId, project_id: null as number | null,
    time_from: null as string | null, time_to: null as string | null, hours: null as number | null, description: "",
    material_bought: false, billable: true }), [workerId]);
  const [v, setV] = useState(blank);
  const [hoursTouched, setHoursTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!hoursTouched && v.time_from && v.time_to) {
      const h = hoursBetween(v.time_from, v.time_to, rounding);
      if (h !== null && h !== v.hours) setV((o) => ({ ...o, hours: h }));
    }
  }, [v.time_from, v.time_to, hoursTouched, rounding, v.hours]);
  const incomplete = !v.project_id || (!v.hours && !(v.time_from && v.time_to));
  const save = async () => {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = { ...v };
      if (!isAdmin) {
        delete payload.worker_id;
        delete payload.billable;
      }
      if (!hoursTouched && v.time_from && v.time_to) delete payload.hours;
      await api.post("/api/data/timesheets", payload);
      toast.ok(incomplete ? "Uložené – záznam je neúplný" : "Uložené");
      // keep date, worker and project for fast entry of the next record
      setV({ ...blank, date: v.date, worker_id: v.worker_id, project_id: v.project_id });
      setHoursTouched(false);
      await qc.invalidateQueries({ queryKey: ["data", "timesheets"] });
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  if (!meta.data) return <Spinner />;
  return (
    <Card title="Rýchle zadanie hodín">
      <form className="grid grid-cols-2 gap-3 md:grid-cols-12" onSubmit={(e) => { e.preventDefault(); void save(); }}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void save(); } }}>
        <div className="md:col-span-2"><label className="label">Dátum</label><DateInput value={v.date} onChange={(x) => setV({ ...v, date: x ?? "" })} /></div>
        {isAdmin && <div className="md:col-span-2"><label className="label">Pracovník</label><RefSelect entity="workers" value={v.worker_id} onChange={(x) => setV({ ...v, worker_id: x })} /></div>}
        <div className={isAdmin ? "md:col-span-3" : "md:col-span-4"}><label className="label">Zákazka</label><RefSelect entity="projects" value={v.project_id} onChange={(x) => setV({ ...v, project_id: x })} /></div>
        <div className="md:col-span-1"><label className="label">Od</label><TimeInput value={v.time_from} onChange={(x) => setV({ ...v, time_from: x })} /></div>
        <div className="md:col-span-1"><label className="label">Do</label><TimeInput value={v.time_to} onChange={(x) => setV({ ...v, time_to: x })} /></div>
        <div className="md:col-span-1"><label className="label">Hodiny</label><NumberInput value={v.hours} onChange={(x) => { setHoursTouched(true); setV({ ...v, hours: x }); }} /></div>
        <div className="col-span-2 md:col-span-2 flex flex-col justify-end gap-1 text-sm">
          <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-brand-600" checked={v.material_bought} onChange={(e) => setV({ ...v, material_bought: e.target.checked })} /> nakúpený materiál</label>
          {isAdmin && <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-brand-600" checked={v.billable} onChange={(e) => setV({ ...v, billable: e.target.checked })} /> fakturovať</label>}
        </div>
        <div className="col-span-2 md:col-span-10"><label className="label">Popis práce</label><input className="input" value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} /></div>
        <div className="col-span-2 flex items-end md:col-span-2">
          <button className="btn-primary w-full" disabled={busy || !v.date}>{busy ? <Spinner /> : <Save className="h-4 w-4" />} Uložiť</button>
        </div>
      </form>
      {incomplete && (v.time_from || v.project_id) && <p className="mt-2 text-xs text-amber-600">Neúplný záznam: chýba {!v.project_id ? "zákazka" : "začiatok alebo koniec"}.</p>}
      <p className="mt-2 text-xs text-slate-500">Tip: Ctrl + Enter uloží; dátum{isAdmin ? ", pracovník" : ""} a zákazka ostanú predvyplnené pre ďalší záznam.</p>
    </Card>
  );
}

// ----------------------------------------------------------------------------- Trips
export function TripsPage() {
  const { isAdmin, me } = useAuth();
  const [show, setShow] = useState(true);
  return (
    <div className="space-y-4">
      <PageHeader title="Jazdy" sub="Jedna jazda = jedno vozidlo. Ak km nevyplníte, dopočítajú sa: 2 × vzdialenosť zákazky + prirážka (default 10 %)."
        actions={<button className="btn-secondary btn-sm md:hidden" onClick={() => setShow(!show)}>{show ? "Skryť formulár" : "Zadať jazdu"}</button>} />
      {show && <QuickTrip workerId={me?.worker_id ?? null} isAdmin={isAdmin} />}
      <DataTable entity="trips" hideCreate
        initial={{ columns: isAdmin ? ["date", "vehicle_id", "project_id", "driver_id", "crew_ids", "km", "km_effective", "cost_amount"]
          : ["date", "vehicle_id", "project_id", "driver_id", "crew_ids", "km_effective"] }} />
    </div>
  );
}

function QuickTrip({ workerId, isAdmin }: { workerId: number | null; isAdmin: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const blank = { date: isoDate(new Date()), vehicle_id: null as number | null, project_id: null as number | null,
    driver_id: workerId, crew_ids: [] as number[], km: null as number | null, note: "" };
  const [v, setV] = useState(blank);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.post("/api/data/trips", v);
      toast.ok("Jazda uložená");
      setV({ ...blank, date: v.date, vehicle_id: v.vehicle_id });
      await qc.invalidateQueries({ queryKey: ["data", "trips"] });
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Rýchle zadanie jazdy">
      <form className="grid grid-cols-2 gap-3 md:grid-cols-12" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <div className="md:col-span-2"><label className="label">Dátum</label><DateInput value={v.date} onChange={(x) => setV({ ...v, date: x ?? "" })} /></div>
        <div className="md:col-span-3"><label className="label">Vozidlo</label><RefSelect entity="vehicles" value={v.vehicle_id} onChange={(x) => setV({ ...v, vehicle_id: x })} /></div>
        <div className="md:col-span-3"><label className="label">Zákazka</label><RefSelect entity="projects" value={v.project_id} onChange={(x) => setV({ ...v, project_id: x })} /></div>
        <div className="md:col-span-2"><label className="label">Vodič</label><RefSelect entity="workers" value={v.driver_id} onChange={(x) => setV({ ...v, driver_id: x })} disabled={!isAdmin && !!workerId} /></div>
        <div className="md:col-span-2"><label className="label">Km (nepovinné)</label><NumberInput value={v.km} onChange={(x) => setV({ ...v, km: x })} placeholder="dopočíta sa" /></div>
        <div className="col-span-2 md:col-span-5"><label className="label">Posádka</label><MultiRefSelect entity="workers" value={v.crew_ids} onChange={(x) => setV({ ...v, crew_ids: x })} /></div>
        <div className="col-span-2 md:col-span-5"><label className="label">Poznámka</label><input className="input" value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} /></div>
        <div className="col-span-2 flex items-end md:col-span-2">
          <button className="btn-primary w-full" disabled={busy || !v.vehicle_id || !v.date}>{busy ? <Spinner /> : <Plus className="h-4 w-4" />} Uložiť</button>
        </div>
      </form>
    </Card>
  );
}
