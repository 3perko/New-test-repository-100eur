"""Saved table views (per user, optionally shared by admin) + last state remembered on the server."""
import json

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_

from app.deps import Ctx, get_ctx
from app.models import TableView

router = APIRouter(prefix="/api/views", tags=["views"])


def _out(v: TableView, user_id: int) -> dict:
    return {"id": v.id, "entity": v.entity, "name": v.name, "config": json.loads(v.config), "is_default": v.is_default,
            "shared": v.shared, "own": v.user_id == user_id, "is_last": v.is_last}


@router.get("")
def list_views(entity: str, ctx: Ctx = Depends(get_ctx)):
    rows = (ctx.db.query(TableView).filter(TableView.entity == entity,
                                           or_(TableView.user_id == ctx.user.id, TableView.shared.is_(True)))
            .order_by(TableView.name).all())
    views = [_out(v, ctx.user.id) for v in rows if not v.is_last]
    last = next((_out(v, ctx.user.id) for v in rows if v.is_last and v.user_id == ctx.user.id), None)
    return {"views": views, "last": last}


@router.post("")
def create_view(body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    if not body.get("name") or not body.get("entity"):
        raise HTTPException(422, "Zadajte názov pohľadu.")
    shared = bool(body.get("shared")) and ctx.is_admin
    v = TableView(user_id=ctx.user.id, entity=body["entity"], name=body["name"][:200],
                  config=json.dumps(body.get("config") or {}), shared=shared)
    ctx.db.add(v)
    if body.get("is_default"):
        _set_default(ctx, v)
    ctx.db.commit()
    return _out(v, ctx.user.id)


def _set_default(ctx, v: TableView):
    for o in ctx.db.query(TableView).filter(TableView.user_id == ctx.user.id, TableView.entity == v.entity):
        o.is_default = False
    v.is_default = True


@router.patch("/{view_id}")
def update_view(view_id: int, body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    v = ctx.db.get(TableView, view_id)
    if not v or v.user_id != ctx.user.id:
        raise HTTPException(404, "Pohľad neexistuje.")
    if "name" in body:
        v.name = body["name"][:200]
    if "config" in body:
        v.config = json.dumps(body["config"])
    if "shared" in body:
        v.shared = bool(body["shared"]) and ctx.is_admin
    if body.get("is_default") is True:
        _set_default(ctx, v)
    elif body.get("is_default") is False:
        v.is_default = False
    ctx.db.commit()
    return _out(v, ctx.user.id)


@router.delete("/{view_id}")
def delete_view(view_id: int, ctx: Ctx = Depends(get_ctx)):
    v = ctx.db.get(TableView, view_id)
    if not v or v.user_id != ctx.user.id:
        raise HTTPException(404, "Pohľad neexistuje.")
    ctx.db.delete(v)
    ctx.db.commit()
    return {"ok": True}


@router.put("/last/{entity}")
def save_last(entity: str, body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    v = (ctx.db.query(TableView).filter(TableView.user_id == ctx.user.id, TableView.entity == entity,
                                        TableView.is_last.is_(True)).first())
    if v is None:
        v = TableView(user_id=ctx.user.id, entity=entity, name="__last__", is_last=True, config="{}")
        ctx.db.add(v)
    v.config = json.dumps(body.get("config") or {})
    ctx.db.commit()
    return {"ok": True}
