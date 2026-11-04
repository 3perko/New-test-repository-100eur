"""Field registry: metadata for every entity + generic server-side list engine.

Adding a field to an entity definition is enough for it to appear in the UI
(column chooser, filters, sorting, export, detail form).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Boolean, String, and_, cast, func, literal, not_, or_, select
from sqlalchemy.orm import Session

ALL_ROLES = ("admin", "worker")
ADMIN = ("admin",)
NUMERIC_TYPES = ("number", "money", "hours")


@dataclass
class F:
    key: str
    label: str
    type: str = "text"  # text | longtext | number | money | hours | date | time | datetime | select | bool | ref | multiref
    expr: Callable[[], Any] | None = None  # SQL expression; default = model column `attr or key`
    attr: str | None = None  # model attribute for editing
    editable: bool = True
    required: bool = False
    sortable: bool = True
    filterable: bool = True
    computed: bool = False
    roles: tuple[str, ...] = ALL_ROLES
    edit_roles: tuple[str, ...] | None = None
    options: list[tuple[str, str]] | None = None
    ref: str | None = None  # entity name for ref/multiref
    label_expr: Callable[[], Any] | None = None  # display label for ref / multiref
    default_visible: bool = True
    in_form: bool = True
    width: int | None = None
    help: str | None = None
    aggregate: bool = True  # sum in footer for numeric types
    ref_filter: dict | None = None  # extra params for option lookup
    virtual: bool = False  # not stored on the model, only passed to hooks (e.g. password)

    def meta(self, role: str) -> dict:
        return {
            "key": self.key, "label": self.label, "type": self.type, "sortable": self.sortable,
            "filterable": self.filterable, "computed": self.computed,
            "editable": self.editable and not self.computed and role in (self.edit_roles or self.roles),
            "required": self.required, "options": [{"value": v, "label": lab} for v, lab in (self.options or [])],
            "ref": self.ref, "default_visible": self.default_visible, "in_form": self.in_form,
            "width": self.width, "help": self.help, "ref_filter": self.ref_filter,
            "aggregate": self.aggregate and self.type in NUMERIC_TYPES,
        }


@dataclass
class Action:
    key: str
    label: str
    handler: Callable  # (ctx, ids, payload) -> dict
    roles: tuple[str, ...] = ADMIN
    confirm: str | None = None
    payload: str | None = None  # name of payload widget: "project" | None


@dataclass
class Entity:
    name: str
    label: str
    model: Any
    fields: list[F]
    joins: Callable[[], list] = lambda: []  # [(target, onclause)] outer joins
    company_scoped: bool = True
    has_active: bool = False
    read_roles: tuple[str, ...] = ADMIN
    write_roles: tuple[str, ...] = ADMIN
    row_filter: Callable[[Any], Any] | None = None  # (ctx) -> clause
    base_filter: Callable[[Any], Any] | None = None  # (ctx) -> clause, replaces company scoping
    default_sort: str = "id:desc"
    title_field: str = "name"
    deletable: bool = True  # hard delete allowed (otherwise only deactivation)
    before_save: Callable | None = None  # (ctx, obj, data, is_new) -> None
    after_save: Callable | None = None  # (ctx, obj, data, is_new) -> None
    before_delete: Callable | None = None  # (ctx, obj) -> None
    multiref_save: dict[str, Callable] = field(default_factory=dict)  # key -> (ctx, obj, ids)
    actions: list[Action] = field(default_factory=list)
    detail_url: str | None = None  # custom frontend detail page (e.g. documents)
    creatable: bool = True

    def fmap(self) -> dict[str, F]:
        return {f.key: f for f in self.fields}

    def visible_fields(self, role: str) -> list[F]:
        return [f for f in self.fields if role in f.roles]

    def col(self, f: F):
        if f.expr is not None:
            return f.expr()
        return getattr(self.model, f.attr or f.key)


REGISTRY: dict[str, Entity] = {}


def register(e: Entity) -> Entity:
    REGISTRY[e.name] = e
    return e


def get_entity(name: str) -> Entity:
    e = REGISTRY.get(name)
    if not e:
        raise HTTPException(404, f"Neznáma entita {name}")
    return e


# ----------------------------------------------------------------------------- query building

def _parse_value(f: F, v: Any) -> Any:
    if v is None or v == "":
        return None
    if f.type in NUMERIC_TYPES:
        return Decimal(str(v).replace(",", ".").replace(" ", ""))
    if f.type == "date":
        return date.fromisoformat(str(v)[:10])
    if f.type == "datetime":
        return datetime.fromisoformat(str(v))
    if f.type == "time":
        return time.fromisoformat(str(v))
    if f.type == "bool":
        return v in (True, "true", "1", 1, "yes")
    if f.type in ("ref",):
        return int(v)
    return v


def _filter_clause(ent: Entity, f: F, flt: dict):
    op = flt.get("op", "eq")
    value = flt.get("value")
    col = ent.col(f)
    if f.type in ("ref", "multiref") and op == "contains":
        col = f.label_expr() if f.label_expr else col
    if op == "isnull":
        return col.is_(None)
    if op == "notnull":
        return col.is_not(None)
    if f.type == "multiref":
        if op == "contains":
            return cast(col, String).ilike(f"%{value}%")
        raise HTTPException(400, f"Nepodporovaný filter pre {f.key}")
    if op == "contains":
        return cast(col, String).ilike(f"%{value}%")
    if op == "not_contains":
        return or_(col.is_(None), not_(cast(col, String).ilike(f"%{value}%")))
    if op == "starts":
        return cast(col, String).ilike(f"{value}%")
    if op == "in":
        vals = value if isinstance(value, list) else [value]
        parsed = [_parse_value(f, v) for v in vals]
        clauses = [col.in_([p for p in parsed if p is not None])]
        if any(p is None for p in parsed):
            clauses.append(col.is_(None))
        return or_(*clauses)
    if op == "between":
        lo, hi = (value or [None, None]) + [None] * (2 - len(value or []))
        conds = []
        lo, hi = _parse_value(f, lo), _parse_value(f, hi)
        if lo is not None:
            conds.append(col >= lo)
        if hi is not None:
            conds.append(col <= hi)
        return and_(*conds) if conds else None
    v = _parse_value(f, value)
    if op == "eq":
        if f.type == "text":
            return func.lower(cast(col, String)) == str(value).lower()
        return col.is_(None) if v is None else col == v
    if op == "neq":
        return or_(col.is_(None), col != v)
    if op == "gte":
        return col >= v
    if op == "lte":
        return col <= v
    if op == "gt":
        return col > v
    if op == "lt":
        return col < v
    raise HTTPException(400, f"Neznámy operátor {op}")


@dataclass
class ListParams:
    columns: list[str] | None = None
    sort: str | None = None
    filters: list[dict] = field(default_factory=list)
    q: str | None = None
    page: int = 1
    page_size: int = 50
    group_by: str | None = None
    include_inactive: bool = False

    @classmethod
    def from_query(cls, columns: str | None, sort: str | None, filter: str | None, q: str | None, page: int,
                   page_size: int, group_by: str | None, include_inactive: bool) -> ListParams:
        try:
            flt = json.loads(filter) if filter else []
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "Neplatný filter") from exc
        return cls(columns=[c for c in columns.split(",") if c] if columns else None, sort=sort, filters=flt, q=q,
                   page=max(1, page), page_size=min(max(1, page_size), 5000), group_by=group_by or None,
                   include_inactive=include_inactive)


def base_where(ent: Entity, ctx, include_inactive: bool) -> list:
    conds = []
    if ent.base_filter is not None:
        c = ent.base_filter(ctx)
        if c is not None:
            conds.append(c)
    elif ent.company_scoped:
        conds.append(ent.model.company_id == ctx.company_id)
    if ent.row_filter is not None:
        c = ent.row_filter(ctx)
        if c is not None:
            conds.append(c)
    if ent.has_active and not include_inactive:
        conds.append(ent.model.active.is_(True))
    return conds


def build_where(ent: Entity, ctx, p: ListParams) -> list:
    role = ctx.role
    fm = {f.key: f for f in ent.visible_fields(role)}
    conds = base_where(ent, ctx, p.include_inactive)
    for flt in p.filters:
        f = fm.get(flt.get("field", ""))
        if f is None or not f.filterable:
            continue
        c = _filter_clause(ent, f, flt)
        if c is not None:
            conds.append(c)
    if p.q:
        text_cols = []
        for f in fm.values():
            if f.type in ("text", "longtext", "select"):
                text_cols.append(cast(ent.col(f), String))
            elif f.type in ("ref", "multiref") and f.label_expr:
                text_cols.append(cast(f.label_expr(), String))
        if text_cols:
            conds.append(or_(*[c.ilike(f"%{p.q}%") for c in text_cols]))
    return conds


def _select_from(ent: Entity, cols: list):
    stmt = select(*cols).select_from(ent.model)
    for target, onclause in ent.joins():
        stmt = stmt.outerjoin(target, onclause)
    return stmt


def _row_cols(ent: Entity, fields: list[F]) -> list:
    cols = [ent.model.id.label("id")]
    for f in fields:
        cols.append(ent.col(f).label(f.key))
        if f.type in ("ref", "multiref") and f.label_expr is not None:
            cols.append(f.label_expr().label(f.key + "__label"))
    if ent.has_active and "active" not in {f.key for f in fields}:
        cols.append(ent.model.active.label("active"))
    return cols


def _order_by(ent: Entity, fm: dict[str, F], sort: str | None):
    order = []
    for part in (sort or ent.default_sort).split(","):
        if not part:
            continue
        key, _, direction = part.partition(":")
        if key == "id":
            col = ent.model.id
        else:
            f = fm.get(key)
            if f is None or not f.sortable:
                continue
            col = f.label_expr() if f.type in ("ref", "multiref") and f.label_expr else ent.col(f)
        order.append(col.desc().nullslast() if direction == "desc" else col.asc().nullsfirst())
    order.append(ent.model.id.desc())
    return order


def serialize(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M")
    return v


def list_rows(ent: Entity, ctx, p: ListParams, *, for_export: bool = False) -> dict:
    db: Session = ctx.db
    role = ctx.role
    visible = ent.visible_fields(role)
    fm = {f.key: f for f in visible}
    if p.columns:
        fields = [fm[c] for c in p.columns if c in fm]
    else:
        fields = [f for f in visible if f.default_visible]
    if p.group_by and p.group_by in fm and fm[p.group_by] not in fields:
        fields = [fm[p.group_by]] + fields
    conds = build_where(ent, ctx, p)

    count_stmt = _select_from(ent, [func.count(func.distinct(ent.model.id))]).where(*conds)
    total = db.execute(count_stmt).scalar_one()

    order = _order_by(ent, fm, p.sort)
    if p.group_by and p.group_by in fm:
        g = fm[p.group_by]
        gcol = g.label_expr() if g.type in ("ref", "multiref") and g.label_expr else ent.col(g)
        order = [gcol.asc().nullsfirst()] + order
    stmt = _select_from(ent, _row_cols(ent, fields)).where(*conds).order_by(*order)
    if not for_export:
        stmt = stmt.limit(p.page_size).offset((p.page - 1) * p.page_size)
    rows = [{k: serialize(v) for k, v in r._mapping.items()} for r in db.execute(stmt)]

    numeric = [f for f in fields if f.type in NUMERIC_TYPES and f.aggregate]
    totals = {}
    if numeric:
        sub = _select_from(ent, [ent.model.id.label("_id")] + [ent.col(f).label(f.key) for f in numeric]).where(*conds).subquery()
        tstmt = select(*[func.sum(sub.c[f.key]).label(f.key) for f in numeric])
        totals = {k: serialize(v) for k, v in db.execute(tstmt).one()._mapping.items()}

    groups = None
    if p.group_by and p.group_by in fm:
        g = fm[p.group_by]
        gval = ent.col(g)
        glabel = g.label_expr() if g.type in ("ref", "multiref") and g.label_expr else gval
        sub = _select_from(ent, [gval.label("_g"), glabel.label("_gl")] +
                           [ent.col(f).label(f.key) for f in numeric]).where(*conds).subquery()
        gstmt = (select(sub.c._g, sub.c._gl, func.count().label("_count"), *[func.sum(sub.c[f.key]).label(f.key) for f in numeric])
                 .group_by(sub.c._g, sub.c._gl).order_by(sub.c._gl.asc().nullsfirst()))
        groups = [{"value": serialize(r._g), "label": serialize(r._gl), "count": r._count,
                   "totals": {f.key: serialize(getattr(r, f.key)) for f in numeric}} for r in db.execute(gstmt)]

    return {"rows": rows, "total": total, "totals": totals, "groups": groups, "columns": [f.key for f in fields],
            "page": p.page, "page_size": p.page_size}


def fields_meta(ent: Entity, ctx) -> dict:
    role = ctx.role
    return {
        "entity": ent.name, "label": ent.label, "has_active": ent.has_active,
        "fields": [f.meta(role) for f in ent.visible_fields(role)],
        "can_write": role in ent.write_roles, "can_create": role in ent.write_roles and ent.creatable,
        "deletable": ent.deletable and role in ent.write_roles,
        "default_sort": ent.default_sort, "detail_url": ent.detail_url, "title_field": ent.title_field,
        "actions": [{"key": a.key, "label": a.label, "confirm": a.confirm, "payload": a.payload}
                    for a in ent.actions if role in a.roles],
    }


def get_row(ent: Entity, ctx, obj_id: int) -> dict:
    visible = ent.visible_fields(ctx.role)
    conds = base_where(ent, ctx, True) + [ent.model.id == obj_id]
    stmt = _select_from(ent, _row_cols(ent, visible)).where(*conds)
    r = ctx.db.execute(stmt).first()
    if r is None:
        raise HTTPException(404, "Záznam neexistuje alebo k nemu nemáte prístup.")
    row = {k: serialize(v) for k, v in r._mapping.items()}
    # multiref raw ids
    for f in visible:
        if f.type == "multiref":
            obj = ctx.db.get(ent.model, obj_id)
            rel = getattr(obj, f.attr or f.key, None) or []
            row[f.key] = [x.id for x in rel]
    return row


def string_agg_names(name_col, link_table, link_fk, target_model, target_fk, owner_id_col):
    """Correlated subquery: comma separated names via an association table."""
    return (select(func.string_agg(name_col, literal(", ")))
            .select_from(link_table.join(target_model, target_fk == target_model.id))
            .where(link_fk == owner_id_col).correlate_except(link_table, target_model).scalar_subquery())


TRUE = literal(True, Boolean)
_ = timedelta  # re-export convenience
