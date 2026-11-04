import { monthRange, yearRange } from "@/lib/format";
import { DateInput } from "./inputs";

export type Period = { from: string | null; to: string | null };

export function PeriodPicker({ value, onChange, allowAll = true }: {
  value: Period; onChange: (p: Period) => void; allowAll?: boolean;
}) {
  const set = (r: [string, string]) => onChange({ from: r[0], to: r[1] });
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="w-36">
        <label className="label">Od</label>
        <DateInput value={value.from} onChange={(v) => onChange({ ...value, from: v })} />
      </div>
      <div className="w-36">
        <label className="label">Do</label>
        <DateInput value={value.to} onChange={(v) => onChange({ ...value, to: v })} />
      </div>
      <div className="flex flex-wrap gap-1 pb-0.5">
        <button className="btn-secondary btn-sm" onClick={() => set(monthRange(0))}>Tento mesiac</button>
        <button className="btn-secondary btn-sm" onClick={() => set(monthRange(-1))}>Minulý mesiac</button>
        <button className="btn-secondary btn-sm" onClick={() => set(yearRange())}>Tento rok</button>
        {allowAll && <button className="btn-secondary btn-sm" onClick={() => onChange({ from: null, to: null })}>Celé obdobie</button>}
      </div>
    </div>
  );
}

export function MonthPicker({ year, month, onChange }: { year: number; month: number; onChange: (y: number, m: number) => void }) {
  const shift = (d: number) => {
    const dt = new Date(year, month - 1 + d, 1);
    onChange(dt.getFullYear(), dt.getMonth() + 1);
  };
  const MONTHS = ["január", "február", "marec", "apríl", "máj", "jún", "júl", "august", "september", "október", "november", "december"];
  return (
    <div className="flex items-center gap-2">
      <button className="btn-secondary btn-sm" onClick={() => shift(-1)} aria-label="Predchádzajúci mesiac">‹</button>
      <select className="input w-auto py-1" value={month} onChange={(e) => onChange(year, Number(e.target.value))}>
        {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </select>
      <input className="input w-20 py-1" type="number" value={year} onChange={(e) => onChange(Number(e.target.value), month)} />
      <button className="btn-secondary btn-sm" onClick={() => shift(1)} aria-label="Nasledujúci mesiac">›</button>
    </div>
  );
}
