import { Check } from "lucide-react";
import { fmtDate, fmtDateTime, fmtMoney, fmtNum, fmtTime } from "@/lib/format";
import type { FieldMeta, Row } from "@/lib/types";
import { Badge } from "./ui";

const STATUS_COLORS: Record<string, "gray" | "green" | "red" | "amber" | "blue"> = {
  review: "amber", confirmed: "green", unpaid: "red", partial: "amber", paid: "green",
  unmatched: "red", suggested: "amber", matched: "green", no_document: "gray",
  draft: "amber", closed: "green", new: "blue", processed: "green", duplicate: "gray", error: "red", skipped: "gray",
  valid: "green", invalid: "red", unknown: "gray", planned: "gray", in_progress: "blue", finished: "green",
};

export function cellText(field: FieldMeta, row: Row): string {
  const v = row[field.key];
  switch (field.type) {
    case "ref":
    case "multiref":
      return String(row[`${field.key}__label`] ?? "");
    case "select":
      return field.options.find((o) => o.value === v)?.label ?? (v == null ? "" : String(v));
    case "bool":
      return v ? "áno" : v === false ? "nie" : "";
    case "money":
      return fmtMoney(v);
    case "number":
    case "hours":
      return fmtNum(v);
    case "date":
      return fmtDate(v);
    case "datetime":
      return fmtDateTime(v);
    case "time":
      return fmtTime(v);
    default:
      return v == null ? "" : String(v);
  }
}

export function Cell({ field, row }: { field: FieldMeta; row: Row }) {
  const v = row[field.key];
  if (field.type === "bool") return v ? <Check className="h-4 w-4 text-emerald-600" aria-label="áno" /> : <span className="text-slate-300">–</span>;
  if (field.type === "select" && typeof v === "string" && (field.key === "status" || field.key.endsWith("_status") || field.key === "result"))
    return <Badge color={STATUS_COLORS[v] ?? "gray"}>{cellText(field, row)}</Badge>;
  const text = cellText(field, row);
  if (field.type === "money" || field.type === "number" || field.type === "hours") {
    const neg = typeof v === "number" && v < 0;
    return <span className={`block num ${neg ? "text-red-600" : ""}`}>{text}</span>;
  }
  if (field.type === "longtext") return <span className="line-clamp-2" title={text}>{text}</span>;
  return <span className="block truncate" title={text}>{text}</span>;
}

export function isNumeric(f: FieldMeta) {
  return f.type === "money" || f.type === "number" || f.type === "hours";
}

export function defaultWidth(f: FieldMeta): number {
  if (f.width) return f.width;
  switch (f.type) {
    case "bool": return 80;
    case "date": return 100;
    case "time": return 70;
    case "datetime": return 140;
    case "money": return 120;
    case "number": case "hours": return 95;
    case "longtext": return 260;
    case "select": return 130;
    default: return 170;
  }
}
