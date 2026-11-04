from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.deps import Ctx, get_ctx, require_admin
from app.models import DocumentSource, SourceFile
from app.services import documents as ds
from app.services import ingest, jobs, storage

router = APIRouter(prefix="/api", tags=["documents"])
MAX_UPLOAD = 40 * 1024 * 1024


@router.get("/documents/{doc_id}/full")
def get_full(doc_id: int, ctx: Ctx = Depends(require_admin)):
    return ds.doc_to_dict(ctx.db, ds.load_doc(ctx, doc_id))


@router.put("/documents/{doc_id}/full")
def save_full(doc_id: int, body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    doc = ds.load_doc(ctx, doc_id)
    ds.save_full(ctx, doc, body)
    if body.get("confirm"):
        ds.confirm(ctx, doc)
    ctx.db.commit()
    ctx.db.refresh(doc)
    return ds.doc_to_dict(ctx.db, doc)


@router.post("/documents/{doc_id}/confirm")
def confirm(doc_id: int, ctx: Ctx = Depends(require_admin)):
    doc = ds.load_doc(ctx, doc_id)
    ds.confirm(ctx, doc)
    ctx.db.commit()
    return ds.doc_to_dict(ctx.db, doc)


@router.post("/documents/{doc_id}/unconfirm")
def unconfirm(doc_id: int, ctx: Ctx = Depends(require_admin)):
    ds.action_unconfirm(ctx, [doc_id], {})
    return ds.doc_to_dict(ctx.db, ds.load_doc(ctx, doc_id))


@router.post("/documents/{doc_id}/physical")
def physical(doc_id: int, body: dict = Body(default={}), ctx: Ctx = Depends(require_admin)):
    doc = ds.load_doc(ctx, doc_id)
    if body.get("value", True):
        ds.mark_physical(ctx, doc)
    else:
        doc.physical_original = False
        doc.physical_original_at = None
    ctx.db.commit()
    return ds.doc_to_dict(ctx.db, doc)


@router.post("/documents/manual")
def create_manual(body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    doc = ds.create_manual(ctx, body.get("doc_type", "receipt"))
    ctx.db.commit()
    return {"id": doc.id}


@router.post("/documents/split-even")
def split_even(body: dict = Body(...), ctx: Ctx = Depends(get_ctx)):
    from decimal import Decimal
    parts = ds.split_even(Decimal(str(body.get("total") or 0)), int(body.get("n") or 0))
    return {"parts": [float(p) for p in parts]}


@router.get("/files/{file_id}")
def get_file(file_id: int, download: bool = False, ctx: Ctx = Depends(require_admin)):
    sf = ctx.db.get(SourceFile, file_id)
    if not sf or sf.company_id != ctx.company_id:
        raise HTTPException(404, "Súbor neexistuje.")
    path = storage.file_path(sf)
    if not path.exists():
        raise HTTPException(404, "Súbor chýba v úložisku.")
    return FileResponse(path, media_type=sf.mime or "application/octet-stream",
                        filename=sf.original_name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@router.post("/documents/{doc_id}/files")
async def attach(doc_id: int, file: UploadFile = File(...), physical: bool = Form(False),
                 ctx: Ctx = Depends(require_admin)):
    doc = ds.load_doc(ctx, doc_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Súbor je príliš veľký.")
    sf, _ = storage.store_file(ctx.db, company_id=ctx.company_id, name=file.filename or "subor", data=data,
                               source="upload", physical=physical, user_id=ctx.user.id)
    sf.status = "processed"
    sf.document_id = doc.id
    ingest.attach_file(ctx.db, doc, sf, "physical_scan" if physical else "original")
    if physical and doc.doc_type == "receipt":
        ds.mark_physical(ctx, doc)
    ctx.db.commit()
    return ds.doc_to_dict(ctx.db, doc)


@router.delete("/documents/{doc_id}/files/{file_id}")
def detach(doc_id: int, file_id: int, ctx: Ctx = Depends(require_admin)):
    doc = ds.load_doc(ctx, doc_id)
    ctx.db.query(DocumentSource).filter(DocumentSource.document_id == doc.id,
                                        DocumentSource.source_file_id == file_id).delete()
    if doc.source_file_id == file_id:
        doc.source_file_id = None
    ctx.db.commit()
    return ds.doc_to_dict(ctx.db, doc)


# ----------------------------------------------------------------------------- inbox
@router.post("/inbox/upload")
async def upload(files: list[UploadFile] = File(...), kind: str = Form("auto"), physical: bool = Form(False),
                 note: str = Form(""), process: bool = Form(True), ctx: Ctx = Depends(require_admin)):
    if kind not in ("auto", "receipt", "invoice_in", "invoice_out", "bank"):
        raise HTTPException(422, "Neplatný druh dokladu.")
    stored = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"Súbor {f.filename} je príliš veľký.")
        sf, is_new = storage.store_file(ctx.db, company_id=ctx.company_id, name=f.filename or "subor", data=data,
                                        source="upload", kind_hint=kind, physical=physical, user_id=ctx.user.id,
                                        note=note or None)
        stored.append({"file": sf.original_name, "id": sf.id, "new": is_new, "status": sf.status,
                       "document_id": sf.document_id})
    ctx.db.commit()
    results = ingest.process_pending(ctx.db, ctx.company_id) if process else []
    return {"stored": stored, "results": results}


@router.post("/inbox/run")
def run_inbox(ctx: Ctx = Depends(require_admin)):
    return jobs.run_inbox(ctx.db, ctx.company)


@router.post("/receipts/quick-check")
async def quick_check(file: UploadFile | None = File(None), ekasa_id: str = Form(""), mark_physical: bool = Form(True),
                      ctx: Ctx = Depends(require_admin)):
    data = await file.read() if file else None
    res = ingest.quick_check(ctx.db, ctx.company_id, ekasa_id=ekasa_id or None, image=data)
    if res.get("found") and mark_physical and not res.get("physical_original"):
        doc = ds.load_doc(ctx, res["document_id"])
        if data:
            sf, _ = storage.store_file(ctx.db, company_id=ctx.company_id, name=file.filename or "sken.jpg", data=data,
                                       source="upload", physical=True, user_id=ctx.user.id)
            sf.status, sf.document_id = "duplicate", doc.id
            ingest.attach_file(ctx.db, doc, sf, "physical_scan")
        ds.mark_physical(ctx, doc)
        ctx.db.commit()
        res["marked_physical"] = True
    elif not res.get("found") and data and res.get("ekasa_id"):
        # not registered yet -> new record from the physical scan
        sf, _ = storage.store_file(ctx.db, company_id=ctx.company_id, name=file.filename or "sken.jpg", data=data,
                                   source="upload", kind_hint="receipt", physical=True, user_id=ctx.user.id)
        ctx.db.commit()
        r = ingest.process_pending(ctx.db, ctx.company_id)
        res["created"] = r
        res["message"] = "Bloček nebol zaevidovaný – založený nový záznam na kontrolu."
    return res
