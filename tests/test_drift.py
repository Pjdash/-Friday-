"""The scheme rules in mitra/schemes.py are typed in by hand. These tests fail if they stop matching the
markdown they claim to come from, so an edited guideline cannot leave the code silently out of date."""
from __future__ import annotations

import re

import pytest

from mitra import i18n
from mitra.schemes import (
    SCHEMES, AllOf, AnyOf, Condition, fmt_value, official_names, parse_required_documents,
)


def _conditions(node):
    if isinstance(node, Condition):
        yield node
    else:
        for child in node.children:
            yield from _conditions(child)


def _literals(cond: Condition, value) -> list[str]:
    shown = fmt_value(cond.field, value)
    if isinstance(value, (set, frozenset)):
        return [str(v).upper() for v in value]
    return [shown.removeprefix("₹")]


def _all_conditions():
    for scheme in SCHEMES.values():
        for cond in _conditions(scheme.rules):
            yield pytest.param(scheme, cond, id=f"{scheme.scheme_id}-{cond.id}")


@pytest.mark.parametrize("scheme, cond", list(_all_conditions()))
def test_rule_values_appear_in_the_cited_documents(kb, scheme, cond):
    base = kb.get(cond.source_id).body
    assert cond.field in base, f"{cond.field} not mentioned in {cond.source_id}"
    for literal in _literals(cond, cond.value):
        assert literal in base, f"{literal!r} not found in {cond.source_id}"
    for override in cond.overrides:
        doc = kb.get(override.source_id)
        assert scheme.scheme_id in doc.scheme_ids
        for literal in _literals(cond, override.value):
            assert literal in doc.body, f"{literal!r} not found in {override.source_id}"


@pytest.mark.parametrize("scheme", SCHEMES.values(), ids=lambda s: s.scheme_id)
def test_scheme_header_facts_match_the_guideline(kb, scheme):
    guideline = kb.get(scheme.guideline_id)
    assert scheme.scheme_id in guideline.scheme_ids
    assert scheme.department in guideline.body
    assert scheme.name in guideline.body
    for amount in re.findall(r"₹[\d,]+", scheme.benefit):
        assert amount in guideline.body
    sla_days = re.search(r"(\d+) working days", scheme.verification_sla).group(1)
    assert f"{sla_days} working days" in guideline.body


def test_logic_shape_of_krishi_sinchai_matches_the_stated_rule(kb):
    body = kb.get("GL-FRM-02").body
    assert "occupation = farmer AND (land_holding_acres <= 2.5 OR category in {SC, ST})" in body
    rules = SCHEMES["SCH-FRM-02"].rules
    assert isinstance(rules, AllOf) and isinstance(rules.children[1], AnyOf)


def test_caveats_and_limits_are_in_the_guidelines(kb):
    assert "superannuation pension" in kb.get("GL-PEN-01").body
    assert "Permanent resident" in kb.get("GL-PEN-01").body
    assert "one active benefit enrolment" in kb.get("GL-FRM-01").body


def test_note_texts_match_their_circulars(kb):
    assert "per farming household" in kb.get("CIR-2026-07").body
    assert "digital land passbook" in kb.get("CIR-2026-08").body
    assert "paper patta" in kb.get("CIR-2026-08").body


@pytest.mark.parametrize("scheme_id, mandatory, conditional, optional", [
    ("SCH-FRM-01", 4, 0, 1),
    ("SCH-FRM-02", 4, 1, 1),
    ("SCH-PEN-01", 5, 0, 1),
])
def test_required_documents_are_parsed_from_markdown(kb, scheme_id, mandatory, conditional, optional):
    docs = parse_required_documents(kb.get(SCHEMES[scheme_id].guideline_id))
    count = lambda kind: sum(d.requirement == kind for d in docs)  # noqa: E731
    assert (count("mandatory"), count("conditional"), count("optional")) == (mandatory, conditional, optional)
    assert all(d.validity for d in docs)


def test_every_conditional_document_has_a_rule(kb):
    for scheme in SCHEMES.values():
        for doc in parse_required_documents(kb.get(scheme.guideline_id)):
            if doc.requirement == "conditional":
                assert any(doc.name.startswith(prefix) for prefix in scheme.doc_conditions), doc.name


def test_official_names_cover_four_languages(kb):
    for scheme in SCHEMES.values():
        assert len(official_names(kb.get(scheme.guideline_id))) == 4


def test_appeal_timelines_quoted_by_the_assistant_match_pol_grv_01(kb):
    body = " ".join(kb.get("POL-GRV-01").body.split())
    for phrase in ("within 30 days of rejection/delay", "within **15 working days**",
                   "within 30 days of Tier 1 order", "within **30 working days**"):
        assert phrase in body, phrase
    agent_source = open(__import__("mitra.agent", fromlist=["x"]).__file__, encoding="utf-8").read()
    for phrase in ("within 30 days of the rejection", "15 working days", "within 30 days of the Tier 1 order",
                   "within 30 working days"):
        assert phrase in agent_source


@pytest.mark.parametrize("table", ["FINAL_DECISION", "ZERO_FEE", "FRAUD_REPORT", "NEVER_SHARE_OTP"])
@pytest.mark.parametrize("lang", ["hi", "kn", "ta"])
def test_localised_sentences_are_official_text_from_the_kb(kb, table, lang):
    corpus = " ".join(
        " ".join(d.body.replace("**", "").split()) for d in kb if d.language == lang and d.doc_type != "grievance")
    for sentence in re.split(r"[।.]\s*", getattr(i18n, table)[lang]):
        sentence = sentence.strip()
        if sentence:
            assert sentence in corpus, f"{lang}/{table}: {sentence!r} is not in the knowledge base"
