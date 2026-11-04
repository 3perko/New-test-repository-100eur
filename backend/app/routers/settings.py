from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_db
from app.deps import Ctx, require_admin
from app.services import extraction, google, settings
from app.services.settings import PARAMS

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings(ctx: Ctx = Depends(require_admin)):
    out = []
    for p in PARAMS:
        out.append({"key": p.key, "label": p.label, "type": p.type, "help": p.help, "company_level": p.company_level,
                    "default": p.default, "global_value": settings.get_value(ctx.db, p.key),
                    "company_value": settings.get_value(ctx.db, p.key, ctx.company_id) if p.company_level else None,
                    "effective": settings.get_param(ctx.db, p.key, ctx.company_id)})
    return out


@router.put("/settings")
def put_settings(body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    """body: {key: {scope: 'global'|'company', value: any|null}}"""
    from app.services import audit
    valid = {p.key: p for p in PARAMS}
    for key, spec in body.items():
        p = valid.get(key)
        if p is None:
            raise HTTPException(422, f"Neznámy parameter {key}")
        scope = spec.get("scope", "global")
        value = spec.get("value")
        if p.type == "number" and value not in (None, ""):
            try:
                value = float(str(value).replace(",", "."))
            except ValueError as exc:
                raise HTTPException(422, f"{p.label}: zadajte číslo") from exc
        if p.type == "time" and value:
            import re
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(value)):
                raise HTTPException(422, f"{p.label}: čas vo formáte HH:MM (24 h)")
        if value == "":
            value = None
        cid = ctx.company_id if scope == "company" and p.company_level else None
        old = settings.get_value(ctx.db, key, cid)
        settings.set_value(ctx.db, key, value, cid)
        audit.log(ctx.db, user_id=ctx.user.id, company_id=cid, entity="settings", entity_id=None, action="update",
                  changes={key: (old, value)})
    ctx.db.commit()
    return get_settings(ctx)


@router.get("/integrations")
def integrations(ctx: Ctx = Depends(require_admin)):
    cfg = get_config()
    from app.services.vehicle_check import adapters
    return {
        "google": google.status(ctx.db),
        "claude": {"configured": extraction.is_available(), "model": cfg.claude_model},
        "ekasa": {"enabled": cfg.ekasa_enabled, "url": cfg.ekasa_url},
        "inbox_last_run": settings.get_value(ctx.db, "inbox.last_run", ctx.company_id),
        "company": {"name": ctx.company.name, "drive_inbox_folder_id": ctx.company.drive_inbox_folder_id,
                    "drive_processed_folder_id": ctx.company.drive_processed_folder_id,
                    "drive_bank_inbox_folder_id": ctx.company.drive_bank_inbox_folder_id,
                    "email_tag_invoices": ctx.company.email_tag_invoices,
                    "email_tag_bank": ctx.company.email_tag_bank},
        "vehicle_checks": [{"service": a.service, "label": a.label, "url": a.url, "has_api": a.has_api}
                           for a in adapters(ctx.db)],
    }


@router.get("/integrations/google/auth-url")
def google_auth_url(ctx: Ctx = Depends(require_admin)):
    try:
        return {"url": google.auth_url(ctx.db)}
    except google.GoogleError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/integrations/google/callback", response_class=HTMLResponse)
def google_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    if error:
        msg = f"Prihlásenie zrušené: {error}"
    else:
        try:
            email = google.handle_callback(db, code, state)
            msg = f"Google účet {email} bol pripojený."
        except google.GoogleError as exc:
            msg = f"Chyba: {exc}"
    import html
    return HTMLResponse(f"<html><body style='font-family:sans-serif;padding:2rem'><p>{html.escape(msg)}</p>"
                        f"<p><a href='/nastavenia/integracie'>Späť do aplikácie</a></p></body></html>")


@router.post("/integrations/google/disconnect")
def google_disconnect(ctx: Ctx = Depends(require_admin)):
    google.disconnect(ctx.db)
    return {"ok": True}


@router.post("/integrations/ekasa/test")
def ekasa_test(body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    from app.services import ekasa
    try:
        r = ekasa.fetch_receipt(body.get("receipt_id", "").strip())
        ex = ekasa.receipt_to_extracted(r)
        return {"ok": True, "partner_name": ex.partner_name, "total_gross": ex.total_gross, "issue_date": ex.issue_date,
                "lines": len(ex.lines)}
    except ekasa.EkasaError as exc:
        return {"ok": False, "error": str(exc)}
