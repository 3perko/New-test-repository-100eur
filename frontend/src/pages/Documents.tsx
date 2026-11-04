import { useNavigate } from "react-router-dom";
import { FilePlus2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { DataTable } from "@/components/DataTable";
import { PageHeader, useToast } from "@/components/ui";
import { UploadBox } from "./Inbox";

const LABELS: Record<string, string> = { receipt: "Bločky", invoice_in: "Prijaté faktúry", invoice_out: "Vystavené faktúry" };

function NewDocButton({ docType }: { docType: string }) {
  const nav = useNavigate();
  const toast = useToast();
  return (
    <button className="btn-secondary btn-sm" onClick={async () => {
      try {
        const r = await api.post<{ id: number }>("/api/documents/manual", { doc_type: docType });
        nav(`/doklady/${r.id}`);
      } catch (e) {
        toast.error(e);
      }
    }}>
      <FilePlus2 className="h-3.5 w-3.5" /> Zadať ručne
    </button>
  );
}

export function DocumentsPage({ docType }: { docType: "receipt" | "invoice_in" | "invoice_out" }) {
  const qc = useQueryClient();
  return (
    <div className="space-y-4">
      <PageHeader title={LABELS[docType]} />
      <UploadBox kind={docType} compact onDone={() => qc.invalidateQueries({ queryKey: ["data", "documents"] })} />
      <DataTable entity="documents" viewKey={`documents:${docType}`} hideCreate
        fixedFilters={[{ field: "doc_type", op: "in", value: [docType] }]}
        toolbar={<NewDocButton docType={docType} />}
        initial={docType === "invoice_out" ? { columns: ["issue_date", "number", "partner_name", "total_net", "total_gross", "projects", "status", "payment_status"] }
          : docType === "invoice_in" ? { columns: ["issue_date", "number", "partner_name", "due_date", "total_gross", "projects", "status", "payment_status"] }
            : { columns: ["issue_date", "issue_time", "partner_name", "total_gross", "projects", "status", "extraction_source", "physical_original"] }} />
    </div>
  );
}

export function ReviewQueue() {
  const qc = useQueryClient();
  return (
    <div className="space-y-4">
      <PageHeader title="Na kontrolu" sub="Automaticky spracované doklady čakajú na potvrdenie a priradenie zákazky. Do prehľadov sa započítajú až potvrdené." />
      <UploadBox compact onDone={() => qc.invalidateQueries({ queryKey: ["data", "documents"] })} />
      <DataTable entity="documents" viewKey="documents:review" hideCreate
        fixedFilters={[{ field: "status", op: "in", value: ["review"] }]}
        toolbar={<NewDocButton docType="receipt" />}
        initial={{ columns: ["doc_type", "issue_date", "partner_name", "total_gross", "projects", "extraction_source", "has_warnings", "file_name"], sort: [{ key: "id", dir: "asc" }] }} />
    </div>
  );
}
