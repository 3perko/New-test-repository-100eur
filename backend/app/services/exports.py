"""Exports: XLSX / CSV for any table view, PDF for billing and worker statements."""
import csv
import io
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

MONEY_FMT = '#,##0.00 "€"'
NUM_FMT = "#,##0.00"
DATE_FMT = "DD.MM.YYYY"


def fmt_date(v) -> str:
    if not v:
        return ""
    if isinstance(v, str):
        try:
            v = date.fromisoformat(v[:10])
        except ValueError:
            return v
    return v.strftime("%d.%m.%Y")


def fmt_num(v, decimals=2, suffix="") -> str:
    if v is None or v == "":
        return ""
    s = f"{float(v):,.{decimals}f}".replace(",", " ").replace(".", ",")
    return s + suffix


def fmt_money(v) -> str:
    return fmt_num(v, 2, " €")


def table_xlsx(title: str, columns: list[dict], rows: list[dict], totals: dict | None = None) -> bytes:
    """columns: [{key, label, type, options?}]"""
    wb = Workbook()
    ws = wb.active
    ws.title = (title or "Export")[:31]
    head_fill = PatternFill("solid", fgColor="E5E7EB")
    for i, c in enumerate(columns, 1):
        cell = ws.cell(row=1, column=i, value=c["label"])
        cell.font = Font(bold=True)
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for r_i, row in enumerate(rows, 2):
        for c_i, c in enumerate(columns, 1):
            v = _cell_value(c, row)
            cell = ws.cell(row=r_i, column=c_i, value=v)
            if c["type"] == "money":
                cell.number_format = MONEY_FMT
            elif c["type"] in ("number", "hours"):
                cell.number_format = NUM_FMT
            elif c["type"] == "date" and isinstance(v, date):
                cell.number_format = DATE_FMT
            elif c["type"] == "datetime" and isinstance(v, datetime):
                cell.number_format = "DD.MM.YYYY HH:MM"
    if totals:
        r_i = len(rows) + 2
        ws.cell(row=r_i, column=1, value="Spolu").font = Font(bold=True)
        for c_i, c in enumerate(columns, 1):
            if c["key"] in totals and totals[c["key"]] is not None and c_i > 1:
                cell = ws.cell(row=r_i, column=c_i, value=totals[c["key"]])
                cell.font = Font(bold=True)
                cell.number_format = MONEY_FMT if c["type"] == "money" else NUM_FMT
    for i, c in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, len(c["label"]) + 4))
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell_value(c: dict, row: dict):
    v = row.get(c["key"])
    if c["type"] in ("ref", "multiref"):
        return row.get(c["key"] + "__label") or (v if not isinstance(v, list) else "")
    if c["type"] == "select" and c.get("options"):
        return {o["value"]: o["label"] for o in c["options"]}.get(v, v)
    if c["type"] == "bool":
        return "áno" if v else ("nie" if v is not None else "")
    if c["type"] == "date" and isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return v
    if c["type"] == "datetime" and isinstance(v, str):
        try:
            return datetime.fromisoformat(v).replace(tzinfo=None)
        except ValueError:
            return v
    return v


def table_csv(columns: list[dict], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c["label"] for c in columns])
    for row in rows:
        out = []
        for c in columns:
            v = _cell_value(c, row)
            if isinstance(v, (date, datetime)):
                v = v.strftime("%d.%m.%Y %H:%M") if isinstance(v, datetime) else v.strftime("%d.%m.%Y")
            elif isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            out.append("" if v is None else v)
        w.writerow(out)
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ----------------------------------------------------------------------------- PDF
_FONT_READY = False


def _fonts() -> tuple[str, str]:
    global _FONT_READY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if _FONT_READY:
        return "AppSans", "AppSans-Bold"
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for reg, bold in candidates:
        if Path(reg).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("AppSans", reg))
            pdfmetrics.registerFont(TTFont("AppSans-Bold", bold))
            _FONT_READY = True
            return "AppSans", "AppSans-Bold"
    return "Helvetica", "Helvetica-Bold"


def _pdf_doc(title: str, story_builder) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=title)
    doc.build(story_builder())
    return buf.getvalue()


def _styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    reg, bold = _fonts()
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName=bold, fontSize=15, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName=bold, fontSize=11.5, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontName=reg, fontSize=9, leading=12),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontName=reg, fontSize=8, leading=10),
        "cell": ParagraphStyle("cell", parent=ss["Normal"], fontName=reg, fontSize=8, leading=10),
        "reg": reg, "bold": bold,
    }


def _table(data, widths, st, right_cols=(), bold_last=False):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle
    rows = [[Paragraph(str(c), st["cell"]) if isinstance(c, str) and len(c) > 25 else c for c in r] for r in data]
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [("FONT", (0, 0), (-1, -1), st["reg"], 8), ("FONT", (0, 0), (-1, 0), st["bold"], 8),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9CA3AF")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    for c in right_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    if bold_last:
        style.append(("FONT", (0, -1), (-1, -1), st["bold"], 8))
    t.setStyle(TableStyle(style))
    return t


def billing_pdf(d: dict) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    st = _styles()
    fixed = d.get("billing_type") == "fixed"

    def build():
        s = [Paragraph(f"Podklad k fakturácii – {d['project_name']}", st["h1"]),
             Paragraph(f"Obdobie: {fmt_date(d['period_from'])} – {fmt_date(d['period_to'])} · "
                       f"Stav: {'uzavretý' if d['status'] == 'closed' else 'návrh'} · Podklad č. {d['id']}", st["p"])]
        comp = d["company"]
        s.append(Paragraph(f"Dodávateľ: {comp['name']}, IČO {comp.get('ico') or '–'}"
                           f"{', IČ DPH ' + comp['ic_dph'] if comp.get('ic_dph') else ''}", st["p"]))
        if d.get("customer"):
            c = d["customer"]
            s.append(Paragraph(f"Odberateľ: {c['name']}, IČO {c.get('ico') or '–'}"
                               f"{', ' + c['address'] if c.get('address') else ''}", st["p"]))
        if fixed:
            s.append(Paragraph("Zákazka s pevnou cenou – prehľad vykonanej práce bez ocenenia.", st["p"]))
        s.append(Spacer(1, 4 * mm))
        groups = [("hours", "Práca"), ("material", "Materiál"), ("transport", "Doprava"), ("other", "Iné")]
        for key, label in groups:
            lines = [ln for ln in d["lines"] if ln["line_type"] == key]
            if not lines:
                continue
            s.append(Paragraph(label, st["h2"]))
            if key == "hours":
                if d.get("group_by") == "day":
                    agg: dict = {}
                    for ln in lines:
                        a = agg.setdefault(ln["date"], {"q": 0.0, "amt": 0.0, "desc": []})
                        a["q"] += ln["quantity"] or 0
                        a["amt"] += ln["amount"] or 0
                        if ln.get("description"):
                            a["desc"].append(f"{ln.get('worker_name') or ''}: {ln['description']}")
                    data = [["Dátum", "Popis", "Hodiny", "Suma"]] + [
                        [fmt_date(k), "; ".join(v["desc"])[:300], fmt_num(v["q"]), "" if fixed else fmt_money(v["amt"])]
                        for k, v in sorted(agg.items())]
                    widths = [22 * mm, 108 * mm, 20 * mm, 30 * mm]
                else:
                    agg = {}
                    for ln in lines:
                        k = (ln.get("worker_name") or "", ln.get("rate"))
                        a = agg.setdefault(k, {"q": 0.0, "amt": 0.0})
                        a["q"] += ln["quantity"] or 0
                        a["amt"] += ln["amount"] or 0
                    data = [["Pracovník", "Hodiny", "Sadzba", "Suma"]] + [
                        [k[0], fmt_num(v["q"]), "" if fixed else fmt_money(k[1]), "" if fixed else fmt_money(v["amt"])]
                        for k, v in sorted(agg.items(), key=lambda x: x[0][0])]
                    widths = [80 * mm, 30 * mm, 35 * mm, 35 * mm]
                tq = sum(ln["quantity"] or 0 for ln in lines)
                ta = sum(ln["amount"] or 0 for ln in lines)
                data.append(["Spolu", "", fmt_num(tq), "" if fixed else fmt_money(ta)] if d.get("group_by") == "day"
                            else ["Spolu", fmt_num(tq), "", "" if fixed else fmt_money(ta)])
                s.append(_table(data, widths, st, right_cols=(1, 2, 3) if d.get("group_by") != "day" else (2, 3),
                                bold_last=True))
            else:
                data = [["Dátum", "Popis", "Množstvo", "Cena", "Prirážka", "Suma"]]
                for ln in lines:
                    data.append([fmt_date(ln["date"]), ln.get("description") or "",
                                 f"{fmt_num(ln['quantity'])} {ln.get('unit') or ''}", "" if fixed else fmt_money(ln["rate"]),
                                 f"{fmt_num(ln['markup_pct'])} %" if ln.get("markup_pct") else "",
                                 "" if fixed else fmt_money(ln["amount"])])
                data.append(["Spolu", "", "", "", "", "" if fixed else fmt_money(sum(ln["amount"] or 0 for ln in lines))])
                s.append(_table(data, [20 * mm, 72 * mm, 22 * mm, 22 * mm, 18 * mm, 26 * mm], st,
                                right_cols=(2, 3, 4, 5), bold_last=True))
        if not fixed:
            s.append(Spacer(1, 4 * mm))
            data = [["", "Suma"], ["Spolu bez DPH", fmt_money(d["total_net"])]]
            if comp.get("vat_payer"):
                data += [[f"DPH {fmt_num(d['vat_rate'], 0)} %", fmt_money(d["total_vat"])],
                         ["Spolu s DPH", fmt_money(d["total_gross"])]]
            s.append(_table(data, [130 * mm, 50 * mm], st, right_cols=(1,), bold_last=True))
        if d.get("note"):
            s += [Spacer(1, 3 * mm), Paragraph(f"Poznámka: {d['note']}", st["p"])]
        s += [Spacer(1, 6 * mm), Paragraph(f"Vygenerované {datetime.now():%d.%m.%Y %H:%M}", st["small"])]
        return s
    return _pdf_doc(f"Podklad {d['id']}", build)


def worker_pdf(d: dict) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    st = _styles()

    def build():
        w = d["worker"]
        rel = {"employee": "zamestnanec", "contractor": "živnostník", "other": "iné"}.get(w["relation_type"], "")
        s = [Paragraph(f"Podklad pre pracovníka – {w['name']}", st["h1"]),
             Paragraph(f"Obdobie: {fmt_date(d['period_from'])} – {fmt_date(d['period_to'])} · {d['company']} · {rel}"
                       f"{' · IČO ' + w['ico'] if w.get('ico') else ''}", st["p"]),
             Spacer(1, 3 * mm)]
        data = [["Dátum", "Od", "Do", "Hodiny", "Zákazka", "Popis práce", "Suma"]]
        for r in d["rows"]:
            data.append([fmt_date(r["date"]), r.get("time_from") or "", r.get("time_to") or "", fmt_num(r["hours"]),
                         r["project"] or "", r.get("description") or "", fmt_money(r["amount"])])
        data.append(["Spolu", "", "", fmt_num(d["total_hours"]), "", "", fmt_money(d["total_amount"])])
        s.append(_table(data, [19 * mm, 11 * mm, 11 * mm, 15 * mm, 35 * mm, 66 * mm, 23 * mm], st,
                        right_cols=(3, 6), bold_last=True))
        s.append(Paragraph("Súhrn po zákazkách", st["h2"]))
        data = [["Zákazka", "Hodiny", "Suma"]] + [[p["project"], fmt_num(p["hours"]), fmt_money(p["amount"])]
                                                  for p in d["by_project"]]
        data.append(["Spolu", fmt_num(d["total_hours"]), fmt_money(d["total_amount"])])
        s.append(_table(data, [110 * mm, 30 * mm, 40 * mm], st, right_cols=(1, 2), bold_last=True))
        label = ("Suma, ktorú pracovník fakturuje firme" if w["relation_type"] == "contractor"
                 else "Podklad k mzde (suma podľa nákladovej sadzby)")
        s += [Spacer(1, 4 * mm), Paragraph(f"{label}: <b>{fmt_money(d['total_amount'])}</b> za "
                                           f"{fmt_num(d['total_hours'])} h", st["p"]),
              Spacer(1, 6 * mm), Paragraph(f"Vygenerované {datetime.now():%d.%m.%Y %H:%M}", st["small"])]
        return s
    return _pdf_doc(f"Podklad {w_name(d)}", build)


def w_name(d):
    return d["worker"]["name"]


def billing_xlsx(d: dict) -> bytes:
    cols = [{"key": "line_type", "label": "Typ", "type": "select",
             "options": [{"value": "hours", "label": "Práca"}, {"value": "material", "label": "Materiál"},
                         {"value": "transport", "label": "Doprava"}, {"value": "other", "label": "Iné"}]},
            {"key": "date", "label": "Dátum", "type": "date"}, {"key": "worker_name", "label": "Pracovník", "type": "text"},
            {"key": "description", "label": "Popis", "type": "text"},
            {"key": "quantity", "label": "Množstvo", "type": "number"}, {"key": "unit", "label": "MJ", "type": "text"},
            {"key": "rate", "label": "Sadzba / cena", "type": "money"},
            {"key": "markup_pct", "label": "Prirážka %", "type": "number"}, {"key": "amount", "label": "Suma", "type": "money"}]
    return table_xlsx(f"Podklad {d['id']}", cols, d["lines"], {"amount": d["total_net"]})


def worker_xlsx(d: dict) -> bytes:
    cols = [{"key": "date", "label": "Dátum", "type": "date"}, {"key": "time_from", "label": "Od", "type": "text"},
            {"key": "time_to", "label": "Do", "type": "text"}, {"key": "hours", "label": "Hodiny", "type": "hours"},
            {"key": "project", "label": "Zákazka", "type": "text"}, {"key": "company", "label": "Firma", "type": "text"},
            {"key": "description", "label": "Popis práce", "type": "text"},
            {"key": "cost_rate", "label": "Sadzba", "type": "money"}, {"key": "amount", "label": "Suma", "type": "money"}]
    return table_xlsx(d["worker"]["name"], cols, d["rows"], {"hours": d["total_hours"], "amount": d["total_amount"]})
