from __future__ import annotations

import json

import pytest

from llm.full_document_tailor import (
    DocumentStructureError,
    FullDocumentTailor,
)
from llm.resume_rewriter import HallucinationError

PROFILE = {
    "personal_info": {"full_name": "Jane Doe"},
    "professional_experience": [
        {
            "title": "Backend Engineer",
            "company": "Initech",
            "location": "Remote",
            "start_date": "2020-01",
            "end_date": "Present",
            "achievements": [
                "Built a Python service handling 10,000 requests per day",
                "Mentored two junior engineers",
            ],
        },
        {
            "title": "Junior Developer",
            "company": "Globex",
            "location": "Remote",
            "start_date": "2018-01",
            "end_date": "2019-12",
            "achievements": ["Wrote SQL migration scripts"],
        },
    ],
}


class FakeLLMClient:
    def __init__(self, reply: str):
        self.reply = reply
        self.last_max_tokens: int | None = None

    def chat(self, messages, temperature=0.2, max_tokens=1024):
        self.last_max_tokens = max_tokens
        return self.reply


def _resume_reply(experience):
    return json.dumps({"tailored_summary": "Grounded summary.", "experience": experience})


def test_tailor_resume_preserves_achievement_count_and_order():
    reply = _resume_reply(
        [
            {
                "index": 0,
                "achievements": [
                    "Mentored two junior engineers",
                    "Built a Python service handling 10,000 requests per day",
                ],
            },
            {"index": 1, "achievements": ["Wrote SQL migration scripts"]},
        ]
    )
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    result = tailor.tailor_resume(PROFILE, "Backend role", strict=True)

    assert result.unsupported_terms == []
    assert len(result.experience) == 2
    assert result.experience[0].company == "Initech"
    assert len(result.experience[0].achievements) == 2
    assert len(result.experience[1].achievements) == 1


def test_tailor_resume_falls_back_to_original_bullets_on_wrong_count():
    # Structural violation: role 0 should have 2 achievements, model
    # returned only 1 -- must fall back to the original bullets for that
    # role rather than silently shipping a resume missing an achievement.
    reply = _resume_reply(
        [
            {"index": 0, "achievements": ["Only one bullet"]},
            {"index": 1, "achievements": ["Wrote SQL migration scripts"]},
        ]
    )
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    result = tailor.tailor_resume(PROFILE, "Backend role", strict=True)

    assert result.experience[0].achievements == [
        "Built a Python service handling 10,000 requests per day",
        "Mentored two junior engineers",
    ]


def test_tailor_resume_falls_back_when_role_index_missing_entirely():
    reply = _resume_reply([{"index": 0, "achievements": ["Reworded bullet one", "Reworded bullet two"]}])
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    result = tailor.tailor_resume(PROFILE, "Backend role", strict=True)

    # role 1 got no entry at all -- falls back to its original achievement.
    assert result.experience[1].achievements == ["Wrote SQL migration scripts"]


def test_tailor_resume_raises_hallucination_error_on_unsupported_terms():
    reply = _resume_reply(
        [
            {
                "index": 0,
                "achievements": [
                    "Scaled Acmecorp's infra to 1,000,000 users",
                    "Mentored two junior engineers",
                ],
            },
            {"index": 1, "achievements": ["Wrote SQL migration scripts"]},
        ]
    )
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    with pytest.raises(HallucinationError):
        tailor.tailor_resume(PROFILE, "Backend role", strict=True)


def test_tailor_cover_letter_succeeds_when_grounded():
    reply = json.dumps(
        {
            "opening_paragraph": "I am excited to apply to Acme for the Backend Engineer role.",
            "body_paragraphs": [
                "At Initech I built a Python service handling 10,000 requests per day."
            ],
            "closing_paragraph": "Thank you for your consideration.",
        }
    )
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    result = tailor.tailor_cover_letter(PROFILE, "Acme", "Backend Engineer", "Backend role", strict=True)

    assert result.unsupported_terms == []
    assert "Initech" in result.full_text


def test_tailor_cover_letter_raises_structure_error_when_section_missing():
    reply = json.dumps(
        {
            "opening_paragraph": "",
            "body_paragraphs": [],
            "closing_paragraph": "Thank you.",
        }
    )
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    with pytest.raises(DocumentStructureError):
        tailor.tailor_cover_letter(PROFILE, "Acme", "Backend Engineer", "Backend role", strict=True)


def test_tailor_cover_letter_raises_hallucination_error_on_unsupported_terms():
    reply = json.dumps(
        {
            "opening_paragraph": "I am excited to apply to Acme for the Backend Engineer role.",
            "body_paragraphs": ["At Acmecorp I scaled infra to 1,000,000 users."],
            "closing_paragraph": "Thank you for your consideration.",
        }
    )
    tailor = FullDocumentTailor(llm_client=FakeLLMClient(reply))

    with pytest.raises(HallucinationError):
        tailor.tailor_cover_letter(PROFILE, "Acme", "Backend Engineer", "Backend role", strict=True)
