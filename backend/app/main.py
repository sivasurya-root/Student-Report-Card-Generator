from __future__ import annotations

from io import BytesIO
from typing import Any
import hashlib
import os
import re

import pandas as pd
import qrcode
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

app = FastAPI(title="Student Report Card Generator API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COLLEGE = "SARDAR RAJA COLLEGE OF ENGINEERING"
ADDRESS = "Raja Nagar, Alangulam, Tenkasi"
DEFAULT_DEPARTMENT = "B.Tech"
DEFAULT_PROGRAMME = "(Artificial Intelligence & Data Science)"
DEFAULT_EXAM = "Continuous Assessment Test - 1 Examination"
REGULATION_DEFAULT = "—"

DATA: dict[str, Any] = {
    "students": pd.DataFrame(),
    "subjects": pd.DataFrame(),
    "filename": None,
}

MARK_COLUMNS = [f"Subject {i} Mark" for i in range(1, 6)]
NAME_COLUMNS = [f"Subject {i} Name" for i in range(1, 6)]


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def excel_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d-%m-%Y")
    return value


def register_key(value: Any) -> str:
    value = excel_scalar(value)
    return str(value).strip()


def grade_for_percent(percent: float) -> tuple[str, int, str, str]:
    if percent >= 91:
        return "O", 10, "Pass", "Outstanding"
    if percent >= 81:
        return "A+", 9, "Pass", "Excellent"
    if percent >= 71:
        return "A", 8, "Pass", "Very Good"
    if percent >= 61:
        return "B+", 7, "Pass", "Good"
    if percent >= 51:
        return "B", 6, "Pass", "Above Average"
    if percent >= 45:
        return "C", 5, "Pass", "Average"
    return "U / RA", 0, "Fail (Arrear)", "Reappearance"


def load_workbook(content: bytes) -> None:
    try:
        # Final workbook: title rows 1-3, real column headers are on row 4.
        students = pd.read_excel(BytesIO(content), sheet_name="Student_Data", header=3)
        # Subject_Config: title row 1, real column headers are on row 2.
        subjects = pd.read_excel(BytesIO(content), sheet_name="Subject_Config", header=1)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Excel must contain Student_Data and Subject_Config sheets: {exc}",
        ) from exc

    students = clean_columns(students)
    subjects = clean_columns(subjects)

    required_student = ["Register Number", "Student Name", *MARK_COLUMNS, *NAME_COLUMNS]
    missing = [c for c in required_student if c not in students.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Student_Data missing column(s): {', '.join(missing)}")

    required_subject = ["Subject No.", "Subject Code", "Subject Name", "Max Mark", "Pass Mark", "Report Order"]
    missing = [c for c in required_subject if c not in subjects.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Subject_Config missing column(s): {', '.join(missing)}")

    # Keep only actual student rows.
    students = students[students["Student Name"].fillna("").astype(str).str.strip() != ""].copy()
    if students.empty:
        raise HTTPException(status_code=400, detail="Student_Data has no student records.")

    # Normalize five mark columns to numbers; blanks remain missing.
    for col in MARK_COLUMNS:
        students[col] = pd.to_numeric(students[col], errors="coerce")

    subjects["Max Mark"] = pd.to_numeric(subjects["Max Mark"], errors="coerce").fillna(100)
    subjects["Report Order"] = pd.to_numeric(subjects["Report Order"], errors="coerce")
    subjects = subjects.dropna(subset=["Subject Code", "Subject Name"]).copy()
    subjects = subjects.sort_values(["Report Order", "Subject No."]).reset_index(drop=True)

    DATA.update({"students": students, "subjects": subjects})


def subject_config_by_order(index: int) -> dict[str, Any]:
    if index >= len(DATA["subjects"]):
        return {"code": f"SUB{index + 1:03d}", "max_mark": 100}
    row = DATA["subjects"].iloc[index]
    return {
        "code": str(excel_scalar(row["Subject Code"])),
        "max_mark": float(excel_scalar(row["Max Mark"]) or 100),
    }


def report_id_for(register_no: str) -> str:
    raw = f"SREC|CAT1|{register_no.strip()}".encode()
    return f"SREC-CAT1-{hashlib.sha1(raw).hexdigest()[:8].upper()}"


def serialize_student(row: pd.Series) -> dict[str, Any]:
    reg = register_key(row["Register Number"])
    student = {str(k): excel_scalar(v) for k, v in row.to_dict().items()}

    subjects: list[dict[str, Any]] = []
    total = 0.0
    max_total = 0.0
    grade_points: list[int] = []
    arrears = 0

    for i, (mark_col, name_col) in enumerate(zip(MARK_COLUMNS, NAME_COLUMNS)):
        mark_value = row.get(mark_col, None)
        subject_name = str(excel_scalar(row.get(name_col, ""))).strip()
        if pd.isna(mark_value) or str(mark_value).strip() == "" or not subject_name:
            continue
        mark = float(mark_value)
        cfg = subject_config_by_order(i)
        max_mark = cfg["max_mark"] or 100.0
        percent = (mark / max_mark * 100) if max_mark else 0.0
        grade, gp, status, description = grade_for_percent(percent)
        total += mark
        max_total += max_mark
        grade_points.append(gp)
        if status != "Pass":
            arrears += 1
        subjects.append({
            "code": cfg["code"],
            "name": subject_name,
            "mark": round(mark, 2),
            "max_mark": round(max_mark, 2),
            "percentage": round(percent, 2),
            "grade": grade,
            "grade_point": gp,
            "status": status,
            "description": description,
        })

    overall_percentage = (total / max_total * 100) if max_total else 0.0
    overall_grade, _, _, _ = grade_for_percent(overall_percentage)
    average_gp = round(sum(grade_points) / len(grade_points), 2) if grade_points else 0.0
    result = "FAIL (ARREAR)" if arrears else "PASS"

    department = str(student.get("Department", "") or DEFAULT_DEPARTMENT)
    programme = str(student.get("Programme", "") or DEFAULT_PROGRAMME)
    exam = str(student.get("Exam Name", "") or DEFAULT_EXAM)
    attendance = student.get("Attendance %", "")
    photo = student.get("Student Photo", "")

    return {
        "student": student,
        "subjects": subjects,
        "meta": {
            "college": COLLEGE,
            "address": ADDRESS,
            "department": department,
            "programme": programme,
            "exam": exam,
            "report_id": report_id_for(reg),
            "regulation": str(student.get("Regulation", REGULATION_DEFAULT) or REGULATION_DEFAULT),
            "attendance": attendance,
            "student_photo": photo,
        },
        "summary": {
            "total_marks": round(total, 2),
            "max_marks": round(max_total, 2),
            "percentage": round(overall_percentage, 2),
            "average_grade_point": average_gp,
            "overall_grade": overall_grade,
            "result": result,
            "arrear_count": arrears,
        },
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_excel(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel .xlsx or .xls file.")
    content = await file.read()
    load_workbook(content)
    DATA["filename"] = file.filename
    return {
        "message": "Dataset loaded successfully",
        "filename": file.filename,
        "students": int(len(DATA["students"])),
        "subjects": int(len(DATA["subjects"])),
    }


@app.get("/api/students")
def search_students(query: str = "") -> list[dict[str, str]]:
    if DATA["students"].empty:
        return []
    df = DATA["students"]
    q = query.strip().lower()
    if q:
        names = df["Student Name"].astype(str).str.lower()
        regs = df["Register Number"].map(register_key).str.lower()
        df = df[names.str.contains(q, regex=False) | regs.str.contains(q, regex=False)]
    return [
        {
            "register_no": register_key(r["Register Number"]),
            "student_name": str(r["Student Name"]),
            "department": str(r.get("Department", DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT),
        }
        for _, r in df.head(50).iterrows()
    ]


@app.get("/api/students/{register_no}")
def get_student(register_no: str) -> dict[str, Any]:
    if DATA["students"].empty:
        raise HTTPException(status_code=404, detail="No dataset loaded.")
    key = register_no.strip()
    df = DATA["students"]
    matches = df[df["Register Number"].map(register_key) == key]
    if matches.empty:
        raise HTTPException(status_code=404, detail="Student not found.")
    return serialize_student(matches.iloc[0])


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "report"


def build_pdf(report: dict[str, Any]) -> bytes:
    out = BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="College", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=15, leading=18, textColor=colors.HexColor("#183B5F")))
    styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9, leading=12, textColor=colors.HexColor("#4E5D6C")))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=9.5, leading=12, textColor=colors.HexColor("#183B5F"), spaceBefore=7, spaceAfter=5, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8.0, leading=10))
    styles.add(ParagraphStyle(name="SmallBold", parent=styles["Small"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Title2", parent=styles["Heading2"], alignment=TA_CENTER, fontSize=10.5, leading=13, textColor=colors.HexColor("#183B5F"), spaceBefore=5, spaceAfter=6))

    student = report["student"]
    meta = report["meta"]
    summary = report["summary"]
    story: list[Any] = []

    logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png"))

    def draw_watermark(canvas, _doc):
        # Logo-only watermark: no diagonal college-name text, kept very light so all report data remains readable.
        if not os.path.exists(logo_path):
            return
        canvas.saveState()
        try:
            canvas.setFillAlpha(0.065)
        except AttributeError:
            pass
        size = 78 * mm
        canvas.drawImage(
            ImageReader(logo_path),
            (A4[0] - size) / 2,
            82 * mm,
            width=size,
            height=size,
            preserveAspectRatio=True,
            anchor='c',
            mask='auto',
        )
        canvas.restoreState()

    # Prominent but compact header logo. The watermark is separate and intentionally lighter.
    if os.path.exists(logo_path):
        header = Table(
            [[Image(logo_path, width=23 * mm, height=23 * mm),
              [Paragraph(meta["college"], styles["College"]),
               Paragraph(meta["address"], styles["Sub"]),
               Paragraph(f"{meta['department']} – {meta['programme']}", styles["Sub"])]]],
            colWidths=[27 * mm, 150 * mm],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header)
    else:
        story.append(Paragraph(meta["college"], styles["College"]))
        story.append(Paragraph(meta["address"], styles["Sub"]))
        story.append(Paragraph(f"{meta['department']} – {meta['programme']}", styles["Sub"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(meta["exam"].upper(), styles["Title2"]))

    qr_payload = f"{meta['report_id']}|{student.get('Student Name','')}|{summary['percentage']}%|{summary['result']}"
    qr = qrcode.make(qr_payload)
    qr_buf = BytesIO()
    qr.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    dob = student.get("Date of Birth", "") or "—"
    attendance = meta.get("attendance", "") or "—"
    details = [
        ["Student Name", student.get("Student Name", ""), "Register No", student.get("Register Number", "")],
        ["Department", meta["department"], "Programme", meta["programme"]],
        ["Semester", student.get("Semester", ""), "Section", student.get("Section", "")],
        ["Academic Year", student.get("Academic Year", ""), "Attendance", attendance],
        ["Date of Birth", dob, "Report ID", meta["report_id"]],
    ]
    detail_table = Table(
        [[Paragraph(str(a), styles["SmallBold"]), Paragraph(str(b), styles["Small"]), Paragraph(str(c), styles["SmallBold"]), Paragraph(str(d), styles["Small"])] for a, b, c, d in details],
        colWidths=[28 * mm, 60 * mm, 28 * mm, 48 * mm],
    )
    detail_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0D8")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F5F8")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F2F5F8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph("ACADEMIC PERFORMANCE", styles["Section"]))

    table_data = [["Course Code", "Course / Subject", "Max", "Marks", "%", "Grade", "GP", "Status"]]
    for s in report["subjects"]:
        table_data.append([
            s["code"], s["name"], f"{s['max_mark']:.0f}", f"{s['mark']:.0f}",
            f"{s['percentage']:.2f}", s["grade"], str(s["grade_point"]), s["status"],
        ])
    perf = Table(table_data, colWidths=[20 * mm, 54 * mm, 13 * mm, 16 * mm, 16 * mm, 15 * mm, 11 * mm, 28 * mm], repeatRows=1)
    perf.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD3DA")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4), ("LEFTPADDING", (0, 0), (-1, -1), 3.5), ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(perf)
    story.append(Spacer(1, 7))

    summary_rows = [
        ["Total Marks", f"{summary['total_marks']:.0f} / {summary['max_marks']:.0f}", "Percentage", f"{summary['percentage']:.2f}%"],
        ["Overall Grade", summary["overall_grade"], "Average Grade Point", f"{summary['average_grade_point']:.2f}"],
        ["Arrear Count", str(summary["arrear_count"]), "Result", summary["result"]],
    ]
    summary_table = Table([[Paragraph(a, styles["SmallBold"]), Paragraph(str(b), styles["Small"]), Paragraph(c, styles["SmallBold"]), Paragraph(str(d), styles["Small"])] for a, b, c, d in summary_rows], colWidths=[30 * mm, 40 * mm, 36 * mm, 45 * mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0D8")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F5F8")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F2F5F8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    verification = Table([[summary_table, Image(qr_buf, width=25 * mm, height=25 * mm)]], colWidths=[151 * mm, 25 * mm])
    verification.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(verification)
    story.append(Spacer(1, 10))

    remarks = str(student.get("Remarks", "") or "").strip()
    if remarks:
        story.append(Paragraph(f"<b>Remarks:</b> {remarks}", styles["Small"]))
        story.append(Spacer(1, 8))

    sign = Table([["Class Advisor", "Head of Department", "Principal"], ["\n\n____________________", "\n\n____________________", "\n\n____________________"]], colWidths=[58 * mm, 58 * mm, 58 * mm])
    sign.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
    story.append(sign)
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Report ID: {meta['report_id']} • Computer-generated academic report", styles["Sub"]))

    doc.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    out.seek(0)
    return out.read()


@app.get("/api/report/{register_no}")
def generate_report(register_no: str) -> StreamingResponse:
    report = get_student(register_no)
    pdf = build_pdf(report)
    filename = safe_filename(f"{report['student'].get('Student Name', 'Student')}_CAT1_Report.pdf")
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
