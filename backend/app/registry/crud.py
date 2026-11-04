"""Generic create / update / delete driven by the field registry (with audit log)."""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import inspect as sa_inspect

from app.registry.base import Entity, F, _parse_value, get_row
from app.services import audit


def _editable_fields(ent: Entity, role: str) -> dict[str, F]:
    out = {}
    for f in ent.visible_fields(role):
        if f.computed or not f.editable or role not in (f.edit_roles or f.roles):
            continue
        out[f.key] = f
    return out


def _coerce(f: F, v: Any) -> Any:
    if f.type == "multiref":
        return [int(x) for x in (v or [])]
    if f.type in ("text", "longtext", "select"):
        if v is None:
            return None
        v = str(v).strip()
        return v or None
    try:
        return _parse_value(f, v)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, f"Neplatná hodnota pre pole „{f.label}“.") from exc


def _check_access(ent: Entity, ctx, obj) -> None:
    if ent.base_filter is None and ent.company_scoped and getattr(obj, "company_id", None) != ctx.company_id:
        raise HTTPException(404, "Záznam neexistuje v aktívnej firme.")


def load(ent: Entity, ctx, obj_id: int):
    obj = ctx.db.get(ent.model, obj_id)
    if obj is None:
        raise HTTPException(404, "Záznam neexistuje.")
    _check_access(ent, ctx, obj)
    # row-level filter (e.g. worker sees only own records)
    get_row(ent, ctx, obj_id)
    return obj


def save(ent: Entity, ctx, data: dict, obj_id: int | None = None) -> dict:
    if ctx.role not in ent.write_roles:
        raise HTTPException(403, "Nemáte oprávnenie na zápis.")
    db = ctx.db
    editable = _editable_fields(ent, ctx.role)
    is_new = obj_id is None
    if is_new:
        if not ent.creatable:
            raise HTTPException(400, "Záznam sa nedá vytvoriť ručne.")
        obj = ent.model()
        if ent.company_scoped and hasattr(obj, "company_id"):
            obj.company_id = ctx.company_id
    else:
        obj = load(ent, ctx, obj_id)

    values: dict[str, Any] = {}
    multirefs: dict[str, list[int]] = {}
    for key, raw in data.items():
        f = editable.get(key)
        if f is None:
            continue
        if f.virtual:
            continue
        v = _coerce(f, raw)
        if f.type == "multiref":
            multirefs[key] = v
        else:
            values[f.attr or f.key] = v
    if is_new:
        for f in editable.values():
            if f.required and values.get(f.attr or f.key) is None and f.type != "multiref" and not f.virtual:
                raise HTTPException(422, f"Pole „{f.label}“ je povinné.")
    else:
        for f in editable.values():
            if f.required and (f.attr or f.key) in values and values[f.attr or f.key] is None:
                raise HTTPException(422, f"Pole „{f.label}“ je povinné.")

    table_cols = ent.model.__table__.columns
    for attr in list(values):
        col = table_cols.get(attr)
        if values[attr] is None and col is not None and not col.nullable:
            f = next((x for x in editable.values() if (x.attr or x.key) == attr), None)
            if f is not None and f.type == "bool":
                values[attr] = False
            elif is_new:
                values.pop(attr)  # column default applies
            else:
                raise HTTPException(422, f"Pole „{f.label if f else attr}“ nemôže byť prázdne.")

    changes = {}
    for attr, v in values.items():
        old = getattr(obj, attr, None)
        if old != v:
            changes[attr] = (old, v)
            setattr(obj, attr, v)
    if is_new:  # apply scalar column defaults now so hooks see them (e.g. billable=True)
        for col in ent.model.__table__.columns:
            attr = col.key
            if col.default is not None and getattr(col.default, "is_scalar", False) and getattr(obj, attr, None) is None:
                setattr(obj, attr, col.default.arg)
    ctx.changed = set(changes)  # available to hooks
    if ent.before_save:
        ent.before_save(ctx, obj, data, is_new)
    if not is_new:  # capture computed attribute changes for audit
        state = sa_inspect(obj)
        for attr in state.mapper.column_attrs.keys():
            hist = state.attrs[attr].history
            if hist.has_changes() and attr not in changes and attr != "updated_at":
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                if old != new:
                    changes[attr] = (old, new)
    if is_new:
        db.add(obj)
    db.flush()
    for key, ids in multirefs.items():
        handler = ent.multiref_save.get(key)
        if handler:
            before = handler(ctx, obj, ids)
            if before is not None and sorted(before) != sorted(ids):
                changes[key] = (before, ids)
    if ent.after_save:
        ent.after_save(ctx, obj, data, is_new)
    db.flush()
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company.id if ctx.company else None, entity=ent.name,
              entity_id=obj.id, action="create" if is_new else "update",
              changes=changes if not is_new else {k: (None, v) for k, (_, v) in changes.items()})
    db.commit()
    return get_row(ent, ctx, obj.id)


def delete(ent: Entity, ctx, obj_id: int) -> None:
    if ctx.role not in ent.write_roles:
        raise HTTPException(403, "Nemáte oprávnenie na zápis.")
    obj = load(ent, ctx, obj_id)
    if not ent.deletable:
        if ent.has_active:
            obj.active = False
            audit.log(ctx.db, user_id=ctx.user.id, company_id=ctx.company.id if ctx.company else None,
                      entity=ent.name, entity_id=obj.id, action="deactivate")
            ctx.db.commit()
            return
        raise HTTPException(400, "Záznam sa nedá vymazať.")
    if ent.before_delete:
        ent.before_delete(ctx, obj)
    audit.log(ctx.db, user_id=ctx.user.id, company_id=ctx.company.id if ctx.company else None, entity=ent.name,
              entity_id=obj.id, action="delete")
    ctx.db.delete(obj)
    ctx.db.commit()
