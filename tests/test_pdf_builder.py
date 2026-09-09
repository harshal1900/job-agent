from __future__ import annotations

from pypdf import PdfReader

from documents.pdf_builder import (
    _display_company_name,
    build_cover_letter_pdf,
    build_resume_pdf,
)
from llm.full_document_tailor import FullCoverLetterResult, TailoredExperienceEntry

PROFILE = {
    "personal_info": {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-1234",
        "location": "Austin, TX",
        "linkedin": "linkedin.com/in/janedoe",
    },
    "technical_skills": {"enterprise_architecture": ["Python", "AWS"]},
    "core_ai_competencies": {"llms_genai": ["Prompt engineering"]},
    "ai_ml_projects": [
        {
            "name": "Widget Classifier",
            "description": "Built a classifier for widgets.",
            "skills_tools": ["scikit-learn"],
        }
    ],
    "education": [
        {"program": "B.S. Computer Science", "institution": "State University", "start_date": "2010", "end_date": "2014"}
    ],
    "certifications": [{"name": "AWS Certified", "issuer": "AWS", "year": 2020}],
}

EXPERIENCE = [
    TailoredExperienceEntry(
        title="Backend Engineer",
        company="Initech",
        location="Remote",
        start_date="2020-01",
        end_date="Present",
        achievements=["Built a Python service", "Mentored two engineers"],
    )
]


def _extract_text(path) -> str:
    reader = PdfReader(str(path))
    return "".join(page.extract_text() for page in reader.pages)


def test_build_resume_pdf_includes_every_section(tmp_path):
    output = tmp_path / "resume.pdf"
    build_resume_pdf(PROFILE, "Tailored summary paragraph.", EXPERIENCE, output)

    assert output.exists()
    text = _extract_text(output)
    assert "Jane Doe" in text
    assert "Tailored summary paragraph." in text
    assert "Backend Engineer" in text and "Initech" in text
    assert "Built a Python service" in text
    assert "Mentored two engineers" in text
    assert "Widget Classifier" in text
    assert "State University" in text
    assert "AWS Certified" in text


def test_build_resume_pdf_merges_duplicate_skill_category_labels(tmp_path):
    # core_ai_competencies and technical_skills can both map to the same
    # display label (e.g. "AI-Augmented Development") -- must render once,
    # combined, not as two separate lines with the same heading.
    profile = {
        **PROFILE,
        "core_ai_competencies": {"ai_augmented_dev": ["Copilot"]},
        "technical_skills": {"ai_augmented_development": ["Devin"]},
    }
    output = tmp_path / "resume.pdf"
    build_resume_pdf(profile, "Summary.", EXPERIENCE, output)

    text = _extract_text(output)
    assert text.count("AI-AUGMENTED DEVELOPMENT") + text.count("AI-Augmented Development") <= 1
    assert "Copilot" in text and "Devin" in text


def test_build_cover_letter_pdf_has_business_letter_structure(tmp_path):
    letter = FullCoverLetterResult(
        opening_paragraph="I am excited to apply to Acme for the Backend Engineer role.",
        body_paragraphs=["At Initech I built a Python service."],
        closing_paragraph="Thank you for your consideration.",
    )
    output = tmp_path / "cover_letter.pdf"
    build_cover_letter_pdf(PROFILE, "gitlab", "Backend Engineer", letter, output)

    assert output.exists()
    text = _extract_text(output)
    assert "Jane Doe" in text
    # Company slug must be display-cased, not printed as the raw lowercase
    # board-URL slug stored on Job.company.
    assert "GitLab" in text
    assert "gitlab Hiring Team" not in text
    assert letter.opening_paragraph in text
    assert letter.closing_paragraph in text
    assert "Sincerely" in text


def test_display_company_name_known_and_unknown():
    assert _display_company_name("gitlab") == "GitLab"
    assert _display_company_name("discord") == "Discord"
    assert _display_company_name("some_new_co") == "Some_New_Co"
