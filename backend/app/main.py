"""FastAPI application: REST API + serving the built frontend (single container)."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

import app.registry.entities  # noqa: F401  (registers entities)
from app.config import get_config
from app.db import SessionLocal
from app.models import User
from app.routers import auth, bank, billing, data, documents, reports, settings, views
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def bootstrap_admin() -> None:
    cfg = get_config()
    if not (cfg.admin_email and cfg.admin_password):
        return
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            db.add(User(email=cfg.admin_email.lower(), name=cfg.admin_name, role="admin",
                        password_hash=hash_password(cfg.admin_password)))
            db.commit()
            log.info("Created bootstrap admin %s", cfg.admin_email)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(get_config().storage_dir).mkdir(parents=True, exist_ok=True)
    try:
        bootstrap_admin()
    except Exception as exc:  # noqa: BLE001
        log.warning("Bootstrap admin skipped: %s", exc)
    yield


app = FastAPI(title="Náklady zákaziek", version="1.1", lifespan=lifespan)

for r in (auth.router, data.router, views.router, documents.router, reports.router, billing.router, bank.router,
          settings.router):
    app.include_router(r)


@app.exception_handler(IntegrityError)
async def integrity_handler(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Údaje porušujú obmedzenie databázy (duplicita alebo chýbajúci povinný údaj)."})


@app.get("/api/health")
def health():
    return {"ok": True}


# ----------------------------------------------------------------------------- frontend (SPA)
FRONTEND = Path(__file__).resolve().parent.parent / "static"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        f = FRONTEND / path
        if path and f.is_file() and FRONTEND in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(FRONTEND / "index.html")
