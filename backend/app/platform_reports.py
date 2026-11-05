"""Portable technical reports from persisted records, rendered with ReportLab."""
from __future__ import annotations

import csv
import json
import io
import os
from pathlib import Path
from xml.sax.saxutils import escape
from collections import Counter

from .platform_db import now, uid
from .platform_jobs import hardware


def pdf_document(lines):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    font_path=Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'
    font='Helvetica'
    if font_path.is_file():
        if 'NVReport' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('NVReport',str(font_path)))
        font='NVReport'
    output=io.BytesIO()
    document=SimpleDocTemplate(output,pagesize=(595,842),rightMargin=45,leftMargin=45,topMargin=60,bottomMargin=50,pdfVersion=(1,4),title='Nazar Vision technical report')
    body=ParagraphStyle('NVBody',fontName=font,fontSize=9,leading=13,textColor=colors.HexColor('#314c70'),spaceAfter=6,splitLongWords=True)
    heading=ParagraphStyle('NVHeading',parent=body,fontSize=12,leading=18,textColor=colors.HexColor('#2563eb'),spaceBefore=12,spaceAfter=10)
    title=ParagraphStyle('NVTitle',parent=heading,fontSize=18,leading=25,spaceBefore=0)
    story=[]
    for index,line in enumerate(lines):
        if not str(line).strip():story.append(Spacer(1,8));continue
        style=title if index==0 else heading if str(line).isupper() and len(str(line))<80 else body
        story.append(Paragraph(escape(str(line)).replace('\n','<br/>'),style))
    def page(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#dbeafe'));canvas.line(45,807,550,807)
        canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#6b83a5'))
        canvas.drawString(45,818,'NAZAR VISION | AI LIFECYCLE PLATFORM')
        canvas.drawString(45,28,'Generated from persisted project records');canvas.drawRightString(550,28,f'Page {doc.page}')
    document.build(story,onFirstPage=page,onLaterPages=page)
    return output.getvalue()


def create_report(db, payload):
    kind = payload.get("kind", "project")
    tables = {"dataset": "platform_datasets", "annotations": "reviews", "preparation": "platform_versions",
              "training": "platform_jobs", "models": "platform_models", "evaluation": "platform_evaluations",
              "comparison": "platform_models"}
    selected = payload.get("entity_id")
    if kind == "project":
        records = {name: db.all(f"SELECT * FROM {table}") for name, table in tables.items() if name != "comparison"}
        records['training'] = db.all("SELECT * FROM platform_jobs WHERE kind='train'")
        records['background_jobs'] = db.all('SELECT * FROM platform_jobs')
    elif kind == "dataset":
        records = {"datasets":db.all("SELECT * FROM platform_datasets"),"images":db.all("SELECT * FROM platform_images"),"quality_decisions":db.all("SELECT * FROM platform_quality_decisions")}
    elif kind == "annotations":
        records = {"reviews":db.all("SELECT * FROM reviews"),"history":db.all("SELECT * FROM review_events")}
    elif kind == 'training':
        records = db.all("SELECT * FROM platform_jobs WHERE kind='train'" + (' AND id=?' if selected else ''), (selected,) if selected else ())
    elif kind in tables:
        table = tables[kind]
        records = db.all(f"SELECT * FROM {table}" + (" WHERE id=?" if selected and table != "reviews" else ""), (selected,) if selected and table != "reviews" else ())
    elif kind == "inference":
        from .config import JOB_ROOT
        records = [json.loads(p.read_text(encoding="utf-8")) for p in JOB_ROOT.glob("*/state.json")]
    else:
        raise ValueError("Unsupported report kind")
    report_id = uid(); folder = db.root / "reports" / report_id; folder.mkdir(parents=True)
    context = {'active_model':db.one("SELECT value FROM platform_settings WHERE key='active_model'"),
               'model_versions':db.all('SELECT id,name,sha256,dataset_id FROM platform_models'),
               'dataset_versions':db.all('SELECT id,name,state FROM platform_versions')}
    snapshot = {"id": report_id, "kind": kind, "generated_at": now(), "software": hardware()["packages"], "context":context,"records": records,
                "qualifications": ["Verified status records approval; reviewer identity is recorded when supplied.",
                                   "Legacy validation metrics do not establish independent field accuracy.",
                                   "Video instances across frames are not unique animals."]}
    (folder / "report.json").write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    with (folder / "report.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream); writer.writerow(["section", "record"])
        writer.writerow(['report_context', json.dumps(context,default=str)])
        for section, data in (records.items() if isinstance(records, dict) else [(kind, records)]):
            for row in data:
                writer.writerow([section, json.dumps(row, default=str)])
    lines=["NAZAR VISION | " + kind.upper() + " REPORT", "Generated " + snapshot["generated_at"], "Report ID: " + report_id, ""]
    for section,data in (records.items() if isinstance(records,dict) else [(kind,records)]):
        lines.extend([section.upper()+f" - {len(data)} records", ""])
        if section in {'reviews','annotations'}:
            lines.append("Decisions: "+json.dumps(dict(Counter(r['status'] for r in data))))
            lines.append("Approved hatchling boxes: "+str(sum(sum(b['class_name']=='hatchling' for b in json.loads(r['boxes_json'])) for r in data if r['status'] in {'verified_positive','verified_negative'})))
        if section=='images':
            codes=Counter(issue['code'] for r in data for issue in json.loads(r['issues_json']))
            lines.append("Original-source quality findings: "+json.dumps(dict(codes)))
            lines.append("Full file checksums, geometry, and findings are retained in the JSON/CSV companion records.")
        else:
            for row in data[:30]:
                compact={k:v for k,v in row.items() if k not in {'boxes_json','before_json','after_json','manifest_json','original_json','predictions_json','config_json','path','log_path'}}
                for key in ('metrics_json','summary_json','result_json'):
                    if key in compact:
                        value=json.loads(compact.pop(key)); compact[key.removesuffix('_json')]={k:v for k,v in value.items() if k not in {'gallery','timeline'}}
                lines.append(json.dumps(compact,default=str))
            if len(data)>30:lines.append(f"{len(data)-30} additional records are retained in JSON and CSV.")
        lines.append("")
    lines.extend(['MODEL AND DATASET VERSION CONTEXT',json.dumps(context,default=str),'',"SOFTWARE",json.dumps(snapshot['software']),"","INTERPRETATION"]+snapshot['qualifications'])
    (folder / "report.pdf").write_bytes(pdf_document(lines))
    db.execute("INSERT INTO platform_reports VALUES(?,?,?,?,?)", (report_id, kind, now(), str(folder), json.dumps({"software": snapshot["software"], "entity_id": selected})))
    return {"report_id": report_id, "kind": kind}
