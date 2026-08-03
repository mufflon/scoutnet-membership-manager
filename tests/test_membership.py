from __future__ import annotations

from sqlalchemy import create_engine

from karverktyg.config.models import Bracket
from karverktyg.db import Base, make_sessionmaker
from karverktyg.db.session import get_session
from karverktyg.membership import eligible_bracket, pronoun_sv
from karverktyg.membership.drafts import build_draft
from karverktyg.membership.templates import (
    DEFAULT_TEMPLATES,
    effective_templates,
    get_template,
    upsert_template,
)
from karverktyg.scoutnet.models import Member


def _m(**kw):
    m = Member(member_no=kw.pop("member_no", "1"))
    emails = kw.pop("emails", {})
    for k, v in kw.items():
        setattr(m, k, v)
    m.emails = emails
    return m


def test_pronoun_neutral_default():
    assert pronoun_sv("1") == "han"
    assert pronoun_sv("2") == "hon"
    assert pronoun_sv("0") == "hen"
    assert pronoun_sv(None) == "hen"


def test_eligible_bracket(config):
    assert eligible_bracket(2018, 2026, config) is Bracket.SPARARE  # age 8
    assert eligible_bracket(2015, 2026, config) is Bracket.UPPTACKARE  # age 11
    assert eligible_bracket(2011, 2026, config) is Bracket.UTMANARE  # age 15


def test_scout_draft_goes_to_guardians(config):
    m = _m(
        first_name="Alva",
        unit="Hajarna",
        unit_type_code=2,
        unit_troop_id=10155,
        birth_year=2018,
        sex_code="2",
        emails={"contact_email_mum": "mum@ex.se", "contact_email_dad": "dad@ex.se"},
    )
    d = build_draft(m, config, 2026, DEFAULT_TEMPLATES, "Scoutkåren Finn")
    assert d.kind == "scout"
    assert set(d.to) == {"mum@ex.se", "dad@ex.se"}
    assert "Alva" in d.body
    assert "Spårare" in d.body
    assert "måndagar (Hajarna)" in d.body  # weekday eligibility sentence
    assert "hon" in d.body  # pronoun from sex code


def test_ledare_draft_goes_to_self_not_parents(config):
    m = _m(
        first_name="Cecilia",
        unit="Ledare",
        unit_type_code=7,
        unit_troop_id=10172,
        birth_year=1988,
        sex_code="2",
        emails={"contact_email": "c@ex.se", "contact_email_mum": "parent@ex.se"},
    )
    d = build_draft(m, config, 2026, DEFAULT_TEMPLATES, "Finn")
    assert d.kind == "ledare"
    assert d.to == ["c@ex.se"]
    assert "parent@ex.se" not in d.to


def test_unsendable_when_no_address(config):
    m = _m(first_name="X", unit="Hajarna", unit_type_code=2, birth_year=2018)
    d = build_draft(m, config, 2026, DEFAULT_TEMPLATES, "Finn")
    assert d.unsendable is True
    assert d.to == []


def test_template_override_roundtrip():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_sessionmaker(engine)
    with get_session(factory) as s:
        assert (
            get_template(s, "scout_request").subject == DEFAULT_TEMPLATES["scout_request"].subject
        )  # default before edit
        upsert_template(s, "scout_request", "NY {{ first_name }}", "Body {{ kar }}", "alex")
    with get_session(factory) as s:
        assert get_template(s, "scout_request").subject == "NY {{ first_name }}"
        scout = next(e for e in effective_templates(s) if e["key"] == "scout_request")
        assert scout["edited"] is True
