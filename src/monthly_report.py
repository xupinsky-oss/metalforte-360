"""Geração de relatórios analíticos de fechamento mensal e YTD."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

_LOGO_PATH = Path(__file__).resolve().parents[1] / "LOGO_METALFORTE.jpg"
_BRAND_DARK = "#172033"
_BRAND_ORANGE = "#F36A2D"
_BRAND_MID = "#778397"
_BRAND_PALE = "#F2F5F9"


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


def _comparison_values(report, period, metric):
    """Séries comparáveis para fechamento mensal e acumulado YTD."""
    if period == "month":
        keys = ("month", "prior_month", "prior_year")
        labels = ("Mês atual", "Mês anterior", "Mesmo mês AA")
    else:
        keys = ("ytd", "prior_ytd")
        labels = ("YTD atual", "YTD ano anterior")
    return list(labels), [float(report["totals"][key][metric]) for key in keys]


def make_pdf(report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as PDFImage
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=13*mm, leftMargin=13*mm, topMargin=12*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="MFTitleBrand", parent=styles["Title"], textColor=colors.HexColor(_BRAND_DARK), fontSize=19, alignment=1))
    styles.add(ParagraphStyle(name="MFSectionBrand", parent=styles["Heading1"], textColor=colors.HexColor(_BRAND_ORANGE), fontSize=14, spaceBefore=3*mm, spaceAfter=2*mm))
    styles.add(ParagraphStyle(name="MFChartBrand", parent=styles["Heading3"], textColor=colors.HexColor(_BRAND_DARK), alignment=1, fontSize=9, leading=11))

    def page_chrome(canvas, doc_):
        canvas.saveState()
        width, _ = landscape(A4)
        canvas.setStrokeColor(colors.HexColor(_BRAND_ORANGE)); canvas.setLineWidth(2)
        canvas.line(13*mm, 11*mm, width-13*mm, 11*mm)
        if doc_.page > 1 and _LOGO_PATH.exists():
            canvas.drawImage(str(_LOGO_PATH), width-30*mm, landscape(A4)[1]-22*mm, width=17*mm, height=17*mm, preserveAspectRatio=True, mask="auto")
        canvas.setFillColor(colors.HexColor(_BRAND_DARK)); canvas.setFont("Helvetica", 7)
        canvas.drawString(13*mm, 7*mm, "METALFORTE 360  •  Fechamento comercial")
        canvas.drawRightString(width-13*mm, 7*mm, str(doc_.page))
        canvas.restoreState()

    def comparison_chart(period, metric, scale):
        labels, raw_values = _comparison_values(report, period, metric)
        drawing = Drawing(255, 112)
        chart = VerticalBarChart()
        chart.x, chart.y, chart.width, chart.height = 28, 22, 214, 81
        chart.data = [[raw_values[0]/scale, 0, 0], [0, raw_values[1]/scale, 0], [0, 0, raw_values[2]/scale]] if len(raw_values) == 3 else [[raw_values[0]/scale, 0], [0, raw_values[1]/scale]]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 7
        chart.categoryAxis.labels.fillColor = colors.HexColor(_BRAND_DARK)
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.labels.fillColor = colors.HexColor(_BRAND_MID)
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max([value/scale for value in raw_values] + [1]) * 1.15
        chart.valueAxis.valueStep = chart.valueAxis.valueMax/4
        chart.valueAxis.labelTextFormat = "%.1f"
        chart.valueAxis.visibleGrid = True
        chart.valueAxis.gridStrokeColor = colors.HexColor("#D7DEE8")
        chart.valueAxis.gridStrokeWidth = .45
        chart.valueAxis.strokeColor = colors.HexColor("#D7DEE8")
        chart.categoryAxis.strokeColor = colors.HexColor("#D7DEE8")
        palette = [colors.HexColor(_BRAND_ORANGE), colors.HexColor(_BRAND_MID), colors.HexColor("#BEC6D0")]
        for series_index in range(len(chart.data)):
            chart.bars[series_index].fillColor = palette[series_index]
            chart.bars[series_index].strokeColor = colors.white
        chart.barWidth = 30 if len(labels) == 2 else 23
        chart.barSpacing = 11
        chart.groupSpacing = 16
        chart.barLabelFormat = lambda value: "" if value <= 0 else f"{value:.1f}"
        chart.barLabels.fontName = "Helvetica-Bold"
        chart.barLabels.fontSize = 7
        chart.barLabels.fillColor = colors.HexColor(_BRAND_DARK)
        drawing.add(chart)
        return drawing

    if _LOGO_PATH.exists():
        logo = PDFImage(str(_LOGO_PATH), width=34*mm, height=19*mm, kind="proportional")
        header = Table([[logo, [Paragraph("METALFORTE 360 | Fechamento comercial", styles["MFTitleBrand"]),
                                Paragraph(f"Competência {report['month']:%m/%Y} • dados até {report['end']:%d/%m/%Y} • filtros globais aplicados", styles["Normal"])]]],
                       colWidths=[44*mm, 224*mm], hAlign="LEFT")
        header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,0),(-1,-1),2,colors.HexColor(_BRAND_ORANGE)),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
        story = [header, Spacer(1,4*mm)]
    else:
        story = [Paragraph("METALFORTE 360 | Fechamento comercial", styles["MFTitleBrand"]),
                 Paragraph(f"Competência {report['month']:%m/%Y} • dados até {report['end']:%d/%m/%Y}", styles["Normal"]), Spacer(1,4*mm)]

    for period, heading, reference in (("month", "Fechamento do mês", "prior_month"), ("ytd", "Acumulado YTD", "prior_ytd")):
        current, prior = report["totals"][period], report["totals"][reference]
        story.append(Paragraph(heading, styles["MFSectionBrand"]))
        data = [["Faturamento", "Variação vs comparação", "KG faturado", "Preço médio/kg", "Margem", "Clientes positivados"],
                [_money(current["revenue"]), _pct(current["revenue"]/prior["revenue"]-1 if prior["revenue"] else float("nan")),
                 f"{current['weight']:,.0f} kg".replace(",", "."), _money(current["price"]),
                 f"{current['margin_pct']*100:.2f}%".replace(".", ","), _number(current["clients"])]]
        kpis = Table(data, colWidths=[42*mm,39*mm,39*mm,37*mm,30*mm,42*mm], hAlign="LEFT")
        kpis.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(_BRAND_DARK)),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                                  ("BACKGROUND",(0,1),(-1,1),colors.HexColor(_BRAND_PALE)),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D7DEE8")),
                                  ("FONTNAME",(0,0),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),8),("PADDING",(0,0),(-1,-1),6)]))
        labels = "Atual × mês anterior × mesmo mês do ano anterior" if period == "month" else "YTD atual × mesmo período do ano anterior"
        graphs = Table([[Paragraph("Faturamento (R$ milhões)",styles["MFChartBrand"]),Paragraph("Peso (mil kg)",styles["MFChartBrand"]),Paragraph("Clientes positivados",styles["MFChartBrand"])],
                         [comparison_chart(period,"revenue",1_000_000),comparison_chart(period,"weight",1_000),comparison_chart(period,"clients",1)]],
                        colWidths=[88*mm,88*mm,88*mm], hAlign="LEFT")
        graphs.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
                                    ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        story += [kpis, Spacer(1,2*mm), Paragraph(f"Comparação: {labels}.",styles["Normal"]), graphs]
        if period == "month":
            year = report["totals"]["prior_year"]
            annual_change = _pct(current["revenue"]/year["revenue"]-1 if year["revenue"] else float("nan"))
            story.append(Paragraph(f"Mesmo mês do ano anterior: {_money(year['revenue'])} • variação anual: {annual_change}", styles["Normal"]))
        story.append(PageBreak())

    detail_sections = [(period,label,group) for period,label in (("month","Mês"),("ytd","YTD")) for group in report["dimensions"]]
    for section_index,(period,label,group) in enumerate(detail_sections):
        frame = report["tables"][(period,group)]
        story.append(Paragraph(f"{group} — {label}", styles["MFSectionBrand"]))
        if frame.empty:
            story.append(Paragraph("Sem registros para este recorte.", styles["Normal"]))
        else:
            rows = _table_rows(frame,report["top_n"])
            table = Table(rows,repeatRows=1,hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(_BRAND_DARK)),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                                       ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor(_BRAND_PALE)]),
                                       ("GRID",(0,0),(-1,-1),.3,colors.HexColor("#D7DEE8")),("FONTSIZE",(0,0),(-1,-1),7),
                                       ("PADDING",(0,0),(-1,-1),4)]))
            story.append(table)
        if section_index < len(detail_sections)-1:
            story.append(PageBreak())
    doc.build(story,onFirstPage=page_chrome,onLaterPages=page_chrome)
    return output.getvalue()


def make_pptx(report):
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    dark, orange, pale = RGBColor(23,32,51), RGBColor(243,106,45), RGBColor(242,245,249)

    def brand_header(slide, heading, subtitle):
        slide.background.fill.solid(); slide.background.fill.fore_color.rgb = RGBColor(255,255,255)
        if _LOGO_PATH.exists():
            slide.shapes.add_picture(str(_LOGO_PATH), Inches(.55), Inches(.22), width=Inches(1.35))
        box = slide.shapes.add_textbox(Inches(2.05), Inches(.28), Inches(10.7), Inches(.5)).text_frame
        box.text = heading; p=box.paragraphs[0]; p.font.size=Pt(23); p.font.bold=True; p.font.color.rgb=dark
        sub = slide.shapes.add_textbox(Inches(2.08), Inches(.82), Inches(10.6), Inches(.34)).text_frame
        sub.text = subtitle; sub.paragraphs[0].font.size=Pt(10); sub.paragraphs[0].font.color.rgb=dark
        line=slide.shapes.add_shape(1,Inches(.55),Inches(1.22),Inches(12.2),Inches(.045)); line.fill.solid(); line.fill.fore_color.rgb=orange; line.line.fill.background()

    def footer(slide):
        frame=slide.shapes.add_textbox(Inches(.6),Inches(7.16),Inches(12),Inches(.18)).text_frame
        frame.text="METALFORTE 360  •  Dados consolidados a partir dos filtros selecionados no painel"
        frame.paragraphs[0].font.size=Pt(8); frame.paragraphs[0].font.color.rgb=dark

    def add_chart(slide, left, heading, metric, scale, number_format, period):
        labels, values = _comparison_values(report,period,metric)
        box=slide.shapes.add_textbox(Inches(left),Inches(2.62),Inches(3.98),Inches(.3)).text_frame
        box.text=heading; box.paragraphs[0].font.size=Pt(12); box.paragraphs[0].font.bold=True; box.paragraphs[0].font.color.rgb=dark
        chart_data=CategoryChartData(); chart_data.categories=labels; chart_data.add_series("Valor",[value/scale for value in values])
        chart=slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,Inches(left),Inches(2.95),Inches(3.98),Inches(3.8),chart_data).chart
        chart.has_legend=False; chart.has_title=False; chart.chart_style=10
        chart.value_axis.has_major_gridlines=True; chart.value_axis.tick_labels.font.size=Pt(9); chart.value_axis.tick_labels.number_format=number_format
        chart.category_axis.tick_labels.font.size=Pt(9)
        chart.plots[0].gap_width=85; chart.plots[0].vary_by_categories=True
        chart.plots[0].has_data_labels=True
        chart.plots[0].data_labels.show_value=True
        chart.plots[0].data_labels.position=XL_LABEL_POSITION.OUTSIDE_END
        chart.plots[0].data_labels.font.size=Pt(9); chart.plots[0].data_labels.number_format=number_format
        palette=[RGBColor(243,106,45),RGBColor(119,131,151),RGBColor(190,198,208)]
        for idx,point in enumerate(chart.series[0].points):
            point.format.fill.solid(); point.format.fill.fore_color.rgb=palette[idx%len(palette)]; point.format.line.fill.background()

    def summary_slide(period, heading, subtitle, reference):
        slide=prs.slides.add_slide(prs.slide_layouts[6]); brand_header(slide,heading,subtitle)
        current,prior=report["totals"][period],report["totals"][reference]
        metrics=[("Faturamento",_money(current["revenue"]),_pct(current["revenue"]/prior["revenue"]-1 if prior["revenue"] else float("nan"))),
                 ("KG faturado",f"{current['weight']:,.0f} kg".replace(",","."),""),
                 ("Preço médio/kg",_money(current["price"]),""),
                 ("Margem %",f"{current['margin_pct']*100:.2f}%".replace(".",","),""),
                 ("Clientes positivados",_number(current["clients"]),"")]
        for idx,(label,value,change) in enumerate(metrics):
            x=.5+idx*2.57
            shape=slide.shapes.add_shape(1,Inches(x),Inches(1.48),Inches(2.38),Inches(.96))
            shape.fill.solid(); shape.fill.fore_color.rgb=pale; shape.line.color.rgb=RGBColor(215,222,232)
            tf=shape.text_frame; tf.clear(); tf.vertical_anchor=MSO_ANCHOR.MIDDLE
            p=tf.paragraphs[0]; p.text=label; p.font.size=Pt(9); p.font.color.rgb=dark
            p=tf.add_paragraph(); p.text=value; p.font.size=Pt(15); p.font.bold=True; p.font.color.rgb=dark
            if change:
                p=tf.add_paragraph(); p.text=f"Vs comparação: {change}"; p.font.size=Pt(8); p.font.color.rgb=orange
        add_chart(slide,.55,"Faturamento (R$ milhões)","revenue",1_000_000,"#,##0.0",period)
        add_chart(slide,4.68,"Peso faturado (mil kg)","weight",1_000,"#,##0.0",period)
        add_chart(slide,8.81,"Clientes positivados","clients",1,"#,##0",period)
        footer(slide)

    cover=prs.slides.add_slide(prs.slide_layouts[6]); brand_header(cover,"METALFORTE 360",f"Fechamento {report['month']:%m/%Y} • dados até {report['end']:%d/%m/%Y}")
    statement=cover.shapes.add_textbox(Inches(.9),Inches(2.25),Inches(11.5),Inches(1.2)).text_frame
    statement.text="Fechamento comercial mensal e acumulado YTD"
    statement.paragraphs[0].font.size=Pt(32); statement.paragraphs[0].font.bold=True; statement.paragraphs[0].font.color.rgb=dark
    p=statement.add_paragraph(); p.text="Comparações contra períodos equivalentes, com visões por vendedor, grupo de cliente e grupo de produto."
    p.font.size=Pt(19); p.font.color.rgb=dark
    footer(cover)

    summary_slide("month","Fechamento mensal","Atual, mês anterior e mesmo mês do ano anterior","prior_month")
    summary_slide("ytd","Acumulado YTD","YTD atual comparado ao mesmo período do ano anterior","prior_ytd")
    for period,label in (("month","Fechamento mensal"),("ytd","Acumulado YTD")):
        for group in report["dimensions"]:
            slide=prs.slides.add_slide(prs.slide_layouts[6]); brand_header(slide,f"{group} | {label}",f"Competência {report['month']:%m/%Y} • apuração até {report['end']:%d/%m/%Y}")
            frame=report["tables"][(period,group)]
            cols=[c for c in frame.columns if c in [report["dimensions"][group],"Faturamento R$","Variação %","Variação anual %","KG faturado","Margem % atual","Preço médio/kg","Clientes positivados"]]
            rows=_table_rows(frame[cols],limit=report["top_n"]) if not frame.empty else [[group],["Sem registros"]]
            table=slide.shapes.add_table(len(rows),len(rows[0]),Inches(.45),Inches(1.55),Inches(12.4),Inches(5.35)).table
            for row_index,row in enumerate(rows):
                for col_index,value in enumerate(row):
                    cell=table.cell(row_index,col_index); cell.text=str(value); cell.margin_left=Inches(.05); cell.margin_right=Inches(.05)
                    cell.fill.solid(); cell.fill.fore_color.rgb=dark if row_index==0 else (pale if row_index%2==0 else RGBColor(255,255,255))
                    cell.text_frame.vertical_anchor=MSO_ANCHOR.MIDDLE
                    for paragraph in cell.text_frame.paragraphs:
                        paragraph.font.size=Pt(9 if row_index else 8); paragraph.font.bold=(row_index==0); paragraph.font.color.rgb=RGBColor(255,255,255) if row_index==0 else dark
            footer(slide)
    output=BytesIO(); prs.save(output); return output.getvalue()
