"""Geração de relatórios analíticos de fechamento mensal e YTD."""

from __future__ import annotations

from io import BytesIO

import pandas as pd


def _customer_key(frame):
    if "Cod Cliente" in frame:
        code = frame["Cod Cliente"].astype("string").str.strip()
        code = code.mask(code.str.casefold().isin(["", "nan", "none", "<na>"]))
    else:
        code = pd.Series(pd.NA, index=frame.index, dtype="string")
    name = frame.get("Cliente", pd.Series(pd.NA, index=frame.index)).astype("string").str.strip().str.upper()
    name = name.mask(name.str.casefold().isin(["", "nan", "none", "<na>"]))
    return code.map(lambda value: f"C:{value}" if pd.notna(value) else pd.NA).fillna(
        name.map(lambda value: f"N:{value}" if pd.notna(value) else pd.NA)
    )


def _period(source, start, end):
    return source[(source["Data"] >= start) & (source["Data"] < end + pd.Timedelta(days=1))]


def _metric_totals(frame):
    revenue = float(frame["Faturamento"].sum()) if not frame.empty else 0.0
    weight = float(frame["Peso"].sum()) if not frame.empty else 0.0
    margin = float(frame["Margem"].sum()) if not frame.empty else 0.0
    clients = 0
    if not frame.empty:
        keyed = frame.assign(_customer=_customer_key(frame))
        clients = int((keyed.dropna(subset=["_customer"]).groupby("_customer")["Faturamento"].sum() > 0).sum())
    return {"revenue": revenue, "weight": weight, "margin": margin,
            "margin_pct": margin / revenue if revenue else 0,
            "price": revenue / weight if weight else 0, "clients": clients}


def _group_metrics(frame, dimension):
    if frame.empty or dimension not in frame:
        return pd.DataFrame(columns=[dimension, "Faturamento", "KG", "Margem", "Clientes positivados"])
    src = frame.copy()
    src[dimension] = src[dimension].fillna("Não informado").astype(str).str.strip().replace("", "Não informado")
    totals = src.groupby(dimension, dropna=False).agg(
        Faturamento=("Faturamento", "sum"), KG=("Peso", "sum"), Margem=("Margem", "sum"),
    ).reset_index()
    src["_customer"] = _customer_key(src)
    positive = src.dropna(subset=["_customer"]).groupby([dimension, "_customer"])["Faturamento"].sum().gt(0)
    positive = positive.groupby(level=0).sum()
    totals["Clientes positivados"] = totals[dimension].map(positive).fillna(0).astype(int)
    totals["Margem %"] = totals["Margem"] / totals["Faturamento"].replace(0, pd.NA)
    totals["Preço médio/kg"] = totals["Faturamento"] / totals["KG"].replace(0, pd.NA)
    return totals


def _compare_groups(current, prior, dimension, top_n, add_yoy=None):
    cur = _group_metrics(current, dimension).rename(columns={
        "Faturamento": "Faturamento R$", "KG": "KG faturado", "Margem": "Margem R$",
        "Margem %": "Margem % atual", "Preço médio/kg": "Preço médio/kg",
        "Clientes positivados": "Clientes positivados",
    })
    prev = _group_metrics(prior, dimension)[[dimension, "Faturamento"]].rename(columns={"Faturamento": "Faturamento comparação R$"})
    result = cur.merge(prev, how="left", on=dimension).fillna({"Faturamento comparação R$": 0})
    base = result["Faturamento comparação R$"]
    result["Variação %"] = (result["Faturamento R$"] / base - 1).where(base.ne(0))
    if add_yoy is not None:
        year = _group_metrics(add_yoy, dimension)[[dimension, "Faturamento"]].rename(columns={"Faturamento": "Faturamento ano anterior R$"})
        result = result.merge(year, how="left", on=dimension).fillna({"Faturamento ano anterior R$": 0})
        ybase = result["Faturamento ano anterior R$"]
        result["Variação anual %"] = (result["Faturamento R$"] / ybase - 1).where(ybase.ne(0))
    return result.sort_values("Faturamento R$", ascending=False).head(top_n)


def build_report_data(history, month, top_n=15, customer_dimension="Segmento Cliente"):
    source = history.copy()
    source["Data"] = pd.to_datetime(source["Data"], errors="coerce")
    source = source.dropna(subset=["Data"])
    month = pd.Timestamp(month).to_period("M").start_time
    end = min(month + pd.offsets.MonthEnd(0), source["Data"].max().normalize())
    previous_month_start = month - pd.DateOffset(months=1)
    if end == month + pd.offsets.MonthEnd(0):
        previous_month_end = previous_month_start + pd.offsets.MonthEnd(0)
    else:
        previous_month_end = min(previous_month_start + pd.offsets.MonthEnd(0), end - pd.DateOffset(months=1))
    previous_year_start = month - pd.DateOffset(years=1)
    previous_year_end = end - pd.DateOffset(years=1)
    ytd_start = pd.Timestamp(month.year, 1, 1)
    previous_ytd_start = pd.Timestamp(month.year - 1, 1, 1)

    periods = {
        "month": _period(source, month, end),
        "prior_month": _period(source, previous_month_start, previous_month_end),
        "prior_year": _period(source, previous_year_start, previous_year_end),
        "ytd": _period(source, ytd_start, end),
        "prior_ytd": _period(source, previous_ytd_start, previous_year_end),
    }
    customer_dimension = customer_dimension if customer_dimension in source else (
        "Tipologia Cliente" if "Tipologia Cliente" in source else "Cliente"
    )
    dimensions = {"Vendedor": "Vendedor", "Grupo de cliente": customer_dimension, "Grupo de produto": "Grupo Produto"}
    tables = {}
    for title, dimension in dimensions.items():
        tables[("month", title)] = _compare_groups(periods["month"], periods["prior_month"], dimension, top_n, periods["prior_year"])
        tables[("ytd", title)] = _compare_groups(periods["ytd"], periods["prior_ytd"], dimension, top_n)
    return {"month": month, "end": end, "top_n": top_n, "periods": periods, "dimensions": dimensions, "tables": tables,
            "totals": {key: _metric_totals(value) for key, value in periods.items()},
            "customer_dimension": customer_dimension}


def _money(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _number(value):
    return f"{value:,.0f}".replace(",", ".")


def _pct(value):
    return "—" if pd.isna(value) else f"{value * 100:+.1f}%".replace(".", ",")


def _cell(value, column):
    if pd.isna(value):
        return "—"
    if column in ("Faturamento R$", "Faturamento comparação R$", "Faturamento ano anterior R$", "Margem R$"):
        return _money(float(value))
    if column in ("Margem % atual", "Variação %", "Variação anual %"):
        return _pct(float(value)) if column.startswith("Variação") else f"{float(value)*100:.2f}%".replace(".", ",")
    if column == "Preço médio/kg":
        return _money(float(value))
    if column == "KG faturado":
        return f"{float(value):,.0f} kg".replace(",", ".")
    return _number(value) if isinstance(value, (int, float)) else str(value)


def _table_rows(frame, limit=15):
    columns = [c for c in (frame.columns if frame is not None else []) if c not in ("Margem R$",)]
    rows = [[str(c) for c in columns]]
    for _, row in frame.head(limit).iterrows():
        rows.append([_cell(row[c], c) for c in columns])
    return rows


def make_pdf(report):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=13*mm, leftMargin=13*mm, topMargin=13*mm, bottomMargin=13*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="MFTitle", parent=styles["Title"], textColor=colors.HexColor("#172033"), alignment=TA_CENTER, fontSize=22))
    styles.add(ParagraphStyle(name="MFSection", parent=styles["Heading1"], textColor=colors.HexColor("#F36A2D"), fontSize=15, spaceBefore=5*mm))
    story = [Paragraph("METALFORTE 360 | Fechamento comercial", styles["MFTitle"]),
             Paragraph(f"Mês: {report['month']:%m/%Y} • Apuração até {report['end']:%d/%m/%Y} • Comparações calculadas sobre os filtros ativos", styles["Normal"]), Spacer(1, 7*mm)]
    for key, label in (("month", "Fechamento do mês"), ("ytd", "Acumulado YTD")):
        t = report["totals"][key]
        refkey = "prior_month" if key == "month" else "prior_ytd"
        ref = report["totals"][refkey]
        annual = report["totals"]["prior_year"] if key == "month" else ref
        story += [Paragraph(label, styles["MFSection"])]
        data = [["Faturamento", "Variação vs ref.", "KG faturado", "Preço médio/kg", "Margem", "Clientes positivados"],
                [_money(t["revenue"]), _pct(t["revenue"] / ref["revenue"] - 1 if ref["revenue"] else float("nan")),
                 f"{t['weight']:,.0f} kg".replace(",", "."), _money(t["price"]), f"{t['margin_pct']*100:.2f}%".replace(".", ","), _number(t["clients"])]]
        table = Table(data, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),colors.HexColor("#172033")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("BACKGROUND",(0,1),(-1,1),colors.HexColor("#F2F5F9")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D7DEE8")),("FONTNAME",(0,0),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),9),("PADDING",(0,0),(-1,-1),7)]))
        story += [table, Paragraph(f"Comparação: {'mês anterior e mesmo mês do ano anterior' if key == 'month' else 'mesmo período do ano anterior'}.", styles["Normal"]), Spacer(1, 3*mm)]
        if key == "month":
            yoy = report["totals"]["prior_year"]
            story.append(Paragraph(f"Mesmo mês ano anterior: {_money(yoy['revenue'])} • Variação anual: {_pct(t['revenue']/yoy['revenue']-1 if yoy['revenue'] else float('nan'))} • Margem: {yoy['margin_pct']*100:.2f}%".replace(".", ",", 1), styles["Normal"]))
        story.append(PageBreak())
    for period, label in (("month", "Mês"), ("ytd", "YTD")):
        for group in report["dimensions"]:
            frame = report["tables"][(period, group)]
            story.append(Paragraph(f"{group} — {label}", styles["MFSection"]))
            if frame.empty:
                story.append(Paragraph("Sem registros para este recorte.", styles["Normal"]))
            else:
                rows = _table_rows(frame, report["top_n"])
                table = Table(rows, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),colors.HexColor("#172033")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F2F5F9")]),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#D7DEE8")),("FONTSIZE",(0,0),(-1,-1),7.5),("PADDING",(0,0),(-1,-1),5)]))
                story.append(table)
            story.append(PageBreak())
    doc.build(story)
    return output.getvalue()


def make_pptx(report):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    dark, orange, pale = RGBColor(23,32,51), RGBColor(243,106,45), RGBColor(242,245,249)

    def title(slide, text, subtitle=None):
        box = slide.shapes.add_textbox(Inches(.55), Inches(.25), Inches(12.1), Inches(.55)).text_frame
        box.text = text
        box.paragraphs[0].font.size = Pt(25); box.paragraphs[0].font.bold = True; box.paragraphs[0].font.color.rgb = dark
        if subtitle:
            sub = slide.shapes.add_textbox(Inches(.58), Inches(.83), Inches(12), Inches(.35)).text_frame
            sub.text = subtitle; sub.paragraphs[0].font.size = Pt(10); sub.paragraphs[0].font.color.rgb = dark

    def summary_slide(key, heading, subtitle, reference):
        slide = prs.slides.add_slide(prs.slide_layouts[6]); title(slide, heading, subtitle)
        current, prev = report["totals"][key], report["totals"][reference]
        metrics = [("Faturamento", _money(current["revenue"]), _pct(current["revenue"]/prev["revenue"]-1 if prev["revenue"] else float("nan"))),
                   ("KG faturado", f"{current['weight']:,.0f} kg".replace(",", "."), ""),
                   ("Preço médio/kg", _money(current["price"]), ""),
                   ("Margem %", f"{current['margin_pct']*100:.2f}%".replace(".", ","), ""),
                   ("Clientes positivados", _number(current["clients"]), "")]
        for i,(label,value,change) in enumerate(metrics):
            x = .65 + (i % 3) * 4.1; y = 1.55 + (i // 3) * 1.45
            shape=slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(3.75), Inches(1.12))
            shape.fill.solid(); shape.fill.fore_color.rgb=pale; shape.line.color.rgb=RGBColor(215,222,232)
            tf=shape.text_frame; tf.clear(); tf.vertical_anchor=MSO_ANCHOR.MIDDLE
            p=tf.paragraphs[0]; p.text=label; p.font.size=Pt(12); p.font.color.rgb=dark
            p=tf.add_paragraph(); p.text=value; p.font.size=Pt(22); p.font.bold=True; p.font.color.rgb=dark
            if change:
                p=tf.add_paragraph(); p.text=f"Variação: {change}"; p.font.size=Pt(11); p.font.color.rgb=orange
        foot=slide.shapes.add_textbox(Inches(.7), Inches(6.75), Inches(12), Inches(.3)).text_frame
        foot.text=f"Comparação: {subtitle}"; foot.paragraphs[0].font.size=Pt(10); foot.paragraphs[0].font.color.rgb=dark

    slide=prs.slides.add_slide(prs.slide_layouts[6]); title(slide,"METALFORTE 360",f"Fechamento {report['month']:%m/%Y} • apuração até {report['end']:%d/%m/%Y}")
    band=slide.shapes.add_shape(1, Inches(.7), Inches(2.0), Inches(11.9), Inches(2.3)); band.fill.solid(); band.fill.fore_color.rgb=dark; band.line.fill.background()
    tf=band.text_frame; tf.clear(); tf.vertical_anchor=MSO_ANCHOR.MIDDLE
    p=tf.paragraphs[0]; p.text="Fechamento analítico mensal + visão YTD"; p.alignment=PP_ALIGN.CENTER; p.font.size=Pt(30); p.font.bold=True; p.font.color.rgb=RGBColor(255,255,255)
    p=tf.add_paragraph(); p.text="Vendedor • Grupo de cliente • Grupo de produto"; p.alignment=PP_ALIGN.CENTER; p.font.size=Pt(17); p.font.color.rgb=RGBColor(255,255,255)
    summary_slide("month", "Fechamento do mês", "Mês anterior; mesmo mês do ano anterior", "prior_month")
    summary_slide("ytd", "Acumulado YTD", "Mesmo período do ano anterior", "prior_ytd")
    for period, label in (("month","Fechamento do mês"),("ytd","Acumulado YTD")):
        for group in report["dimensions"]:
            slide=prs.slides.add_slide(prs.slide_layouts[6]); title(slide,f"{group} | {label}",f"Mês {report['month']:%m/%Y} • até {report['end']:%d/%m/%Y}")
            frame=report["tables"][(period,group)]
            cols=[c for c in frame.columns if c in [report["dimensions"][group],"Faturamento R$","Variação %","Variação anual %","KG faturado","Margem % atual","Preço médio/kg","Clientes positivados"]]
            rows=_table_rows(frame[cols],limit=report["top_n"]) if not frame.empty else [[group], ["Sem registros"]]
            table=slide.shapes.add_table(len(rows),len(rows[0]),Inches(.45),Inches(1.4),Inches(12.4),Inches(5.45)).table
            for r,row in enumerate(rows):
                for c,value in enumerate(row):
                    cell=table.cell(r,c); cell.text=str(value); cell.margin_left=Inches(.05); cell.margin_right=Inches(.05)
                    cell.fill.solid(); cell.fill.fore_color.rgb=dark if r==0 else (pale if r%2==0 else RGBColor(255,255,255))
                    cell.text_frame.vertical_anchor=MSO_ANCHOR.MIDDLE
                    for p in cell.text_frame.paragraphs:
                        p.font.size=Pt(9 if r else 8); p.font.bold=(r==0); p.font.color.rgb=RGBColor(255,255,255) if r==0 else dark
    output=BytesIO(); prs.save(output); return output.getvalue()
