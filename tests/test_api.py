import pytest
from fastapi.testclient import TestClient

from mitra import api
from mitra.seed import CitizenStore

client = TestClient(api.app)


def test_health_reports_kb_without_conflicts():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["documents"] > 50 and body["conflicts"] == 0


def test_schemes_lists_the_three_supported_schemes():
    assert {s["scheme_id"] for s in client.get("/schemes").json()} == {"SCH-FRM-01", "SCH-FRM-02", "SCH-PEN-01"}


def test_eligibility_for_a_seed_citizen_is_date_aware():
    def outcome(as_of):
        response = client.post("/eligibility", json={"scheme_id": "SCH-PEN-01", "citizen_id": "C1021", "as_of": as_of})
        assert response.status_code == 200
        return response.json()["outcome"]

    assert outcome("2026-11-21") == "meets_criteria"
    assert outcome("2026-09-09") == "does_not_meet"


def test_eligibility_accepts_an_inline_profile():
    response = client.post("/eligibility", json={
        "scheme_id": "SCH-FRM-01", "as_of": "2026-11-21",
        "profile": {"occupation": "farmer", "land_holding_acres": 3, "residence_type": "rural"}})
    assert response.json()["outcome"] == "meets_criteria"
    assert "makes the final decision" in response.json()["disclaimer"]


@pytest.mark.parametrize("payload, status", [
    ({"scheme_id": "SCH-XXX-99", "profile": {"age": 70}}, 404),
    ({"scheme_id": "SCH-PEN-01", "citizen_id": "C9999"}, 404),
    ({"scheme_id": "SCH-PEN-01"}, 422),
    ({"scheme_id": "SCH-PEN-01", "profile": {"annual_household_income": "lots"}}, 422),
])
def test_eligibility_errors(payload, status):
    assert client.post("/eligibility", json=payload).status_code == status


def test_eligibility_refuses_a_citizen_without_consent(monkeypatch):
    record = {"citizen_id": "CX", "consent_given": "N", "date_of_birth": "1950-01-01"}
    monkeypatch.setattr(api.assistant(), "citizens", CitizenStore({"CX": record}))
    assert client.post("/eligibility", json={"scheme_id": "SCH-PEN-01", "citizen_id": "CX"}).status_code == 403


def test_chat_returns_a_structured_answer():
    body = client.post("/chat", json={"message": "Someone asked me for my OTP", "as_of": "2026-11-21"}).json()
    assert body["intent"] == "fraud" and body["escalate_to"] == "fraud_desk" and "POL-FEE-01" in body["citations"]


def test_chat_validates_input():
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={"message": "hi", "language": "fr"}).status_code == 422
    bad_profile = {"message": "Am I eligible for pension?", "profile": {"age": "old"}}
    assert client.post("/chat", json=bad_profile).status_code == 422
