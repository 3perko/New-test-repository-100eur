"""Google Drive + Gmail adapters (OAuth 2.0 with a regular Gmail account).

Flow: Settings → Integrations → "Pripojiť Google účet" → consent → refresh token stored in settings.
Drive: list inbox folder of each company, download new files, move them to the "processed" folder.
Gmail: messages sent to the plus-address (name+<tag>@gmail.com) → attachments → Drive inbox (or directly to the app).
"""
import base64
import json
import logging
import secrets
import time
import urllib.parse
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import get_config
from app.models import Company
from app.services import storage
from app.services.settings import get_value, set_value

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/gmail.modify",
          "openid", "email"]
TOKEN_KEY = "google.oauth"
STATE_KEY = "google.oauth_state"
DOC_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff")
BANK_EXT = (".xml", ".csv", ".xlsx", ".pdf", ".sta")


class GoogleError(Exception):
    pass


def redirect_uri() -> str:
    return get_config().app_base_url.rstrip("/") + "/api/integrations/google/callback"


def configured() -> bool:
    cfg = get_config()
    return bool(cfg.google_client_id and cfg.google_client_secret)


def auth_url(db: Session) -> str:
    cfg = get_config()
    if not configured():
        raise GoogleError("Chýba GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET v konfigurácii.")
    state = secrets.token_urlsafe(24)
    set_value(db, STATE_KEY, state)
    db.commit()
    q = {"client_id": cfg.google_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)


def handle_callback(db: Session, code: str, state: str) -> str:
    cfg = get_config()
    if not state or state != get_value(db, STATE_KEY):
        raise GoogleError("Neplatný stav OAuth (state).")
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": cfg.google_client_id, "client_secret": cfg.google_client_secret,
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code"}, timeout=30)
    if r.status_code != 200:
        raise GoogleError(f"Google token chyba: {r.text[:300]}")
    tok = r.json()
    email = None
    if tok.get("id_token"):
        try:
            payload = tok["id_token"].split(".")[1]
            payload += "=" * (-len(payload) % 4)
            email = json.loads(base64.urlsafe_b64decode(payload)).get("email")
        except (ValueError, IndexError):
            pass
    set_value(db, TOKEN_KEY, {"refresh_token": tok.get("refresh_token"), "access_token": tok.get("access_token"),
                              "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60, "email": email,
                              "connected_at": datetime.now(timezone.utc).isoformat()})
    set_value(db, STATE_KEY, None)
    db.commit()
    return email or ""


def status(db: Session) -> dict:
    tok = get_value(db, TOKEN_KEY) or {}
    return {"configured": configured(), "connected": bool(tok.get("refresh_token")), "email": tok.get("email"),
            "connected_at": tok.get("connected_at"), "redirect_uri": redirect_uri(),
            "last_sync": get_value(db, "google.last_sync")}


def disconnect(db: Session) -> None:
    set_value(db, TOKEN_KEY, None)
    db.commit()


def _access_token(db: Session) -> str:
    cfg = get_config()
    tok = get_value(db, TOKEN_KEY) or {}
    if not tok.get("refresh_token"):
        raise GoogleError("Google účet nie je pripojený.")
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time():
        return tok["access_token"]
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": cfg.google_client_id, "client_secret": cfg.google_client_secret,
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        raise GoogleError(f"Obnovenie Google tokenu zlyhalo: {r.text[:300]}")
    data = r.json()
    tok["access_token"] = data["access_token"]
    tok["expires_at"] = time.time() + int(data.get("expires_in", 3600)) - 60
    set_value(db, TOKEN_KEY, tok)
    db.commit()
    return tok["access_token"]


class _Client:
    def __init__(self, db: Session):
        self.http = httpx.Client(timeout=60, headers={"Authorization": f"Bearer {_access_token(db)}"})

    def get(self, url, **kw):
        r = self.http.get(url, **kw)
        if r.status_code >= 400:
            raise GoogleError(f"Google API {r.status_code}: {r.text[:300]}")
        return r

    def post(self, url, **kw):
        r = self.http.post(url, **kw)
        if r.status_code >= 400:
            raise GoogleError(f"Google API {r.status_code}: {r.text[:300]}")
        return r

    def patch(self, url, **kw):
        r = self.http.patch(url, **kw)
        if r.status_code >= 400:
            raise GoogleError(f"Google API {r.status_code}: {r.text[:300]}")
        return r


DRIVE = "https://www.googleapis.com/drive/v3"


def drive_list(c: _Client, folder_id: str) -> list[dict]:
    files, token = [], None
    while True:
        params = {"q": f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                  "fields": "nextPageToken, files(id, name, mimeType, size, createdTime)", "pageSize": 200,
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if token:
            params["pageToken"] = token
        data = c.get(f"{DRIVE}/files", params=params).json()
        files += data.get("files", [])
        token = data.get("nextPageToken")
        if not token:
            return files


def drive_download(c: _Client, file_id: str) -> bytes:
    return c.get(f"{DRIVE}/files/{file_id}", params={"alt": "media", "supportsAllDrives": "true"}).content


def drive_move(c: _Client, file_id: str, from_folder: str, to_folder: str) -> None:
    c.patch(f"{DRIVE}/files/{file_id}", params={"addParents": to_folder, "removeParents": from_folder,
                                                 "supportsAllDrives": "true"})


def drive_upload(c: _Client, folder_id: str, name: str, data: bytes, mime: str) -> str:
    boundary = "----app" + secrets.token_hex(8)
    meta = json.dumps({"name": name, "parents": [folder_id]})
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
    r = c.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true",
               content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"})
    return r.json()["id"]


def sync_drive(db: Session, company: Company) -> dict:
    """Download new files from the company's Drive inboxes into the app (dedupe by hash) and move them."""
    from app.services.settings import get_param
    c = _Client(db)
    physical_default = bool(get_param(db, "inbox_physical_default", company.id))
    stats = {"downloaded": 0, "duplicates": 0}
    for folder, kind in ((company.drive_inbox_folder_id, "auto"), (company.drive_bank_inbox_folder_id, "bank")):
        if not folder:
            continue
        for f in drive_list(c, folder):
            data = drive_download(c, f["id"])
            sf, is_new = storage.store_file(db, company_id=company.id, name=f["name"], data=data, source="drive",
                                            kind_hint=kind, physical=physical_default and kind == "auto",
                                            drive_file_id=f["id"])
            stats["downloaded" if is_new else "duplicates"] += 1
            db.commit()
            if company.drive_processed_folder_id:
                drive_move(c, f["id"], folder, company.drive_processed_folder_id)
    set_value(db, "google.last_sync", datetime.now(timezone.utc).isoformat())
    db.commit()
    return stats


GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"


def _walk_parts(part: dict):
    yield part
    for p in part.get("parts", []) or []:
        yield from _walk_parts(p)


def fetch_gmail(db: Session, companies: list[Company]) -> dict:
    """Process unread mails sent to plus-addresses; attachments go to Drive inbox (if set) and into the app."""
    c = _Client(db)
    tok = get_value(db, TOKEN_KEY) or {}
    email = tok.get("email") or ""
    local, _, domain = email.partition("@")
    stats = {"messages": 0, "attachments": 0}
    for comp in companies:
        for tag, kind, folder in ((comp.email_tag_invoices, "auto", comp.drive_inbox_folder_id),
                                  (comp.email_tag_bank, "bank", comp.drive_bank_inbox_folder_id)):
            if not tag or not local:
                continue
            addr = f"{local}+{tag}@{domain}"
            q = f"to:{addr} is:unread has:attachment"
            msgs = c.get(f"{GMAIL}/messages", params={"q": q, "maxResults": 50}).json().get("messages", [])
            for m in msgs:
                full = c.get(f"{GMAIL}/messages/{m['id']}").json()
                stats["messages"] += 1
                for part in _walk_parts(full.get("payload", {})):
                    fname = part.get("filename")
                    att_id = (part.get("body") or {}).get("attachmentId")
                    if not fname or not att_id:
                        continue
                    if not fname.lower().endswith(BANK_EXT if kind == "bank" else DOC_EXT):
                        continue
                    att = c.get(f"{GMAIL}/messages/{m['id']}/attachments/{att_id}").json()
                    data = base64.urlsafe_b64decode(att["data"])
                    if folder:
                        try:
                            drive_upload(c, folder, fname, data, part.get("mimeType") or "application/octet-stream")
                        except GoogleError as exc:
                            log.warning("Upload to Drive failed: %s", exc)
                    storage.store_file(db, company_id=comp.id, name=fname, data=data, source="email", kind_hint=kind)
                    stats["attachments"] += 1
                c.post(f"{GMAIL}/messages/{m['id']}/modify", json={"removeLabelIds": ["UNREAD"]})
                db.commit()
    return stats
