from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT = "NotoSansSC"
FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansSC-Regular.ttf"
pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))


def _value(row, key, default=""):
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = default
    return default if value is None else value


def _money(value) -> str:
    return f"¥{float(value or 0):,.2f}"


def _number(value) -> str:
    number = float(value or 0)
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(18 * mm, 10 * mm, "库存管理系统 · 电子业务单据")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"第 {doc.page} 页")
    canvas.restoreState()


def _paragraph(text, style):
    safe = str(text or "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def _build_pdf(title, number, metadata, columns, item_rows, total, remark, status, void_reason=""):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{title} {number}",
        author="库存管理系统",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle", parent=styles["Title"], fontName=FONT, fontSize=20,
        leading=26, alignment=TA_CENTER, textColor=colors.HexColor("#0F172A"),
        spaceAfter=3 * mm,
    )
    normal = ParagraphStyle(
        "ChineseNormal", parent=styles["BodyText"], fontName=FONT, fontSize=9,
        leading=13, textColor=colors.HexColor("#334155"),
    )
    small = ParagraphStyle(
        "ChineseSmall", parent=normal, fontSize=8, leading=11,
    )
    right = ParagraphStyle("ChineseRight", parent=normal, alignment=TA_RIGHT, fontSize=11)

    story = [Paragraph(title, title_style)]
    story.append(Paragraph(f"单据编号：{number}", ParagraphStyle(
        "Number", parent=normal, alignment=TA_CENTER, textColor=colors.HexColor("#64748B")
    )))
    story.append(Spacer(1, 6 * mm))

    metadata_cells = []
    for label, value in metadata:
        metadata_cells.extend([
            _paragraph(label, small),
            _paragraph(value, normal),
        ])
    if len(metadata_cells) % 4:
        metadata_cells.extend(["", ""])
    metadata_rows = [metadata_cells[index:index + 4] for index in range(0, len(metadata_cells), 4)]
    metadata_table = Table(metadata_rows, colWidths=[24 * mm, 62 * mm, 24 * mm, 62 * mm])
    metadata_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([metadata_table, Spacer(1, 6 * mm)])

    table_data = [[_paragraph(label, small) for label, _, _ in columns]]
    for item in item_rows:
        row = []
        for _, key, _ in columns:
            value = _value(item, key)
            row.append(_paragraph(value, small))
        table_data.append(row)
    widths = [width for _, _, width in columns]
    detail_table = Table(table_data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    detail_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (-3, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([detail_table, Spacer(1, 5 * mm)])
    story.append(Paragraph(f"合计金额：<b>{_money(total)}</b>", right))
    story.append(Spacer(1, 4 * mm))

    notes = [[_paragraph("备注", small), _paragraph(remark or "-", normal)]]
    if status == "已作废":
        notes.append([_paragraph("作废说明", small), _paragraph(void_reason or "-", normal)])
    notes_table = Table(notes, colWidths=[24 * mm, 148 * mm])
    notes_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([notes_table, Spacer(1, 9 * mm)])
    signature_table = Table([
        [_paragraph("制单：________________", normal), _paragraph("审核：________________", normal),
         _paragraph("签收：________________", normal)]
    ], colWidths=[57 * mm, 57 * mm, 58 * mm])
    signature_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(KeepTogether(signature_table))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _product_columns():
    widths = [25 * mm, 40 * mm, 32 * mm, 15 * mm, 18 * mm, 21 * mm, 21 * mm]
    keys = ["product_code", "product_name", "spec", "unit", "quantity", "price", "amount"]
    labels = ["产品编码", "产品名称", "规格型号", "单位", "数量", "单价", "金额"]
    return [(label, key, width) for label, key, width in zip(labels, keys, widths)]


def _formatted_product_rows(items):
    rows = []
    for item in items:
        rows.append({
            "product_code": _value(item, "product_code"),
            "product_name": _value(item, "product_name"),
            "spec": _value(item, "spec"),
            "unit": _value(item, "unit"),
            "quantity": _number(_value(item, "quantity")),
            "price": _money(_value(item, "price")),
            "amount": _money(_value(item, "amount")),
        })
    return rows


def inbound_pdf(header, items) -> bytes:
    columns = _product_columns()
    return _build_pdf(
        "入库单", _value(header, "order_no"),
        [("入库日期", _value(header, "order_date")), ("供应商", _value(header, "supplier", "-")),
         ("仓库", _value(header, "warehouse")), ("经办人", _value(header, "operator", "-")),
         ("单据状态", _value(header, "status")), ("生成方式", "系统电子单据")],
        columns, _formatted_product_rows(items), _value(header, "total_amount"),
        _value(header, "remark"), _value(header, "status"), _value(header, "void_reason"),
    )


def outbound_pdf(header, items) -> bytes:
    columns = _product_columns()
    outbound_type = _value(header, "outbound_type", "销售出库")
    party_label = "领料人/部门" if outbound_type == "领料出库" else "客户"
    title = "领料出库单" if outbound_type == "领料出库" else "销售出库单"
    party = _value(header, "material_recipient", "-") if outbound_type == "领料出库" else _value(header, "customer_name")
    return _build_pdf(
        title, _value(header, "order_no"),
        [("出库日期", _value(header, "order_date")), (party_label, party or "-"),
         ("仓库", _value(header, "warehouse")), ("经办人", _value(header, "operator", "-")),
         ("出库类型", outbound_type), ("单据状态", _value(header, "status"))],
        columns, _formatted_product_rows(items), _value(header, "total_amount"),
        _value(header, "remark"), _value(header, "status"), _value(header, "void_reason"),
    )


def settlement_pdf(header, items) -> bytes:
    columns = [
        ("出库单号", "order_no", 62 * mm),
        ("出库日期", "order_date", 42 * mm),
        ("本次结算金额", "amount", 68 * mm),
    ]
    rows = [{
        "order_no": _value(item, "order_no"),
        "order_date": _value(item, "order_date"),
        "amount": _money(_value(item, "amount")),
    } for item in items]
    return _build_pdf(
        "结算单", _value(header, "settlement_no"),
        [("结算日期", _value(header, "settlement_date")), ("客户", _value(header, "customer_name")),
         ("结算方式", _value(header, "method")), ("经办人", _value(header, "operator", "-")),
         ("单据状态", _value(header, "status")), ("客户编码", _value(header, "customer_code"))],
        columns, rows, _value(header, "amount"), _value(header, "remark"),
        _value(header, "status"), _value(header, "void_reason"),
    )
