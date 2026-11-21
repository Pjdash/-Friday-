from datetime import date

import pytest

from mitra.eligibility import age_on, evaluate, normalize_profile
from mitra.schemes import fmt_value, inr

from conftest import TODAY


def outcome(kb, citizens, citizen_id, scheme_id, as_of=TODAY):
    return evaluate(scheme_id, citizens.get(citizen_id), kb, as_of).outcome


# ---- seed citizens ----------------------------------------------------------------------------

@pytest.mark.parametrize("citizen_id, scheme_id, as_of, expected", [
    # Pension: the cap rose from 1,20,000 to 1,50,000 on 2026-09-10 (CIR-2026-01).
    ("C1021", "SCH-PEN-01", date(2026, 11, 21), "meets_criteria"),    # 68 y, income 1,38,000
    ("C1021", "SCH-PEN-01", date(2026, 9, 9), "does_not_meet"),       # same person, day before the circular
    ("C1021", "SCH-PEN-01", date(2026, 9, 10), "meets_criteria"),
    ("C1027", "SCH-PEN-01", date(2026, 11, 21), "meets_criteria"),    # 75 y, income 62,000
    ("C1031", "SCH-PEN-01", date(2026, 11, 21), "does_not_meet"),     # 77 y but income 2,35,000
    ("C1024", "SCH-PEN-01", date(2026, 11, 21), "does_not_meet"),     # income fine, 30 y
    # Kisan Samriddhi: farmer, rural, household land <= 5.0 acres.
    ("C1019", "SCH-FRM-01", TODAY, "meets_criteria"),                 # 2.2 acres
    ("C1025", "SCH-FRM-01", TODAY, "meets_criteria"),                 # 3.8 acres
    ("C1023", "SCH-FRM-01", TODAY, "does_not_meet"),                  # 6.4 acres
    ("C1021", "SCH-FRM-01", TODAY, "does_not_meet"),                  # not a farmer
    # Krishi Sinchai: farmer AND (land <= 2.5 OR SC/ST).
    ("C1019", "SCH-FRM-02", TODAY, "meets_criteria"),                 # marginal
    ("C1025", "SCH-FRM-02", TODAY, "meets_criteria"),                 # 3.8 acres but ST
    ("C1023", "SCH-FRM-02", TODAY, "does_not_meet"),                  # 6.4 acres, general
])
def test_seed_citizens(kb, citizens, citizen_id, scheme_id, as_of, expected):
    assert outcome(kb, citizens, citizen_id, scheme_id, as_of) == expected


def test_or_branch_that_passed_is_not_reported_as_a_blocker(kb, citizens):
    # C1021 is not a farmer. Land (0.0) satisfies the "land <= 2.5" branch, so the only blocker is occupation.
    verdict = evaluate("SCH-FRM-02", citizens.get("C1021"), kb, TODAY)
    assert verdict.blockers == ["Occupation is farmer"]


def test_every_branch_is_a_blocker_when_the_whole_or_fails(kb, citizens):
    verdict = evaluate("SCH-FRM-02", citizens.get("C1023"), kb, TODAY)
    assert len(verdict.blockers) == 2 and any("2.5" in b for b in verdict.blockers)


# ---- boundaries -------------------------------------------------------------------------------

@pytest.mark.parametrize("acres, expected", [(5.0, "meets_criteria"), (5.1, "does_not_meet")])
def test_land_limit_is_inclusive(kb, acres, expected):
    profile = {"occupation": "farmer", "residence_type": "rural", "land_holding_acres": acres}
    assert evaluate("SCH-FRM-01", profile, kb, TODAY).outcome == expected


@pytest.mark.parametrize("income, as_of, expected", [
    (150000, date(2026, 11, 21), "meets_criteria"),
    (150001, date(2026, 11, 21), "does_not_meet"),
    (120000, date(2026, 9, 9), "meets_criteria"),
    (120001, date(2026, 9, 9), "does_not_meet"),
])
def test_income_limit_is_inclusive_and_date_dependent(kb, income, as_of, expected):
    assert evaluate("SCH-PEN-01", {"age": 65, "annual_household_income": income}, kb, as_of).outcome == expected


def test_age_is_counted_on_the_application_date(kb):
    assert age_on(date(1966, 11, 21), date(2026, 11, 21)) == 60  # birthday is today
    assert age_on(date(1966, 11, 22), date(2026, 11, 21)) == 59  # birthday is tomorrow
    on_birthday = {"date_of_birth": "1966-11-21", "annual_household_income": 100000}
    day_before = {"date_of_birth": "1966-11-22", "annual_household_income": 100000}
    assert evaluate("SCH-PEN-01", on_birthday, kb, TODAY).outcome == "meets_criteria"
    assert evaluate("SCH-PEN-01", day_before, kb, TODAY).outcome == "does_not_meet"


def test_krishi_sinchai_has_no_residence_condition(kb):
    urban = {"occupation": "farmer", "land_holding_acres": 2, "residence_type": "urban"}
    assert evaluate("SCH-FRM-02", urban, kb, TODAY).outcome == "meets_criteria"
    assert evaluate("SCH-FRM-01", {**urban, "land_holding_acres": 2}, kb, TODAY).outcome == "does_not_meet"


# ---- missing information ----------------------------------------------------------------------

def test_missing_fields_are_asked_for_not_guessed(kb):
    verdict = evaluate("SCH-FRM-01", {"occupation": "farmer"}, kb, TODAY)
    assert verdict.outcome == "needs_info"
    assert set(verdict.missing_fields) == {"land_holding_acres", "residence_type"}


def test_a_known_failure_wins_over_missing_information(kb):
    verdict = evaluate("SCH-FRM-01", {"occupation": "labourer"}, kb, TODAY)
    assert verdict.outcome == "does_not_meet"


def test_or_branch_satisfied_without_the_other_field(kb):
    # Marginal land alone is enough for Krishi Sinchai; category is not needed.
    verdict = evaluate("SCH-FRM-02", {"occupation": "farmer", "land_holding_acres": 1.0}, kb, TODAY)
    assert verdict.outcome == "meets_criteria"


def test_scheme_not_yet_in_force_is_not_open(kb):
    assert evaluate("SCH-PEN-01", {"age": 70, "annual_household_income": 1}, kb, date(2026, 3, 31)).outcome == "not_open"


# ---- circular notes and documents -------------------------------------------------------------

def _land_notes(kb, as_of):
    profile = {"occupation": "farmer", "land_holding_acres": 3, "residence_type": "rural"}
    verdict = evaluate("SCH-FRM-01", profile, kb, as_of)
    return next(c for c in verdict.conditions if c.id == "land").notes


def test_household_land_note_appears_only_from_cir_2026_07(kb):
    assert _land_notes(kb, date(2026, 6, 30)) == []
    assert "CIR-2026-07" in _land_notes(kb, date(2026, 7, 1))[0]


def _passbook_notes(kb, as_of):
    verdict = evaluate("SCH-FRM-02", {"occupation": "farmer", "land_holding_acres": 1}, kb, as_of)
    return next(d for d in verdict.documents if d.name.startswith("Certified Land Holding")).notes


def test_digital_passbook_note_appears_only_from_cir_2026_08(kb):
    assert _passbook_notes(kb, date(2026, 8, 14)) == []
    assert "digital land passbook" in _passbook_notes(kb, date(2026, 8, 15))[0]


def _caste_requirement(kb, profile):
    verdict = evaluate("SCH-FRM-02", profile, kb, TODAY)
    return next(d for d in verdict.documents if d.name.startswith("Caste")).requirement


def test_caste_certificate_requirement_depends_on_the_clause_relied_on(kb, citizens):
    assert _caste_requirement(kb, citizens.get("C1025")) == "mandatory"   # ST, 3.8 acres: relies on the ST clause
    assert _caste_requirement(kb, citizens.get("C1019")) == "optional"    # qualifies on land alone
    assert _caste_requirement(kb, {"occupation": "farmer"}) == "conditional"


def test_optional_documents_are_labelled_optional(kb):
    verdict = evaluate("SCH-FRM-01", {}, kb, TODAY)
    optional = [d.name for d in verdict.documents if d.requirement == "optional"]
    assert optional == ["Farmer Registration Slip / Soil Health Card"]


# ---- normalisation and formatting -------------------------------------------------------------

def test_csv_strings_are_normalised():
    row = {"occupation": " Farmer ", "category": "ST", "annual_household_income": "1,25,000",
           "land_holding_acres": "3.8", "date_of_birth": "1969-04-12", "residence_type": "RURAL", "district": ""}
    profile = normalize_profile(row, TODAY)
    assert profile == {"occupation": "farmer", "category": "st", "residence_type": "rural",
                       "annual_household_income": 125000, "land_holding_acres": 3.8, "age": 57}


@pytest.mark.parametrize("amount, text", [(150000, "₹1,50,000"), (120000, "₹1,20,000"), (1500, "₹1,500"),
                                          (500, "₹500"), (12345678, "₹1,23,45,678")])
def test_indian_digit_grouping(amount, text):
    assert inr(amount) == text


def test_value_formatting():
    assert fmt_value("land_holding_acres", 5) == "5.0"
    assert fmt_value("category", frozenset({"st", "sc"})) == "SC / ST"
