"""Generic data API driven by the field registry: meta, list, export, CRUD, bulk actions, options, history."""
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import String, cast, or_, select

from app.deps import Ctx, accessible_company_ids, get_ctx
from app.models import AuditLog, Company, Project, User, Vehicle, Worker, worker_company
from app.registry import crud
from app.registry.base import ListParams, fields_meta, get_entity, get_row, list_rows
from app.services import exports

router = APIRouter(prefix="/api", tags=["data"])

# entities whose options (for select boxes) any logged-in role may read
OPTION_PUBLIC = {"projects", "workers", "vehicles"}


def _check_read(ent, ctx: Ctx):
    if ctx.role not in ent.read_roles:
        raise HTTPException(403, "Nemáte prístup k tejto sekcii.")


@router.get("/meta/{entity}/fields")
def meta(entity: str, ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    return fields_meta(ent, ctx)


def _params(columns, sort, filter, q, page, page_size, group_by, include_inactive):
    return ListParams.from_query(columns, sort, filter, q, page, page_size, group_by, include_inactive)


@router.get("/data/{entity}")
def list_entity(entity: str, columns: str | None = None, sort: str | None = None, filter: str | None = None,
                q: str | None = None, page: int = 1, page_size: int = 50, group_by: str | None = None,
                include_inactive: bool = False, ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    return list_rows(ent, ctx, _params(columns, sort, filter, q, page, page_size, group_by, include_inactive))


@router.get("/data/{entity}/export")
def export_entity(entity: str, format: str = "xlsx", columns: str | None = None, sort: str | None = None,
                  filter: str | None = None, q: str | None = None, include_inactive: bool = False,
                  ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    p = _params(columns, sort, filter, q, 1, 100000, None, include_inactive)
    res = list_rows(ent, ctx, p, for_export=True)
    meta_fields = {f["key"]: f for f in fields_meta(ent, ctx)["fields"]}
    cols = [meta_fields[k] for k in res["columns"] if k in meta_fields]
    name = f"{ent.name}"
    if format == "csv":
        return Response(exports.table_csv(cols, res["rows"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    data = exports.table_xlsx(ent.label, cols, res["rows"], res["totals"])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/data/{entity}/{obj_id}")
def get_entity_row(entity: str, obj_id: int, ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    return get_row(ent, ctx, obj_id)


@router.post("/data/{entity}")
def create_entity(entity: str, data: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    return crud.save(ent, ctx, data)


@router.patch("/data/{entity}/{obj_id}")
def update_entity(entity: str, obj_id: int, data: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    return crud.save(ent, ctx, data, obj_id)


@router.delete("/data/{entity}/{obj_id}")
def delete_entity(entity: str, obj_id: int, ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    crud.delete(ent, ctx, obj_id)
    return {"ok": True}


@router.post("/data/{entity}/actions/{action}")
def run_action(entity: str, action: str, body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    act = next((a for a in ent.actions if a.key == action), None)
    if act is None or ctx.role not in act.roles:
        raise HTTPException(404, "Neznáma akcia.")
    ids = [int(i) for i in body.get("ids", [])]
    if not ids:
        raise HTTPException(422, "Neboli vybrané žiadne záznamy.")
    # only rows visible to the user
    visible = []
    for i in ids:
        try:
            get_row(ent, ctx, i)
            visible.append(i)
        except HTTPException:
            pass
    return act.handler(ctx, visible, body.get("payload") or {})


@router.post("/data/{entity}/bulk-update")
def bulk_update(entity: str, body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    """Set the same field values on several rows (e.g. assign project to many timesheets)."""
    ent = get_entity(entity)
    _check_read(ent, ctx)
    ids = [int(i) for i in body.get("ids", [])]
    values = body.get("values") or {}
    ok, errors = 0, []
    for i in ids:
        try:
            crud.save(ent, ctx, values, i)
            ok += 1
        except HTTPException as exc:
            ctx.db.rollback()
            errors.append(f"#{i}: {exc.detail}")
    return {"message": f"Upravené: {ok}" + (f", chyby: {'; '.join(errors[:5])}" if errors else ""), "ok": ok,
            "errors": errors}


def _title_col(ent):
    col = getattr(ent.model, ent.title_field, None)
    return col if col is not None else ent.model.id


@router.get("/options/{entity}")
def options(entity: str, q: str | None = None, include_inactive: bool = False, ids: str | None = None,
            limit: int = 50, all_companies: bool = False, ctx: Ctx = Depends(get_ctx)):
    """Value/label pairs for select boxes."""
    ent = get_entity(entity)
    if ctx.role not in ent.read_roles and entity not in OPTION_PUBLIC:
        raise HTTPException(403, "Nemáte prístup.")
    db = ctx.db
    model = ent.model
    allowed = accessible_company_ids(db, ctx.user)
    if entity == "vehicles":
        # vehicles of every accessible company – a car of company A may drive for a project of company B
        stmt = select(Vehicle.id, Vehicle.name, Vehicle.plate, Vehicle.company_id, Vehicle.active).where(
            Vehicle.company_id.in_(allowed))
    elif entity == "workers":
        stmt = select(Worker.id, Worker.name, Worker.active)
        if ctx.company:
            linked = select(worker_company.c.worker_id).where(worker_company.c.company_id == ctx.company.id)
            anylink = select(worker_company.c.worker_id)
            stmt = stmt.where(or_(Worker.id.in_(linked), Worker.id.notin_(anylink)))
    elif entity == "companies":
        stmt = select(Company.id, Company.name, Company.active).where(Company.id.in_(allowed))
    elif entity == "users":
        stmt = select(User.id, User.name, User.active)
    else:
        title = _title_col(ent)
        cols = [model.id, title.label("name")]
        if ent.has_active:
            cols.append(model.active)
        stmt = select(*cols)
        if ent.base_filter is not None:
            f = ent.base_filter(ctx)
            if f is not None:
                stmt = stmt.select_from(model)
                for target, onclause in ent.joins():
                    stmt = stmt.outerjoin(target, onclause)
                stmt = stmt.where(f)
        elif ent.company_scoped:
            stmt = stmt.where(model.company_id == ctx.company_id)
        if entity == "projects":
            stmt = stmt.add_columns(Project.is_overhead)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        stmt = stmt.where(model.id.in_(id_list))
    else:
        if ent.has_active and not include_inactive:
            stmt = stmt.where(model.active.is_(True))
        if q:
            name_col = Vehicle.name if entity == "vehicles" else _title_col(ent)
            conds = [cast(name_col, String).ilike(f"%{q}%")]
            if entity == "vehicles":
                conds.append(Vehicle.plate.ilike(f"%{q}%"))
            if hasattr(model, "aliases"):
                conds.append(model.aliases.ilike(f"%{q}%"))
            stmt = stmt.where(or_(*conds))
        stmt = stmt.limit(limit)
    out = []
    for r in ctx.db.execute(stmt):
        m = r._mapping
        if entity == "vehicles":
            lab = f"{m['name']} ({m['plate'] or '–'})"
        else:
            lab = str(m.get("name") if m.get("name") is not None else m["id"])
        item = {"value": m["id"], "label": lab}
        if "active" in m and m["active"] is False:
            item["inactive"] = True
        if m.get("is_overhead"):
            item["overhead"] = True
        out.append(item)
    out.sort(key=lambda x: (not x.get("overhead", False) if entity == "projects" else 0, x["label"].lower()))
    return out


@router.get("/history/{entity}/{obj_id}")
def history(entity: str, obj_id: int, ctx: Ctx = Depends(get_ctx)):
    ent = get_entity(entity)
    _check_read(ent, ctx)
    get_row(ent, ctx, obj_id)  # access check
    users = {u.id: u.name for u in ctx.db.query(User)}
    rows = (ctx.db.query(AuditLog).filter(AuditLog.entity == entity, AuditLog.entity_id == obj_id)
            .order_by(AuditLog.ts.desc()).limit(200).all())
    fields = {f.key: f.label for f in ent.fields}
    out = []
    for r in rows:
        changes = json.loads(r.changes) if r.changes else {}
        if ctx.role != "admin":
            changes = {k: v for k, v in changes.items() if k not in ("billing_rate", "billable_amount")}
        out.append({"ts": r.ts.isoformat(), "user": users.get(r.user_id), "action": r.action, "note": r.note,
                    "changes": [{"field": fields.get(k, k), "old": v[0], "new": v[1]} for k, v in changes.items()]})
    return out
