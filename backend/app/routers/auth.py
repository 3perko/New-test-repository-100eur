from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_db
from app.deps import Ctx, accessible_company_ids, get_ctx, get_current_user
from app.models import Company, User
from app.security import COOKIE_NAME, create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(response: Response, body: dict = Body(...), db: Session = Depends(get_db)):
    email = (body.get("email") or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.active or not verify_password(body.get("password") or "", user.password_hash):
        raise HTTPException(401, "Nesprávny e-mail alebo heslo.")
    cfg = get_config()
    response.set_cookie(COOKIE_NAME, create_token(user.id), httponly=True, samesite="lax", secure=cfg.cookie_secure,
                        max_age=cfg.token_hours * 3600, path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx)):
    u = ctx.user
    companies = [{"id": c.id, "name": c.name, "vat_payer": c.vat_payer, "active": c.active}
                 for c in ctx.db.query(Company).filter(Company.id.in_(accessible_company_ids(ctx.db, u)))
                 .order_by(Company.name)]
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "worker_id": u.worker_id,
            "companies": companies, "company_id": ctx.company.id if ctx.company else None}


@router.post("/company")
def set_company(body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    cid = int(body.get("company_id"))
    if cid not in accessible_company_ids(ctx.db, ctx.user):
        raise HTTPException(403, "K tejto firme nemáte prístup.")
    ctx.user.last_company_id = cid
    ctx.db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(body: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.get("old_password") or "", user.password_hash):
        raise HTTPException(422, "Pôvodné heslo nie je správne.")
    new = body.get("new_password") or ""
    if len(new) < 8:
        raise HTTPException(422, "Nové heslo musí mať aspoň 8 znakov.")
    u = db.merge(user)
    u.password_hash = hash_password(new)
    db.commit()
    return {"ok": True}
