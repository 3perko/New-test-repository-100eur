"""Request context: current user and active company."""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, User
from app.security import COOKIE_NAME, decode_token


@dataclass
class Ctx:
    db: Session
    user: User
    company: Company | None

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin"

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def company_id(self) -> int:
        if self.company is None:
            raise HTTPException(400, "Nie je zvolená aktívna firma.")
        return self.company.id


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    user_id = decode_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if not user or not user.active:
        raise HTTPException(401, "Neprihlásený používateľ.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "app":
        # Simple CSRF protection: cross-site forms cannot set custom headers.
        raise HTTPException(403, "Chýba hlavička X-Requested-With.")
    return user


def accessible_company_ids(db: Session, user: User) -> list[int]:
    if user.role == "admin" and not user.companies:
        return [c.id for c in db.query(Company).all()]
    return [c.id for c in user.companies]


def get_ctx(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_company_id: str | None = Header(default=None),
) -> Ctx:
    company = None
    allowed = accessible_company_ids(db, user)
    cid = None
    if x_company_id and x_company_id.isdigit():
        cid = int(x_company_id)
    elif user.last_company_id:
        cid = user.last_company_id
    if cid is not None:
        if cid not in allowed:
            raise HTTPException(403, "K tejto firme nemáte prístup.")
        company = db.get(Company, cid)
    if company is None and allowed:
        company = db.get(Company, allowed[0])
    return Ctx(db=db, user=user, company=company)


def require_admin(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    if not ctx.is_admin:
        raise HTTPException(403, "Táto akcia je dostupná len pre administrátora.")
    return ctx
