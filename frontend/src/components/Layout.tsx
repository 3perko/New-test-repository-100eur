import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3, Building2, Car, ClipboardCheck, FileSpreadsheet, FileText, Landmark, LayoutDashboard, ListChecks, LogOut,
  Menu, Moon, Receipt, ScanLine, Settings, Sun, Timer, TrendingUp, Truck, Users, Wrench, X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

interface NavItem { to: string; label: string; icon?: ReactNode; worker?: boolean }
interface NavGroup { label: string; items: NavItem[] }

const ic = (C: typeof Receipt) => <C className="h-4 w-4" />;

export const NAV: NavGroup[] = [
  { label: "Prehľady", items: [
    { to: "/", label: "Dashboard", icon: ic(LayoutDashboard) },
    { to: "/zakazky-naklady", label: "Zákazky – náklady", icon: ic(BarChart3) },
    { to: "/ziskovost", label: "Ziskovosť", icon: ic(TrendingUp) },
  ] },
  { label: "Doklady", items: [
    { to: "/doklady/na-kontrolu", label: "Na kontrolu", icon: ic(ClipboardCheck) },
    { to: "/doklady/blocky", label: "Bločky", icon: ic(Receipt) },
    { to: "/doklady/prijate", label: "Prijaté faktúry", icon: ic(FileText) },
    { to: "/doklady/vystavene", label: "Vystavené faktúry", icon: ic(FileText) },
    { to: "/doklady/rychla-kontrola", label: "Rýchla kontrola bločku", icon: ic(ScanLine) },
    { to: "/doklady/inbox", label: "Inbox a súbory" },
    { to: "/doklady/polozky", label: "Položky a priradenia" },
  ] },
  { label: "Práca a doprava", items: [
    { to: "/praca/hodiny", label: "Hodiny", icon: ic(Timer), worker: true },
    { to: "/praca/jazdy", label: "Jazdy", icon: ic(Truck), worker: true },
  ] },
  { label: "Vozový park", items: [
    { to: "/vozovy-park/vozidla", label: "Vozidlá", icon: ic(Car) },
    { to: "/vozovy-park/sadzby", label: "Sadzby €/km" },
    { to: "/vozovy-park/poistenie", label: "PZP a poistenie" },
    { to: "/vozovy-park/znamky", label: "Diaľničné známky" },
    { to: "/vozovy-park/servis", label: "Servis", icon: ic(Wrench) },
    { to: "/vozovy-park/overenie", label: "Overenie vozidla" },
  ] },
  { label: "Financie", items: [
    { to: "/financie/dph", label: "DPH" },
    { to: "/financie/banka", label: "Banka", icon: ic(Landmark) },
    { to: "/financie/mesacna-kontrola", label: "Mesačná kontrola", icon: ic(ListChecks) },
    { to: "/financie/pravidla", label: "Pravidlá bankových pohybov" },
  ] },
  { label: "Výstupy", items: [
    { to: "/vystupy/fakturacia", label: "Podklad k fakturácii", icon: ic(FileSpreadsheet) },
    { to: "/vystupy/pracovnik", label: "Podklad pre pracovníka", worker: true },
    { to: "/vystupy/exporty", label: "Exporty" },
  ] },
  { label: "Číselníky", items: [
    { to: "/ciselniky/firmy", label: "Firmy", icon: ic(Building2) },
    { to: "/ciselniky/ucty", label: "Bankové účty" },
    { to: "/ciselniky/rady", label: "Číselné rady" },
    { to: "/ciselniky/odberatelia", label: "Odberatelia" },
    { to: "/ciselniky/zakazky", label: "Zákazky" },
    { to: "/ciselniky/pracovnici", label: "Pracovníci", icon: ic(Users) },
    { to: "/ciselniky/sadzby", label: "Sadzby pracovníkov" },
    { to: "/ciselniky/opakujuce", label: "Opakujúce sa faktúry" },
  ] },
  { label: "Nastavenia", items: [
    { to: "/nastavenia/pouzivatelia", label: "Používatelia a roly", icon: ic(Settings) },
    { to: "/nastavenia/parametre", label: "Parametre" },
    { to: "/nastavenia/integracie", label: "Integrácie" },
    { to: "/nastavenia/audit", label: "Audit log" },
  ] },
];

function useTheme() {
  const [dark, setDark] = useState(() => {
    try {
      const s = localStorage.getItem("naklady.theme");
      if (s) return s === "dark";
    } catch {
      /* ignore */
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("naklady.theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

export function Layout() {
  const { me, company, companyId, switchCompany, logout, isAdmin } = useAuth();
  const [dark, setDark] = useTheme();
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => setMenu(false), [loc.pathname]);
  const groups = NAV.map((g) => ({ ...g, items: g.items.filter((i) => isAdmin || i.worker) })).filter((g) => g.items.length);

  const nav = (
    <nav className="space-y-4 p-3 text-sm">
      {groups.map((g) => (
        <div key={g.label}>
          <div className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{g.label}</div>
          {g.items.map((i) => (
            <NavLink key={i.to} to={i.to} end={i.to === "/"}
              className={({ isActive }) => `flex items-center gap-2 rounded-md px-2 py-1.5 ${isActive ? "bg-brand-600 text-white" : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}>
              <span className="w-4 shrink-0">{i.icon}</span>
              {i.label}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3 dark:border-slate-800 dark:bg-slate-900">
        <button className="btn-ghost btn-sm lg:hidden" onClick={() => setMenu(true)} aria-label="Menu"><Menu className="h-5 w-5" /></button>
        <div className="hidden shrink-0 font-semibold text-brand-700 sm:block dark:text-brand-100">Náklady zákaziek</div>
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:ml-2 sm:flex-none">
          <span className="hidden text-xs text-slate-500 sm:inline">Aktívna firma:</span>
          <select className="input min-w-0 py-1 font-medium sm:w-auto sm:max-w-[45vw]" value={companyId ?? ""}
            onChange={(e) => switchCompany(Number(e.target.value))} aria-label="Aktívna firma">
            {me?.companies.map((c) => <option key={c.id} value={c.id}>{c.name}{c.active ? "" : " (neaktívna)"}</option>)}
          </select>
          {company && !company.vat_payer && <span className="hidden text-xs text-slate-500 md:inline">neplatiteľ DPH</span>}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <span className="hidden text-sm text-slate-600 md:inline dark:text-slate-400">{me?.name}</span>
          <button className="btn-ghost btn-sm" onClick={() => setDark(!dark)} aria-label="Prepnúť tmavý režim">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <button className="btn-ghost btn-sm" onClick={logout} title="Odhlásiť"><LogOut className="h-4 w-4" /></button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-60 shrink-0 overflow-y-auto border-r border-slate-200 bg-white lg:block dark:border-slate-800 dark:bg-slate-900">{nav}</aside>
        {menu && (
          <div className="fixed inset-0 z-40 bg-slate-900/40 lg:hidden" onClick={() => setMenu(false)}>
            <aside className="h-full w-72 overflow-y-auto bg-white dark:bg-slate-900" onClick={(e) => e.stopPropagation()}>
              <div className="flex justify-end p-2"><button className="btn-ghost btn-sm" onClick={() => setMenu(false)} aria-label="Zavrieť"><X className="h-5 w-5" /></button></div>
              {nav}
            </aside>
          </div>
        )}
        <main className="min-w-0 flex-1 overflow-y-auto p-4 lg:p-6">
          {companyId ? <Outlet /> : (
            <div className="card p-6 text-sm">
              Zatiaľ nie je založená žiadna firma.{" "}
              {isAdmin ? <NavLink className="link" to="/ciselniky/firmy">Založte prvú firmu v Číselníky → Firmy.</NavLink> : "Kontaktujte administrátora."}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
