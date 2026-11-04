export type FieldType =
  | "text" | "longtext" | "number" | "money" | "hours" | "date" | "time" | "datetime" | "select" | "bool" | "ref" | "multiref";

export interface FieldMeta {
  key: string;
  label: string;
  type: FieldType;
  sortable: boolean;
  filterable: boolean;
  computed: boolean;
  editable: boolean;
  required: boolean;
  options: { value: string; label: string }[];
  ref: string | null;
  default_visible: boolean;
  in_form: boolean;
  width: number | null;
  help: string | null;
  aggregate: boolean;
}

export interface EntityMeta {
  entity: string;
  label: string;
  has_active: boolean;
  fields: FieldMeta[];
  can_write: boolean;
  can_create: boolean;
  deletable: boolean;
  default_sort: string;
  detail_url: string | null;
  title_field: string;
  actions: { key: string; label: string; confirm: string | null; payload: string | null }[];
}

export type Row = Record<string, unknown> & { id: number };

export interface ListResult {
  rows: Row[];
  total: number;
  totals: Record<string, number | null>;
  groups: { value: unknown; label: unknown; count: number; totals: Record<string, number | null> }[] | null;
  columns: string[];
  page: number;
  page_size: number;
}

export interface Filter {
  field: string;
  op: string;
  value?: unknown;
}

export interface SortSpec {
  key: string;
  dir: "asc" | "desc";
}

export interface ViewConfig {
  columns?: string[];
  widths?: Record<string, number>;
  sort?: SortSpec[];
  filters?: Filter[];
  q?: string;
  groupBy?: string | null;
  pageSize?: number;
  includeInactive?: boolean;
}

export interface SavedView {
  id: number;
  entity: string;
  name: string;
  config: ViewConfig;
  is_default: boolean;
  shared: boolean;
  own: boolean;
}

export interface Me {
  id: number;
  name: string;
  email: string;
  role: "admin" | "worker";
  worker_id: number | null;
  companies: { id: number; name: string; vat_payer: boolean; active: boolean }[];
  company_id: number | null;
}

export interface Option {
  value: number;
  label: string;
  inactive?: boolean;
  overhead?: boolean;
}
