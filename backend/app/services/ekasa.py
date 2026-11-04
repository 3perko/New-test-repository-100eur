"""eKasa (Finančná správa SR) – public receipt lookup by receipt ID (O-…)."""
import logging
from datetime import datetime
from decimal import Decimal

import httpx

from app.config import get_config
from app.services.extraction import ExtractedDocument, ExtractedLine, VatRow

log = logging.getLogger(__name__)


class EkasaError(Exception):
    pass


def fetch_receipt(receipt_id: str, client: httpx.Client | None = None) -> dict:
    cfg = get_config()
    if not cfg.ekasa_enabled:
        raise EkasaError("eKasa je vypnutá v konfigurácii.")
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        r = client.post(cfg.ekasa_url, json={"receiptId": receipt_id},
                        headers={"Content-Type": "application/json", "Accept": "application/json"})
        if r.status_code != 200:
            raise EkasaError(f"eKasa odpovedala HTTP {r.status_code}")
        data = r.json()
    except httpx.HTTPError as exc:
        raise EkasaError(f"eKasa nedostupná: {exc}") from exc
    finally:
        if own:
            client.close()
    receipt = data.get("receipt") if isinstance(data, dict) else None
    if not receipt:
        raise EkasaError(f"eKasa doklad nenašla (returnValue={data.get('returnValue') if isinstance(data, dict) else '?'})")
    return receipt


def _d(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v))


def receipt_to_extracted(receipt: dict) -> ExtractedDocument:
    """Map the eKasa JSON to our neutral extraction structure."""
    org = receipt.get("organization") or {}
    unit = receipt.get("unit") or {}
    issue = receipt.get("issueDate") or receipt.get("createDate")
    issue_date = issue_time = None
    if issue:
        for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                dt = datetime.strptime(issue[:19], fmt)
                issue_date, issue_time = dt.date().isoformat(), dt.strftime("%H:%M")
                break
            except ValueError:
                continue
    lines = []
    for it in receipt.get("items") or []:
        qty = _d(it.get("quantity"))
        price = _d(it.get("price"))  # total for the line incl. VAT
        rate = _d(it.get("vatRate"))
        lines.append(ExtractedLine(
            description=it.get("name"), quantity=float(qty) if qty is not None else None,
            unit_price=float(price / qty) if price is not None and qty else None,
            vat_rate=float(rate) if rate is not None else None, total_gross=float(price) if price is not None else None,
            total_net=None))
    vat_rows = []
    for base_k, vat_k, rate_k in (("taxBaseBasic", "vatAmountBasic", "vatRateBasic"),
                                  ("taxBaseReduced", "vatAmountReduced", "vatRateReduced")):
        if receipt.get(base_k):
            vat_rows.append(VatRow(rate=float(receipt.get(rate_k) or 0), base=float(receipt[base_k]),
                                   vat=float(receipt.get(vat_k) or 0)))
    if receipt.get("freeTaxAmount"):
        vat_rows.append(VatRow(rate=0.0, base=float(receipt["freeTaxAmount"]), vat=0.0))
    total = _d(receipt.get("totalPrice"))
    vat_total = sum((Decimal(str(v.vat)) for v in vat_rows), Decimal(0))
    address = ", ".join(str(x) for x in [unit.get("streetName") or org.get("streetName"),
                                          unit.get("buildingNumber") or org.get("buildingNumber"),
                                          unit.get("municipality") or org.get("municipality")] if x)
    return ExtractedDocument(
        doc_type="receipt", partner_name=org.get("name"), partner_ico=str(receipt.get("ico") or org.get("ico") or "") or None,
        partner_dic=str(receipt.get("dic") or org.get("dic") or "") or None,
        partner_ic_dph=receipt.get("icDph") or org.get("icDph"), partner_address=address or None,
        number=str(receipt.get("receiptNumber")) if receipt.get("receiptNumber") is not None else None,
        ekasa_receipt_id=receipt.get("receiptId"), issue_date=issue_date, issue_time=issue_time,
        currency="EUR", total_gross=float(total) if total is not None else None,
        total_vat=float(vat_total) if vat_rows else None,
        total_net=float(total - vat_total) if total is not None and vat_rows else None,
        vat_breakdown=vat_rows, lines=lines, buyer_ico=receipt.get("customerId"),
    )
