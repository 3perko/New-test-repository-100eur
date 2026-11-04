import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { PageHeader } from "@/components/ui";
import { useEntityMeta } from "@/components/DataTable";

export function EntityListPage({ entity, title, sub, extra }: { entity: string; title?: string; sub?: string; extra?: string }) {
  const meta = useEntityMeta(entity);
  const [tab, setTab] = useState(entity);
  const extraMeta = useEntityMeta(extra ?? entity);
  return (
    <div>
      <PageHeader title={title ?? meta.data?.label ?? ""} sub={sub} />
      {extra && (
        <div className="mb-3 flex gap-1 border-b border-slate-200 dark:border-slate-800">
          {[entity, extra].map((e) => (
            <button key={e} className={`px-3 py-1.5 text-sm ${tab === e ? "border-b-2 border-brand-600 font-medium" : "text-slate-500"}`}
              onClick={() => setTab(e)}>
              {e === entity ? meta.data?.label : extraMeta.data?.label}
            </button>
          ))}
        </div>
      )}
      <DataTable key={tab} entity={tab} />
    </div>
  );
}
