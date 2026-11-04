"""Document extraction with the Claude API (vision / PDF / text) into a neutral structure."""
import base64
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.config import get_config

log = logging.getLogger(__name__)


class ExtractedLine(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = Field(default=None, description="Unit price including VAT")
    vat_rate: float | None = Field(default=None, description="VAT rate in percent, e.g. 23")
    total_net: float | None = None
    total_gross: float | None = Field(default=None, description="Line total including VAT")


class VatRow(BaseModel):
    rate: float | None = None
    base: float | None = None
    vat: float | None = None


class ExtractedDocument(BaseModel):
    doc_type: Literal["receipt", "invoice_in", "invoice_out", "other"] = "receipt"
    partner_name: str | None = Field(default=None, description="Supplier name (issuer) for received docs; customer for issued")
    partner_ico: str | None = None
    partner_dic: str | None = None
    partner_ic_dph: str | None = None
    partner_iban: str | None = None
    partner_address: str | None = None
    buyer_name: str | None = None
    buyer_ico: str | None = Field(default=None, description="IČO of the buyer / customer printed on the document")
    number: str | None = Field(default=None, description="Invoice number or receipt number")
    ekasa_receipt_id: str | None = Field(default=None, description="eKasa receipt ID starting with 'O-' if present")
    issue_date: str | None = Field(default=None, description="YYYY-MM-DD")
    issue_time: str | None = Field(default=None, description="HH:MM 24h")
    due_date: str | None = Field(default=None, description="YYYY-MM-DD")
    tax_date: str | None = Field(default=None, description="Date of taxable supply, YYYY-MM-DD")
    vs: str | None = Field(default=None, description="Variabilný symbol")
    currency: str | None = "EUR"
    total_net: float | None = None
    total_vat: float | None = None
    total_gross: float | None = None
    vat_breakdown: list[VatRow] = Field(default_factory=list)
    lines: list[ExtractedLine] = Field(default_factory=list)
    handwritten_note: str | None = Field(default=None, description="Any handwritten or added note (often a project name)")
    project_hint: str | None = Field(default=None, description="Name of the matching project from the provided list, if any")


SYSTEM = (
    "Si precízny extraktor údajov zo slovenských účtovných dokladov (bločky z eKasy, faktúry). "
    "Vráť údaje presne tak, ako sú na doklade. Sumy ako čísla s desatinnou bodkou. Dátumy ISO (YYYY-MM-DD), čas 24 h. "
    "Ak údaj na doklade nie je, nechaj ho prázdny – nič si nevymýšľaj. Uveď všetky položky. "
    "doc_type: 'receipt' pre pokladničný bloček, 'invoice_in' pre faktúru, kde je odberateľom naša firma, "
    "'invoice_out' pre faktúru, ktorú naša firma vystavila. Partner = protistrana (pri prijatých dokladoch dodávateľ). "
    "Ak je na doklade ručne dopísaná poznámka (napr. názov zákazky), uveď ju v handwritten_note. "
    "Ak z poznámky alebo textu vyplýva jedna zo zákaziek zo zoznamu, uveď jej presný názov v project_hint."
)


def is_available() -> bool:
    return bool(get_config().anthropic_api_key)


def extract(*, images: list[tuple[bytes, str]] | None = None, pdf: bytes | None = None, text: str | None = None,
            company_name: str = "", company_ico: str = "", projects: list[str] | None = None,
            filename: str = "") -> ExtractedDocument:
    """Call Claude with structured output. Raises RuntimeError when the API is not configured or fails."""
    cfg = get_config()
    if not cfg.anthropic_api_key:
        raise RuntimeError("Claude API nie je nakonfigurované (ANTHROPIC_API_KEY).")
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    content: list[dict] = []
    if pdf is not None:
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": base64.standard_b64encode(pdf).decode()}})
    for data, mime in images or []:
        content.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                                                    "data": base64.standard_b64encode(data).decode()}})
    instructions = (
        f"Naša firma: {company_name} (IČO {company_ico or 'neuvedené'}).\n"
        f"Názov súboru: {filename}\n"
        f"Zákazky firmy: {', '.join(projects or []) or '(žiadne)'}\n"
    )
    if text:
        instructions += f"\nText dokladu:\n{text[:60000]}\n"
    content.append({"type": "text", "text": instructions + "\nVyextrahuj údaje dokladu."})
    try:
        response = client.messages.parse(
            model=cfg.claude_model,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=ExtractedDocument,
            output_config={"effort": "low"},
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except anthropic.APIConnectionError as exc:
        raise RuntimeError(f"Claude API nedostupné: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Claude API chyba {exc.status_code}: {exc.message}") from exc
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude API odmietlo spracovať doklad.")
    if response.parsed_output is None:
        raise RuntimeError("Claude API nevrátilo štruktúrované údaje.")
    return response.parsed_output


def b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode()
