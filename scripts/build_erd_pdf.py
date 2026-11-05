"""Build the Nazar Vision conceptual/logical ERD as a vector PDF.

Source of truth: docs/Nazar_Vision_Entity_Relationship_Model.md and
docs/diagrams/Nazar_Vision_Conceptual_ERD.mmd. This script intentionally
does not alter either source file.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "pdf" / "Nazar_Vision_Entity_Relationship_Diagram.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

FONT_ROOT = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Segoe", str(FONT_ROOT / "segoeui.ttf")))
pdfmetrics.registerFont(TTFont("Segoe-Bold", str(FONT_ROOT / "segoeuib.ttf")))
pdfmetrics.registerFont(TTFont("Consolas", str(FONT_ROOT / "consola.ttf")))

W, H = landscape(A4)
C = canvas.Canvas(str(OUT), pagesize=(W, H), pageCompression=1)
C.setTitle("Nazar Vision - Entity Relationship Model")
C.setAuthor("Nazar Vision project team")
C.setSubject("Conceptual and logical model for the FiftyOne dataset and experiment artifacts")

NAVY = colors.HexColor("#10243A")
NAVY_2 = colors.HexColor("#183B57")
TEAL = colors.HexColor("#007F86")
TEAL_2 = colors.HexColor("#0B9CA3")
GOLD = colors.HexColor("#B57929")
INK = colors.HexColor("#1B2A3B")
MUTED = colors.HexColor("#52677B")
PALE = colors.HexColor("#F5F8FA")
PALE_TEAL = colors.HexColor("#EAF7F7")
PALE_GOLD = colors.HexColor("#FFF8EC")
BORDER = colors.HexColor("#D6E1E8")
CONNECT = colors.HexColor("#476F84")
WHITE = colors.white

CARD_W = 205
CARD_H = 180
X1, X2, X3 = 50, 318, 586
YT, YB = 285, 75


def txt(x, y, value, size=9, font="Segoe", color=INK, align="left"):
    C.setFont(font, size)
    C.setFillColor(color)
    if align == "right":
        C.drawRightString(x, y, value)
    elif align == "center":
        C.drawCentredString(x, y, value)
    else:
        C.drawString(x, y, value)


def rounded(x, y, w, h, radius=9, fill=WHITE, stroke=BORDER, stroke_width=0.8):
    C.setLineWidth(stroke_width)
    C.setFillColor(fill)
    C.setStrokeColor(stroke)
    C.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def line(points, color=CONNECT, width=1.45, dash=None):
    C.setStrokeColor(color)
    C.setLineWidth(width)
    C.setDash(dash or [])
    path = C.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    C.drawPath(path)
    C.setDash([])


def arrowhead(x, y, direction, color=CONNECT):
    C.setFillColor(color)
    p = C.beginPath()
    if direction == "right":
        p.moveTo(x, y)
        p.lineTo(x - 6, y + 3.5)
        p.lineTo(x - 6, y - 3.5)
    elif direction == "up":
        p.moveTo(x, y)
        p.lineTo(x - 3.5, y - 6)
        p.lineTo(x + 3.5, y - 6)
    elif direction == "down":
        p.moveTo(x, y)
        p.lineTo(x - 3.5, y + 6)
        p.lineTo(x + 3.5, y + 6)
    p.close()
    C.drawPath(p, fill=1, stroke=0)


def tag(x, y, label, fill=TEAL, size=7.0):
    width = pdfmetrics.stringWidth(label, "Segoe-Bold", size) + 10
    C.setFillColor(fill)
    C.roundRect(x, y - 2, width, 13, 4, fill=1, stroke=0)
    txt(x + width / 2, y + 1.1, label, size, "Segoe-Bold", WHITE, "center")
    return width


def paragraph(lines, x, y, size=8.7, leading=13, color=MUTED, font="Segoe"):
    for row in lines:
        txt(x, y, row, size, font, color)
        y -= leading
    return y


def page_header(kicker, title, subtitle, page):
    C.setFillColor(PALE)
    C.rect(0, 0, W, H, fill=1, stroke=0)
    txt(50, H - 44, kicker, 8.3, "Segoe-Bold", TEAL)
    txt(50, H - 72, title, 21, "Segoe-Bold", NAVY)
    txt(50, H - 91, subtitle, 9, "Segoe", MUTED)
    C.setStrokeColor(BORDER)
    C.setLineWidth(0.8)
    C.line(50, H - 103, W - 50, H - 103)
    footer(page)


def footer(page):
    C.setStrokeColor(BORDER)
    C.setLineWidth(0.75)
    C.line(50, 52, W - 50, 52)
    txt(50, 32, "NAZAR VISION  /  CONCEPTUAL + LOGICAL ERD  /  PROPOSED V1.0", 7.2,
        "Segoe-Bold", MUTED)
    txt(W - 50, 32, f"{page} / 7", 7.2, "Segoe-Bold", MUTED, "right")


def entity(x, y, name, category, attrs, tint=TEAL):
    # A lightly offset shadow adds depth while all text and edges remain vector.
    C.setFillColor(colors.HexColor("#E6EDF1"))
    C.roundRect(x + 2, y - 2, CARD_W, CARD_H, 8, fill=1, stroke=0)
    rounded(x, y, CARD_W, CARD_H, 8, WHITE, BORDER, 0.8)
    C.setFillColor(tint)
    C.roundRect(x, y + CARD_H - 32, CARD_W, 32, 8, fill=1, stroke=0)
    C.rect(x, y + CARD_H - 32, CARD_W, 14, fill=1, stroke=0)
    txt(x + 12, y + CARD_H - 20, name, 10.1, "Segoe-Bold", WHITE)
    txt(x + CARD_W - 12, y + CARD_H - 46, category.upper(), 6.7,
        "Segoe-Bold", tint, "right")
    start = y + CARD_H - 61
    spacing = 14.4 if len(attrs) >= 8 else 16.0
    for i, (kind, field, typ) in enumerate(attrs):
        yy = start - i * spacing
        left = x + 13
        if kind:
            tag(left, yy - 1.3, kind, TEAL if kind == "PK" else GOLD, 6.2)
            left += 26
        txt(left, yy, field, 8.05, "Consolas", INK)
        txt(x + CARD_W - 11, yy, typ, 7.0, "Segoe", MUTED, "right")


def relation_h(xa, xb, y, name, right="0..*"):
    line([(xa, y), (xb, y)])
    arrowhead(xb, y, "right")
    txt((xa + xb) / 2, y + 10, name, 6.9, "Segoe-Bold", CONNECT, "center")
    txt(xa + 3, y - 12, "1", 6.8, "Segoe-Bold", CONNECT)
    txt(xb - 2, y - 12, right, 6.8, "Segoe-Bold", CONNECT, "right")


def relation_v(x, ya, yb, name, target="0..*"):
    line([(x, ya), (x, yb)])
    arrowhead(x, yb, "up" if yb > ya else "down")
    mid = (ya + yb) / 2
    txt(x + 7, mid + 1, name, 6.8, "Segoe-Bold", CONNECT)
    source_y = ya + 4 if yb > ya else ya - 10
    target_y = yb - 10 if yb > ya else yb + 4
    txt(x - 8, source_y, "1", 6.8, "Segoe-Bold", CONNECT, "right")
    txt(x - 8, target_y, target, 6.8,
        "Segoe-Bold", CONNECT, "right")


def relation_elbow(points, name, source_label=(0, 0), target_label=(0, 0)):
    line(points)
    ex, ey = points[-1]
    px, py = points[-2]
    arrowhead(ex, ey, "up" if ey > py else "down" if ey < py else "right")
    # Each label position is hand placed in the open lane between cards.
    if source_label != (0, 0):
        txt(*source_label, "1", 6.8, "Segoe-Bold", CONNECT)
    if target_label != (0, 0):
        txt(*target_label, "0..*", 6.8, "Segoe-Bold", CONNECT)
    longest = max(zip(points, points[1:]), key=lambda pair: abs(pair[1][0] - pair[0][0]))
    ax, ay = longest[0]
    bx, by = longest[1]
    if abs(bx - ax) >= 80:
        txt((ax + bx) / 2, ay + 6, name, 7.0, "Segoe-Bold", CONNECT, "center")
    else:
        # Short horizontal ends have room for cardinality only. Place the
        # relationship name along the vertical lane between entity columns.
        vertical = max(zip(points, points[1:]),
                       key=lambda pair: abs(pair[1][1] - pair[0][1]))
        vx = vertical[0][0]
        vy = (vertical[0][1] + vertical[1][1]) / 2
        C.saveState()
        C.translate(vx - 7, vy)
        C.rotate(90)
        txt(0, 0, name, 6.9, "Segoe-Bold", CONNECT, "center")
        C.restoreState()


ENTITIES = {
    "SOURCE_DATASET": ("provenance", [
        ("PK", "source_dataset_id", "string"), ("", "title", "string"),
        ("", "provider", "string"), ("", "version", "string"),
        ("", "license", "string"), ("", "source_uri", "string")]),
    "WORKING_DATASET": ("FiftyOne / MongoDB", [
        ("PK", "working_dataset_id", "string"), ("", "fiftyone_name", "string"),
        ("", "persistent", "boolean"), ("", "imported_at", "datetime")]),
    "MEDIA_SAMPLE": ("FiftyOne sample", [
        ("PK", "sample_id", "string"), ("FK", "source_dataset_id", "string"),
        ("FK", "working_dataset_id", "string"), ("", "source_file_path", "string"),
        ("", "source_split", "string"), ("", "assignment_tags", "string"),
        ("", "source_group_key", "string"), ("", "content_sha256", "string")]),
    "ANNOTATION_BOX": ("embedded Detection", [
        ("PK", "annotation_id", "string"), ("FK", "sample_id", "string"),
        ("", "role", "string"), ("", "class_label", "string"),
        ("", "x", "float"), ("", "y", "float"),
        ("", "width", "float"), ("", "height", "float")]),
    "CLASS_MAPPING": ("configuration file", [
        ("PK", "mapping_id", "string"), ("", "config_path", "string"),
        ("", "config_sha256", "string"), ("", "captured_at", "datetime")]),
    "LABEL_MAPPING_ENTRY": ("mapping entry", [
        ("PK", "mapping_entry_id", "string"), ("FK", "mapping_id", "string"),
        ("", "reviewed_label", "string"),
        ("", "canonical_label_nullable", "string?")]),
    "DATASET_CHECKPOINT": ("backup artifact", [
        ("PK", "checkpoint_id", "string"), ("FK", "working_dataset_id", "string"),
        ("", "created_at", "datetime"), ("", "mongodb_backup_uri", "string"),
        ("", "image_manifest_uri", "string"),
        ("", "dataset_fingerprint", "string")]),
    "EXPORT_SNAPSHOT": ("frozen YOLO export", [
        ("PK", "export_id", "string"), ("FK", "checkpoint_id", "string"),
        ("FK", "mapping_id", "string"), ("", "exported_at", "datetime"),
        ("", "yolo_export_uri", "string"), ("", "split_manifest_uri", "string"),
        ("", "export_sha256", "string")]),
    "TRAINING_RUN": ("experiment record", [
        ("PK", "training_run_id", "string"), ("FK", "export_id", "string"),
        ("", "model_family", "string"), ("", "settings_uri", "string"),
        ("", "settings_sha256", "string"), ("", "started_at", "datetime"),
        ("", "status", "string")]),
    "MODEL_ARTIFACT": ("weight file", [
        ("PK", "model_artifact_id", "string"),
        ("FK", "training_run_id", "string"), ("", "weights_uri", "string"),
        ("", "weights_sha256", "string"), ("", "artifact_kind", "string")]),
    "EVALUATION_RUN": ("evaluation record", [
        ("PK", "evaluation_run_id", "string"),
        ("FK", "model_artifact_id", "string"), ("FK", "export_id", "string"),
        ("", "split_name", "string"), ("", "predictions_field", "string"),
        ("", "settings_uri", "string"), ("", "evaluated_at", "datetime")]),
    "IMAGE_PREDICTION": ("FiftyOne Detection", [
        ("PK", "prediction_id", "string"),
        ("FK", "evaluation_run_id", "string"), ("FK", "sample_id", "string"),
        ("", "predicted_label", "string"), ("", "confidence", "float"),
        ("", "normalized_bbox", "string")]),
    "METRIC_RESULT": ("result artifact", [
        ("PK", "metric_result_id", "string"),
        ("FK", "evaluation_run_id", "string"), ("", "metric_name", "string"),
        ("", "class_or_slice", "string"), ("", "value", "float"),
        ("", "evaluation_settings", "string")]),
    "VIDEO_SOURCE": ("prerecorded input", [
        ("PK", "video_source_id", "string"), ("", "source_path", "string"),
        ("", "source_kind", "string"),
        ("", "frame_rate_nullable", "float?"),
        ("", "content_sha256", "string")]),
    "VIDEO_INFERENCE_RUN": ("inference artifact", [
        ("PK", "video_run_id", "string"),
        ("FK", "video_source_id", "string"),
        ("FK", "model_artifact_id", "string"),
        ("", "settings_uri", "string"),
        ("", "annotated_output_uri", "string"),
        ("", "detections_output_uri", "string"),
        ("", "processed_at", "datetime")]),
    "FRAME_DETECTION": ("result artifact", [
        ("PK", "frame_detection_id", "string"),
        ("FK", "video_run_id", "string"), ("", "frame_index", "int"),
        ("", "timestamp_seconds", "float"),
        ("", "predicted_label", "string"), ("", "confidence", "float"),
        ("", "normalized_bbox", "string")]),
}


def draw_entity(x, y, name, tint=TEAL):
    category, attrs = ENTITIES[name]
    entity(x, y, name, category, attrs, tint)


def overview():
    C.setFillColor(PALE)
    C.rect(0, 0, W, H, fill=1, stroke=0)
    txt(50, 546, "NAZAR VISION", 9.5, "Segoe-Bold", TEAL)
    txt(50, 508, "Entity relationship model", 30, "Segoe-Bold", NAVY)
    txt(50, 482, "Hatchling detection proof of concept  |  Data lineage, annotation state, and experiment artifacts",
        10, "Segoe", MUTED)
    rounded(637, 505, 155, 48, 9, WHITE, BORDER)
    txt(650, 534, "PROPOSED DESIGN", 8.2, "Segoe-Bold", TEAL)
    txt(650, 516, "Version 1.0  |  18 Oct 2026", 8, "Segoe", MUTED)

    rounded(50, 286, W - 100, 173, 14, NAVY, NAVY)
    txt(68, 432, "DATA LIFECYCLE", 9.3, "Segoe-Bold", colors.HexColor("#82DADB"))
    stages = [
        ("01", "Import", ["Source files +", "persistent dataset"]),
        ("02", "Curate", ["Reviewed boxes +", "class mapping"]),
        ("03", "Freeze", ["Checkpoint +", "YOLO export"]),
        ("04", "Prove", ["Train + evaluate", "saved model"]),
        ("05", "Demonstrate", ["Prerecorded video", "inference"]),
    ]
    sx, sw, gap = 67, 132, 13
    for i, (number, title, body) in enumerate(stages):
        xx = sx + i * (sw + gap)
        rounded(xx, 317, sw, 96, 8, WHITE, WHITE)
        txt(xx + 11, 393, number, 7.5, "Segoe-Bold", TEAL)
        txt(xx + 11, 370, title, 12, "Segoe-Bold", NAVY)
        paragraph(body, xx + 11, 348, 8.3, 12, MUTED)
        if i < 4:
            line([(xx + sw + 2, 365), (xx + sw + gap - 4, 365)],
                 colors.HexColor("#82DADB"), 1.4)
            arrowhead(xx + sw + gap - 4, 365, "right", colors.HexColor("#82DADB"))
    txt(68, 300, "The arrows indicate lineage through frozen data and saved artifacts, not live database joins.",
        8.1, "Segoe", colors.HexColor("#CBDEE8"))

    rounded(50, 221, W - 100, 50, 9, PALE_TEAL, colors.HexColor("#B7DCDD"))
    txt(64, 252, "MODEL BOUNDARY", 8.4, "Segoe-Bold", TEAL)
    paragraph([
        "One persistent FiftyOne working dataset, backed by MongoDB, owns the samples, tags, and annotation/prediction fields.",
        "Logical boxes in this ERD may be embedded values, configuration entries, or versioned files; no SQL tables are implied."
    ], 64, 237, 8.8, 12.4, INK)

    txt(50, 198, "HOW TO READ THE DIAGRAMS", 8.8, "Segoe-Bold", NAVY)
    txt(50, 178, "1 = exactly one    0..* = zero or many    1..* = one or many", 8.7, "Segoe", INK)
    txt(50, 160, "PK and FK denote logical identity and lineage, not relational constraints.", 8.7, "Segoe", INK)
    txt(50, 142, "Arrows point from parent or input to child or produced artifact.", 8.7, "Segoe", INK)
    txt(50, 113, "02  Dataset & annotation   03  Export & training   04  Evaluation   05  Video", 8.7,
        "Segoe-Bold", TEAL)
    txt(50, 92, "06  Data invariants        07  Storage realization", 8.7, "Segoe-Bold", TEAL)
    txt(50, 67, "Source: Nazar Vision project brief, especially pp. 5-16 and 25-27.", 7.9,
        "Segoe", MUTED)
    footer(1)
    C.showPage()


def dataset_page():
    page_header("01 / DATASET", "Dataset and annotation", 
                "Source provenance and review state live within the persistent FiftyOne working dataset.", 2)
    # Connectors are drawn first, so their paths terminate cleanly at card borders.
    relation_h(X1 + CARD_W, X2, YT + 90, "supplies")
    relation_h(X2 + CARD_W, X3, YT + 90, "carries")
    relation_h(X1 + CARD_W, X2, YB + 90, "checkpoints")
    relation_elbow([(X1 + CARD_W, YB + 139), (286, YB + 139),
                    (286, 269), (420, 269), (420, YT)], "contains",
                   (260, YB + 144), (425, 274))
    draw_entity(X1, YT, "SOURCE_DATASET")
    draw_entity(X2, YT, "MEDIA_SAMPLE")
    draw_entity(X3, YT, "ANNOTATION_BOX")
    draw_entity(X1, YB, "WORKING_DATASET")
    draw_entity(X2, YB, "DATASET_CHECKPOINT", GOLD)
    rounded(X3, YB, CARD_W, CARD_H, 8, PALE_TEAL, colors.HexColor("#B7DCDD"))
    txt(X3 + 14, YB + CARD_H - 25, "Inside one FiftyOne sample", 10.5, "Segoe-Bold", NAVY)
    paragraph([
        "ground_truth_source",
        "  imported, immutable reference",
        "ground_truth_reviewed",
        "  editable review copy",
        "ground_truth_canonical",
        "  derived on request / export",
        "sample.tags",
        "  train, val, test, or excluded"
    ], X3 + 14, YB + CARD_H - 50, 8.5, 16, INK)
    C.showPage()


def export_page():
    page_header("02 / LINEAGE", "Mapping, export and training",
                "The frozen export records which checkpoint and class mapping produced each training input.", 3)
    relation_h(X1 + CARD_W, X2, YT + 90, "defines", "1..*")
    relation_h(X1 + CARD_W, X2, YB + 90, "precedes")
    relation_h(X2 + CARD_W, X3, YB + 90, "supplies")
    relation_v(X3 + CARD_W / 2, YB + CARD_H, YT, "saves")
    relation_elbow([(X1 + 103, YT), (X1 + 103, 270), (X2 + 102, 270),
                    (X2 + 102, YB + CARD_H)], "configures",
                   (X1 + 108, 273), (X2 + 110, 258))
    draw_entity(X1, YT, "CLASS_MAPPING", NAVY_2)
    draw_entity(X2, YT, "LABEL_MAPPING_ENTRY", NAVY_2)
    draw_entity(X3, YT, "MODEL_ARTIFACT", GOLD)
    draw_entity(X1, YB, "DATASET_CHECKPOINT", GOLD)
    draw_entity(X2, YB, "EXPORT_SNAPSHOT", GOLD)
    draw_entity(X3, YB, "TRAINING_RUN", GOLD)
    C.showPage()


def evaluation_page():
    page_header("03 / EVALUATION", "Model evaluation and predictions",
                "Each evaluation chooses one saved weight file and one frozen export; its predictions stay isolated by run.", 4)
    relation_h(X1 + CARD_W, X2, YT + 90, "evaluates on")
    relation_h(X2 + CARD_W, X3, YT + 90, "produces")
    relation_v(X2 + CARD_W / 2, YT, YB + CARD_H, "reports")
    relation_v(X3 + CARD_W / 2, YB + CARD_H, YT, "receives")
    relation_elbow([(X1 + CARD_W, YB + 139), (286, YB + 139),
                    (286, YT + 45), (X2, YT + 45)], "evaluates",
                   (260, YB + 143), (292, YT + 50))
    draw_entity(X1, YT, "EXPORT_SNAPSHOT", GOLD)
    draw_entity(X2, YT, "EVALUATION_RUN", NAVY_2)
    draw_entity(X3, YT, "IMAGE_PREDICTION")
    draw_entity(X1, YB, "MODEL_ARTIFACT", GOLD)
    draw_entity(X2, YB, "METRIC_RESULT", GOLD)
    draw_entity(X3, YB, "MEDIA_SAMPLE")
    C.showPage()


def video_page():
    page_header("04 / INFERENCE", "Prerecorded video inference",
                "A saved weight file runs on a video or ordered image sequence and produces frame-level detections.", 5)
    relation_h(X1 + CARD_W, X2, YT + 90, "feeds")
    relation_h(X2 + CARD_W, X3, YT + 90, "emits")
    relation_elbow([(X1 + CARD_W, YB + 139), (286, YB + 139),
                    (286, YT + 45), (X2, YT + 45)], "runs",
                   (260, YB + 143), (292, YT + 50))
    draw_entity(X1, YT, "VIDEO_SOURCE", NAVY_2)
    draw_entity(X2, YT, "VIDEO_INFERENCE_RUN", GOLD)
    draw_entity(X3, YT, "FRAME_DETECTION", GOLD)
    draw_entity(X1, YB, "MODEL_ARTIFACT", GOLD)
    rounded(X2, YB, CARD_W * 2 + 63, CARD_H, 8, PALE_GOLD,
            colors.HexColor("#EAD7B9"))
    txt(X2 + 16, YB + CARD_H - 27, "Core workflow boundary", 11, "Segoe-Bold", NAVY)
    paragraph([
        "FRAME_DETECTION records frame index, time, label, confidence, and box.",
        "It does not create a track identity. Tracking, alerts, live camera feeds,",
        "and camera integration remain optional later extensions.",
        "A processed video may correctly have zero detections. Source video",
        "and annotated outputs remain files referenced by the run manifest."
    ], X2 + 16, YB + CARD_H - 51, 9.1, 19.2, INK)
    txt(X2 + 16, YB + 18, "Project brief: p. 15; optional extensions pp. 17, 20-24.",
        7.7, "Segoe", MUTED)
    C.showPage()


def rule_card(x, y, number, title, body, source):
    rounded(x, y, 357, 68, 8, WHITE, BORDER)
    rounded(x + 11, y + 34, 29, 24, 5, TEAL, TEAL)
    txt(x + 25.5, y + 42, f"{number:02d}", 8.6, "Segoe-Bold", WHITE, "center")
    txt(x + 50, y + 47, title, 9.4, "Segoe-Bold", NAVY)
    txt(x + 50, y + 30, body[0], 8.1, "Segoe", INK)
    txt(x + 50, y + 18, body[1], 8.1, "Segoe", INK)
    txt(x + 345, y + 7, source, 6.8, "Segoe", MUTED, "right")


def rules_page():
    page_header("05 / DATA QUALITY", "Data invariants and validation gates",
                "These conditions make the logical model useful for reproducible training and honest evaluation.", 6)
    rows = [
        (1, "Preserve originals", ["Source images and imported boxes remain immutable.",
             "Reviewed boxes are a separate editable field."], "Brief pp. 7-10"),
        (2, "Persist the working dataset", ["FiftyOne dataset.persistent is true; reopened state",
             "retains boxes, tags, canonical labels, and metadata."], "Brief pp. 7, 12-13"),
        (3, "Assign one effective split", ["Exactly one train, val, test, or excluded tag applies",
             "at export; conflicting or missing tags block export."], "Brief pp. 9, 12"),
        (4, "Derive canonical labels", ["Generate canonical from reviewed boxes and mapping.",
             "Unknown reviewed labels cause an explicit error."], "Brief pp. 10-11"),
        (5, "Retain background images", ["Mapping a non-target label to null removes its box,",
             "not the image or its valid split assignment."], "Brief pp. 6, 10-11"),
        (6, "Validate export boxes", ["Require expected class, finite normalized coordinates,",
             "positive size, and bounds within the image."], "Brief p. 12"),
        (7, "Investigate leakage", ["Flag duplicate and related imagery across splits;",
             "record unresolved sequence or augmentation risks."], "Brief pp. 6, 12"),
        (8, "Bind recoverable inputs", ["Checkpoint before export; save mapping, split manifest,",
             "settings, weights, and tested image-path recovery."], "Brief pp. 12-14, 26"),
        (9, "Isolate predictions", ["Use a unique FiftyOne prediction field per evaluation;",
             "never overwrite any ground-truth field."], "Brief pp. 14-15"),
        (10, "Keep final test independent", ["Use train/validation for development choices; record",
              "split, thresholds, metric definitions, and model version."], "Brief pp. 14-15, 26"),
    ]
    for i, (number, title, body, source) in enumerate(rows):
        col = i // 5
        row = i % 5
        x = 50 if col == 0 else 435
        y = 401 - row * 76
        rule_card(x, y, number, title, body, source)
    C.showPage()


def storage_row(y, concern, realization, consequence, height=53):
    rounded(50, y, W - 100, height, 6, WHITE, BORDER)
    txt(62, y + height - 18, concern, 9.0, "Segoe-Bold", NAVY)
    txt(240, y + height - 18, realization[0], 8.5, "Segoe", INK)
    txt(240, y + height - 31, realization[1], 8.5, "Segoe", INK)
    txt(542, y + height - 18, consequence[0], 8.2, "Segoe", MUTED)
    txt(542, y + height - 31, consequence[1], 8.2, "Segoe", MUTED)


def storage_page():
    page_header("06 / IMPLEMENTATION", "Logical-to-physical storage mapping",
                "Logical IDs support traceability; storage uses FiftyOne/MongoDB, configuration, and versioned artifacts.", 7)
    txt(62, 469, "LOGICAL CONCERN", 7.9, "Segoe-Bold", TEAL)
    txt(240, 469, "PHYSICAL REALIZATION", 7.9, "Segoe-Bold", TEAL)
    txt(542, 469, "DESIGN CONSEQUENCE", 7.9, "Segoe-Bold", TEAL)
    storage_row(403, "Source image + provenance",
                ["Read-only image path on FiftyOne sample;", "source/import manifest and metadata."],
                ["MongoDB backup omits image bytes;", "restore needs files or path remap."])
    storage_row(343, "Working annotations + tags",
                ["One persistent FiftyOne dataset; three", "ground-truth fields and sample.tags."],
                ["Review state has one authoritative", "home in the working dataset."])
    storage_row(283, "Class mapping",
                ["Versioned project configuration file;", "hash and entries captured at export."],
                ["Every export is tied to the exact", "label transformation used."])
    storage_row(223, "Checkpoint + YOLO export",
                ["MongoDB backup and image manifest;", "frozen images/labels, data.yaml, splits."],
                ["A run remains reproducible after", "later FiftyOne review edits."])
    storage_row(163, "Training + image evaluation",
                ["Ultralytics run/weight files; unique", "FiftyOne prediction field per run."],
                ["Predictions can be reviewed beside", "ground truth without overwriting it."])
    storage_row(103, "Video inference",
                ["Source video/frames, annotated output,", "optional detections JSON/CSV."],
                ["The core demo uses saved weights", "and needs no tracking identity."])
    rounded(50, 62, W - 100, 31, 6, PALE_TEAL, colors.HexColor("#B7DCDD"))
    txt(61, 75, "Design status: names for IDs, hashes and manifests are proposed metadata; reconcile them with the mentor's existing codebase.",
        8.1, "Segoe", INK)
    C.showPage()


overview()
dataset_page()
export_page()
evaluation_page()
video_page()
rules_page()
storage_page()
C.save()
print(OUT)
