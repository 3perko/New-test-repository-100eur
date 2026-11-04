// Slovak formatting: decimal comma, space thousands separator, €, 24h time, DD.MM.RRRR dates.

const nf2 = new Intl.NumberFormat("sk-SK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nfAuto = new Intl.NumberFormat("sk-SK", { maximumFractionDigits: 2 });

export function fmtMoney(v: unknown): string {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return `${nf2.format(n)} €`;
}

export function fmtNum(v: unknown, decimals?: number): string {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  if (decimals !== undefined)
    return new Intl.NumberFormat("sk-SK", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(n);
  return nfAuto.format(n);
}

export function fmtPct(v: unknown): string {
  if (v === null || v === undefined) return "–";
  return `${fmtNum(v, 1)} %`;
}

export function fmtDate(v: unknown): string {
  if (!v) return "";
  const s = String(v);
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (!m) return s;
  return `${m[3]}.${m[2]}.${m[1]}`;
}

export function fmtDateTime(v: unknown): string {
  if (!v) return "";
  const d = new Date(String(v));
  if (Number.isNaN(d.getTime())) return String(v);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fmtTime(v: unknown): string {
  if (!v) return "";
  return String(v).slice(0, 5);
}

/** Parse Slovak date input: 5.11.2026, 5.11., 5/11/26, 2026-11-05, "dnes" */
export function parseDate(input: string): string | null {
  const s = input.trim().toLowerCase();
  if (!s) return null;
  const today = new Date();
  if (s === "dnes" || s === "d") return isoDate(today);
  if (s === "vcera" || s === "včera") {
    today.setDate(today.getDate() - 1);
    return isoDate(today);
  }
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s);
  if (m) return valid(+m[1], +m[2], +m[3]);
  m = /^(\d{1,2})[.\/\- ]\s*(\d{1,2})[.\/\- ]?\s*(\d{2,4})?$/.exec(s);
  if (m) {
    let y = m[3] ? +m[3] : today.getFullYear();
    if (y < 100) y += 2000;
    return valid(y, +m[2], +m[1]);
  }
  m = /^(\d{2})(\d{2})(\d{4})$/.exec(s);
  if (m) return valid(+m[3], +m[2], +m[1]);
  return null;
}

function valid(y: number, mo: number, d: number): string | null {
  const dt = new Date(y, mo - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return isoDate(dt);
}

export function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Parse 24h time: 7 -> 07:00, 730 -> 07:30, 7:5 -> 07:05, 7.30 -> 07:30 */
export function parseTime(input: string): string | null {
  const s = input.trim().replace(/[.,h ]/g, ":");
  if (!s) return null;
  let h: number, m: number;
  let mm = /^(\d{1,2}):(\d{1,2})$/.exec(s);
  if (mm) {
    h = +mm[1];
    m = +mm[2];
  } else if ((mm = /^(\d{1,2})$/.exec(s))) {
    h = +mm[1];
    m = 0;
  } else if ((mm = /^(\d{1,2})(\d{2})$/.exec(s))) {
    h = +mm[1];
    m = +mm[2];
  } else return null;
  if (h > 24 || m > 59 || (h === 24 && m > 0)) return null;
  if (h === 24) h = 0;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Parse number with decimal comma and spaces */
export function parseNum(input: string): number | null {
  const s = input.replace(/\s| |€/g, "").replace(",", ".");
  if (!s) return null;
  const n = Number(s);
  return Number.isNaN(n) ? null : n;
}

export function hoursBetween(from: string, to: string, rounding = 0.25): number | null {
  const a = parseTime(from);
  const b = parseTime(to);
  if (!a || !b) return null;
  const [ah, am] = a.split(":").map(Number);
  const [bh, bm] = b.split(":").map(Number);
  let diff = bh * 60 + bm - (ah * 60 + am);
  if (diff <= 0) diff += 24 * 60;
  let h = diff / 60;
  if (rounding > 0) h = Math.round(h / rounding) * rounding;
  return Math.round(h * 100) / 100;
}

export function monthRange(offset = 0): [string, string] {
  const d = new Date();
  const first = new Date(d.getFullYear(), d.getMonth() + offset, 1);
  const last = new Date(d.getFullYear(), d.getMonth() + offset + 1, 0);
  return [isoDate(first), isoDate(last)];
}

export function yearRange(): [string, string] {
  const y = new Date().getFullYear();
  return [`${y}-01-01`, `${y}-12-31`];
}

export const MONTHS = [
  "január", "február", "marec", "apríl", "máj", "jún", "júl", "august", "september", "október", "november", "december",
];
