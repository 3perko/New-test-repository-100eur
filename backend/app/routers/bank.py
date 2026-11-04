from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from app.deps import Ctx, require_admin
from app.services import bank, storage

router = APIRouter(prefix="/api/bank", tags=["bank"])


@router.post("/import")
async def import_statement(file: UploadFile = File(...), ctx: Ctx = Depends(require_admin)):
    data = await file.read()
    sf, is_new = storage.store_file(ctx.db, company_id=ctx.company_id, name=file.filename or "vypis", data=data,
                                    source="upload", kind_hint="bank", user_id=ctx.user.id)
    if not is_new and sf.status == "processed":
        return {"message": "Tento výpis už bol importovaný.", "duplicate": True}
    try:
        st = bank.import_statement_file(ctx.db, ctx.company, sf, data)
    except bank.BankImportError as exc:
        sf.status, sf.error = "error", str(exc)
        ctx.db.commit()
        raise HTTPException(422, str(exc)) from exc
    sf.status = "processed"
    sf.error = f"Bankový výpis: {st.tx_count} pohybov, nových {st.new_tx_count}"
    ctx.db.commit()
    return {"message": f"Importované pohyby: {st.tx_count}, nové: {st.new_tx_count}.", "statement_id": st.id}


@router.post("/match")
def run_match(ctx: Ctx = Depends(require_admin)):
    return bank.action_rematch(ctx, [], {})


@router.get("/transactions/{tx_id}")
def tx_detail(tx_id: int, ctx: Ctx = Depends(require_admin)):
    return bank.tx_detail(ctx, tx_id)


@router.post("/transactions/{tx_id}/match")
def manual_match(tx_id: int, body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    amt = Decimal(str(body["amount"])) if body.get("amount") not in (None, "") else None
    bank.manual_match(ctx, tx_id, int(body["document_id"]), amt)
    return bank.tx_detail(ctx, tx_id)


@router.post("/transactions/{tx_id}/no-document")
def no_document(tx_id: int, body: dict = Body(default={}), ctx: Ctx = Depends(require_admin)):
    bank.action_no_document(ctx, [tx_id], body)
    return bank.tx_detail(ctx, tx_id)


@router.post("/matches/{match_id}/confirm")
def confirm_match(match_id: int, ctx: Ctx = Depends(require_admin)):
    bank.confirm_match(ctx, match_id)
    return {"ok": True}


@router.delete("/matches/{match_id}")
def delete_match(match_id: int, ctx: Ctx = Depends(require_admin)):
    bank.delete_match(ctx, match_id)
    return {"ok": True}


@router.get("/missing")
def missing(date_from: str | None = None, date_to: str | None = None, ctx: Ctx = Depends(require_admin)):
    return bank.missing_report(ctx.db, ctx.company_id, date.fromisoformat(date_from) if date_from else None,
                               date.fromisoformat(date_to) if date_to else None)
