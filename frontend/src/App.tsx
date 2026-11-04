import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { EntityListPage } from "@/pages/EntityListPage";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import { ProjectCosts, ProjectDetail } from "@/pages/ProjectCosts";
import Profitability from "@/pages/Profitability";
import { ReviewQueue, DocumentsPage } from "@/pages/Documents";
import DocumentDetail from "@/pages/DocumentDetail";
import QuickCheck from "@/pages/QuickCheck";
import Inbox from "@/pages/Inbox";
import { HoursPage, TripsPage } from "@/pages/Work";
import VehicleCheck from "@/pages/VehicleCheck";
import Vat from "@/pages/Vat";
import { BankPage, BankTransactionDetail } from "@/pages/Bank";
import MonthlyCheck from "@/pages/MonthlyCheck";
import { BillingList, BillingDetail } from "@/pages/Billing";
import WorkerStatement from "@/pages/WorkerStatement";
import Exports from "@/pages/Exports";
import { Integrations, Parameters } from "@/pages/Settings";

function Protected() {
  const { me, loading, isAdmin } = useAuth();
  if (loading) return <div className="flex h-full items-center justify-center"><Spinner /></div>;
  if (!me) return <Navigate to="/prihlasenie" replace />;
  return (
    <Routes>
      <Route element={<Layout />}>
        {isAdmin ? (
          <>
            <Route index element={<Dashboard />} />
            <Route path="zakazky-naklady" element={<ProjectCosts />} />
            <Route path="zakazky-naklady/:id" element={<ProjectDetail />} />
            <Route path="ziskovost" element={<Profitability />} />
            <Route path="doklady/na-kontrolu" element={<ReviewQueue />} />
            <Route path="doklady/blocky" element={<DocumentsPage docType="receipt" />} />
            <Route path="doklady/prijate" element={<DocumentsPage docType="invoice_in" />} />
            <Route path="doklady/vystavene" element={<DocumentsPage docType="invoice_out" />} />
            <Route path="doklady/rychla-kontrola" element={<QuickCheck />} />
            <Route path="doklady/inbox" element={<Inbox />} />
            <Route path="doklady/polozky" element={<EntityListPage entity="allocations" title="Priradenia nákladov a výnosov"
              sub="Každý riadok je časť dokladu priradená k zákazke (náklad alebo výnos)." extra="document_lines" />} />
            <Route path="doklady/:id" element={<DocumentDetail />} />
            <Route path="vozovy-park/vozidla" element={<EntityListPage entity="vehicles" title="Vozidlá" />} />
            <Route path="vozovy-park/sadzby" element={<EntityListPage entity="vehicle_rates" title="Sadzby vozidiel €/km"
              sub="Sadzba s platnosťou od–do. Jazda si sadzbu zafixuje k dátumu jazdy." />} />
            <Route path="vozovy-park/poistenie" element={<EntityListPage entity="vehicle_insurance" title="PZP a poistenie"
              sub="Nová zmluva = nový záznam, história ostáva." />} />
            <Route path="vozovy-park/znamky" element={<EntityListPage entity="vehicle_vignettes" title="Diaľničné známky" />} />
            <Route path="vozovy-park/servis" element={<EntityListPage entity="vehicle_services" title="Servis vozidiel"
              sub="Náklady na servis, PZP a známky idú do Réžie (sú pokryté sadzbou €/km)." />} />
            <Route path="vozovy-park/overenie" element={<VehicleCheck />} />
            <Route path="financie/dph" element={<Vat />} />
            <Route path="financie/banka" element={<BankPage />} />
            <Route path="financie/banka/pohyb/:id" element={<BankTransactionDetail />} />
            <Route path="financie/mesacna-kontrola" element={<MonthlyCheck />} />
            <Route path="financie/pravidla" element={<EntityListPage entity="transaction_rules" title="Pravidlá bankových pohybov"
              sub="Pohyby, ktoré nepotrebujú doklad (poplatky, mzdy, odvody, prevody medzi vlastnými účtami)." />} />
            <Route path="vystupy/fakturacia" element={<BillingList />} />
            <Route path="vystupy/fakturacia/:id" element={<BillingDetail />} />
            <Route path="vystupy/exporty" element={<Exports />} />
            <Route path="ciselniky/firmy" element={<EntityListPage entity="companies" title="Firmy"
              sub="Každá firma má vlastné doklady, zákazky, DPH a Réžiu. Pri založení firmy sa automaticky vytvorí zákazka Réžia." />} />
            <Route path="ciselniky/ucty" element={<EntityListPage entity="bank_accounts" title="Bankové účty aktívnej firmy" />} />
            <Route path="ciselniky/rady" element={<EntityListPage entity="invoice_series" title="Číselné rady vystavených faktúr" />} />
            <Route path="ciselniky/odberatelia" element={<EntityListPage entity="customers" title="Odberatelia" />} />
            <Route path="ciselniky/zakazky" element={<EntityListPage entity="projects" title="Zákazky" />} />
            <Route path="ciselniky/pracovnici" element={<EntityListPage entity="workers" title="Pracovníci"
              sub="Pracovník môže pracovať pre viac firiem; jeho hodiny sa evidujú vo firme zákazky." />} />
            <Route path="ciselniky/sadzby" element={<EntityListPage entity="worker_rates" title="Sadzby pracovníkov"
              sub="Poradie: pracovník + zákazka → pracovník + firma → default pracovníka (platné k dátumu). Sadzby sa k hodinám fixujú pri zadaní." />} />
            <Route path="ciselniky/opakujuce" element={<EntityListPage entity="recurring_rules" title="Opakujúce sa (povinné) faktúry"
              sub="Idú do Réžie; ak v mesiaci chýbajú, mesačná kontrola upozorní." />} />
            <Route path="nastavenia/pouzivatelia" element={<EntityListPage entity="users" title="Používatelia a roly" />} />
            <Route path="nastavenia/parametre" element={<Parameters />} />
            <Route path="nastavenia/integracie" element={<Integrations />} />
            <Route path="nastavenia/audit" element={<EntityListPage entity="audit_log" title="Audit log" />} />
          </>
        ) : (
          <Route index element={<Navigate to="/praca/hodiny" replace />} />
        )}
        <Route path="praca/hodiny" element={<HoursPage />} />
        <Route path="praca/jazdy" element={<TripsPage />} />
        <Route path="vystupy/pracovnik" element={<WorkerStatement />} />
        <Route path="*" element={<div className="text-sm text-slate-500">Stránka neexistuje.</div>} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/prihlasenie" element={<Login />} />
      <Route path="/*" element={<Protected />} />
    </Routes>
  );
}
