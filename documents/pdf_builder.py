"""Renders a full tailored resume and cover letter as ATS-friendly PDFs.

"ATS-friendly" here means: single column, standard fonts, real selectable
text (no images/text-boxes), no tables, and a strict linear reading order --
the layout an applicant-tracking-system parser is most likely to extract
correctly. This intentionally does not attempt a visually elaborate design;
a plain, well-structured document parses more reliably than a decorated one.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from llm.full_document_tailor import FullCoverLetterResult, TailoredExperienceEntry

_MARGIN = 0.75 * inch

_styles = getSampleStyleSheet()

_NAME_STYLE = ParagraphStyle(
    "Name", parent=_styles["Title"], fontName="Helvetica-Bold", fontSize=18,
    leading=22, spaceAfter=2, alignment=0,
)
_CONTACT_STYLE = ParagraphStyle(
    "Contact", parent=_styles["Normal"], fontName="Helvetica", fontSize=9.5,
    leading=13, spaceAfter=10, textColor="#333333",
)
_SECTION_HEADING_STYLE = ParagraphStyle(
    "SectionHeading", parent=_styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=11.5, leading=14, spaceBefore=12, spaceAfter=4,
    textColor="#000000", borderPadding=0,
)
_ROLE_TITLE_STYLE = ParagraphStyle(
    "RoleTitle", parent=_styles["Normal"], fontName="Helvetica-Bold",
    fontSize=10.5, leading=13, spaceBefore=6, spaceAfter=1,
)
_ROLE_META_STYLE = ParagraphStyle(
    "RoleMeta", parent=_styles["Normal"], fontName="Helvetica-Oblique",
    fontSize=9.5, leading=12, spaceAfter=3, textColor="#333333",
)
_BODY_STYLE = ParagraphStyle(
    "Body", parent=_styles["Normal"], fontName="Helvetica", fontSize=10,
    leading=13.5, spaceAfter=6,
)
_BULLET_STYLE = ParagraphStyle(
    "Bullet", parent=_styles["Normal"], fontName="Helvetica", fontSize=10,
    leading=13, spaceAfter=3,
)
_LETTER_META_STYLE = ParagraphStyle(
    "LetterMeta", parent=_styles["Normal"], fontName="Helvetica", fontSize=10,
    leading=13, spaceAfter=2,
)

# Job.company is stored as the lowercase slug used in board URLs (e.g.
# "gitlab", from job-boards.greenhouse.io/gitlab) -- fine for internal
# matching, but wrong to print verbatim in a cover letter greeting. Real
# branding for the current pilot boards; anything else falls back to
# .title(), which is imperfect for names like "GitLab" but far better than
# an all-lowercase company name in a business letter.
_COMPANY_DISPLAY_NAMES = {
    "gitlab": "GitLab",
    "discord": "Discord",
    "fictiv": "Fictiv",
    "wheelhouse": "Wheelhouse",
    "affinipay": "AffiniPay",
}


def _display_company_name(company: str) -> str:
    return _COMPANY_DISPLAY_NAMES.get(company.lower(), company.title())


_SKILL_CATEGORY_LABELS = {
    "llms_genai": "LLMs & GenAI",
    "rag_pipelines": "RAG Pipelines",
    "agentic_ai": "Agentic AI",
    "applied_ml": "Applied ML",
    "nlp": "NLP",
    "ai_augmented_dev": "AI-Augmented Development",
    "ai_ml_engineering": "AI/ML Engineering",
    "ai_augmented_development": "AI-Augmented Development",
    "enterprise_architecture": "Enterprise Architecture",
    "engineering_leadership": "Engineering Leadership",
}


def _date_range(start: str | None, end: str | None) -> str:
    if not start and not end:
        return ""
    return f"{start or '?'} – {end or 'Present'}"


def _section_heading(text: str) -> Paragraph:
    return Paragraph(text.upper(), _SECTION_HEADING_STYLE)


def _bullet_list(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, _BULLET_STYLE), leftIndent=0) for item in items],
        bulletType="bullet",
        start="•",
        leftIndent=14,
        bulletFontSize=9,
        spaceBefore=2,
        spaceAfter=4,
    )


def build_resume_pdf(
    profile: dict,
    tailored_summary: str,
    tailored_experience: list[TailoredExperienceEntry],
    output_path: Path,
) -> Path:
    """Render a complete resume PDF: contact header, tailored summary,
    technical skills, every role with every achievement (reordered/reworded,
    never dropped), AI/ML projects, education, and certifications."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        title=f"{profile.get('personal_info', {}).get('full_name', 'Resume')} - Resume",
    )

    story = []
    personal = profile.get("personal_info", {})

    story.append(Paragraph(personal.get("full_name", ""), _NAME_STYLE))
    contact_parts = [
        p
        for p in [
            personal.get("email"),
            personal.get("phone"),
            personal.get("location"),
            personal.get("linkedin"),
        ]
        if p
    ]
    story.append(Paragraph(" &nbsp;|&nbsp; ".join(contact_parts), _CONTACT_STYLE))

    if tailored_summary:
        story.append(_section_heading("Professional Summary"))
        story.append(Paragraph(tailored_summary, _BODY_STYLE))

    technical_skills = profile.get("technical_skills", {})
    core_ai = profile.get("core_ai_competencies", {})
    if technical_skills or core_ai:
        story.append(_section_heading("Technical Skills"))
        # core_ai_competencies and technical_skills both contain an
        # "ai_augmented_dev(elopment)" category with different item lists --
        # merge by DISPLAY LABEL (not raw key) so they render as one
        # combined line instead of the same heading appearing twice.
        merged: dict[str, list[str]] = {}
        for category, items in {**core_ai, **technical_skills}.items():
            if not items:
                continue
            label = _SKILL_CATEGORY_LABELS.get(category, category.replace("_", " ").title())
            bucket = merged.setdefault(label, [])
            for item in items:
                if item not in bucket:
                    bucket.append(item)
        for label, items in merged.items():
            story.append(Paragraph(f"<b>{label}:</b> {', '.join(items)}", _BODY_STYLE))

    if tailored_experience:
        story.append(_section_heading("Professional Experience"))
        for role in tailored_experience:
            story.append(Paragraph(f"{role.title} — {role.company}", _ROLE_TITLE_STYLE))
            meta = " | ".join(
                p
                for p in [role.location, _date_range(role.start_date, role.end_date)]
                if p
            )
            if meta:
                story.append(Paragraph(meta, _ROLE_META_STYLE))
            if role.achievements:
                story.append(_bullet_list(role.achievements))

    ai_projects = profile.get("ai_ml_projects", [])
    if ai_projects:
        story.append(_section_heading("AI/ML Projects"))
        for project in ai_projects:
            name = project.get("name", "")
            program = project.get("program")
            title_line = name if not program else f"{name} ({program})"
            story.append(Paragraph(title_line, _ROLE_TITLE_STYLE))
            description = project.get("description", "")
            if description:
                story.append(Paragraph(description, _BODY_STYLE))
            tools = project.get("skills_tools", [])
            if tools:
                story.append(Paragraph(f"<i>{', '.join(tools)}</i>", _ROLE_META_STYLE))

    education = profile.get("education", [])
    if education:
        story.append(_section_heading("Education"))
        for entry in education:
            program = entry.get("program", "")
            institution = entry.get("institution", "")
            story.append(Paragraph(f"{program} — {institution}", _ROLE_TITLE_STYLE))
            status = entry.get("status")
            date_line = status or _date_range(entry.get("start_date"), entry.get("end_date"))
            if date_line:
                story.append(Paragraph(date_line, _ROLE_META_STYLE))

    certifications = profile.get("certifications", [])
    if certifications:
        story.append(_section_heading("Certifications"))
        cert_lines = [
            f"{c.get('name', '')} — {c.get('issuer', '')} ({c.get('year', '')})"
            for c in certifications
        ]
        story.append(_bullet_list(cert_lines))

    doc.build(story)
    return output_path


def build_cover_letter_pdf(
    profile: dict,
    company: str,
    role_title: str,
    letter: FullCoverLetterResult,
    output_path: Path,
) -> Path:
    """Render a complete business-letter-format cover letter PDF: contact
    header, date, greeting, opening/body/closing paragraphs, signature."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        title=f"Cover Letter - {role_title} at {_display_company_name(company)}",
    )

    personal = profile.get("personal_info", {})
    story = []
    display_company = _display_company_name(company)

    story.append(Paragraph(personal.get("full_name", ""), _NAME_STYLE))
    contact_parts = [
        p
        for p in [personal.get("email"), personal.get("phone"), personal.get("location")]
        if p
    ]
    story.append(Paragraph(" &nbsp;|&nbsp; ".join(contact_parts), _CONTACT_STYLE))
    story.append(Spacer(1, 12))

    from datetime import date

    story.append(Paragraph(date.today().strftime("%B %d, %Y"), _LETTER_META_STYLE))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Hiring Team, {display_company}", _LETTER_META_STYLE))
    story.append(Paragraph(f"Re: {role_title}", _LETTER_META_STYLE))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Dear {display_company} Hiring Team,", _BODY_STYLE))
    story.append(Paragraph(letter.opening_paragraph, _BODY_STYLE))
    for paragraph in letter.body_paragraphs:
        story.append(Paragraph(paragraph, _BODY_STYLE))
    story.append(Paragraph(letter.closing_paragraph, _BODY_STYLE))

    story.append(Spacer(1, 16))
    story.append(Paragraph("Sincerely,", _BODY_STYLE))
    story.append(Paragraph(personal.get("full_name", ""), _BODY_STYLE))

    doc.build(story)
    return output_path
