from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response

from app.deps import Ctx, get_ctx, require_admin
from app.services import billing, exports

router = APIRouter(prefix="/api", tags=["billing"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _dates(body_or_q) -> tuple[date, date]:
    try:
        return date.fromisoformat(body_or_q["date_from"]), date.fromisoformat(body_or_q["date_to"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "Zadajte obdobie od–do.") from exc


@router.post("/billing/preview")
def preview(body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    d_from, d_to = _dates(body)
    return billing.preview(ctx, int(body["project_id"]), d_from, d_to)


@router.post("/billing")
def create(body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    d_from, d_to = _dates(body)
    st = billing.create(ctx, int(body["project_id"]), d_from, d_to, body.get("group_by") or "worker", body.get("note"))
    return billing.to_dict(ctx, st)


@router.get("/billing/{st_id}")
def get(st_id: int, ctx: Ctx = Depends(require_admin)):
    return billing.to_dict(ctx, billing.load(ctx, st_id))


@router.patch("/billing/{st_id}")
def update(st_id: int, body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    st = billing.load(ctx, st_id)
    billing.update_lines(ctx, st, body)
    return billing.to_dict(ctx, st)


@router.post("/billing/{st_id}/close")
def close(st_id: int, ctx: Ctx = Depends(require_admin)):
    st = billing.load(ctx, st_id)
    billing.close(ctx, st)
    return billing.to_dict(ctx, st)


@router.post("/billing/{st_id}/reopen")
def reopen(st_id: int, ctx: Ctx = Depends(require_admin)):
    st = billing.load(ctx, st_id)
    billing.reopen(ctx, st)
    return billing.to_dict(ctx, st)


@router.post("/billing/{st_id}/invoice")
def link_invoice(st_id: int, body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    st = billing.load(ctx, st_id)
    billing.link_invoice(ctx, st, int(body["document_id"]) if body.get("document_id") else None)
    return billing.to_dict(ctx, st)


@router.get("/billing/{st_id}/export")
def export(st_id: int, format: str = "pdf", ctx: Ctx = Depends(require_admin)):
    d = billing.to_dict(ctx, billing.load(ctx, st_id))
    name = f"podklad-{st_id}"
    if format == "xlsx":
        return Response(exports.billing_xlsx(d), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    if format == "csv":
        cols = [{"key": k, "label": k, "type": "text"} for k in
                ("line_type", "date", "worker_name", "description", "quantity", "unit", "rate", "markup_pct", "amount")]
        return Response(exports.table_csv(cols, d["lines"]), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return Response(exports.billing_pdf(d), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.get("/worker-statement")
def worker_statement(date_from: str, date_to: str, worker_id: int | None = None, all_companies: bool = False,
                     ctx: Ctx = Depends(get_ctx)):
    d_from, d_to = _dates({"date_from": date_from, "date_to": date_to})
    if ctx.role != "admin":
        worker_id = ctx.user.worker_id
    if not worker_id:
        raise HTTPException(422, "Vyberte pracovníka.")
    return billing.worker_statement(ctx, worker_id, d_from, d_to, all_companies)


@router.get("/worker-statement/export")
def worker_statement_export(date_from: str, date_to: str, worker_id: int | None = None, format: str = "pdf",
                            all_companies: bool = False, ctx: Ctx = Depends(get_ctx)):
    d = worker_statement(date_from, date_to, worker_id, all_companies, ctx)
    name = f"podklad-{d['worker']['name']}-{date_from}".replace(" ", "-")
    if format == "xlsx":
        return Response(exports.worker_xlsx(d), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="{_ascii(name)}.xlsx"'})
    return Response(exports.worker_pdf(d), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{_ascii(name)}.pdf"'})


def _ascii(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if ord(c) < 128)
