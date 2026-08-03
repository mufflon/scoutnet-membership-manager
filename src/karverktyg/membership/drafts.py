"""Build membership-request email drafts (§10). No sending — copy-paste output."""

from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Template as JinjaTemplate

from karverktyg.config.models import Bracket, KarConfig
from karverktyg.mail.recipients import resolve_recipients
from karverktyg.membership.eligibility import (
    avdelningar_sentence,
    bracket_label,
    eligible_bracket,
    pronoun_sv,
)
from karverktyg.membership.templates import Template
from karverktyg.scoutnet.models import Member


@dataclass
class EmailDraft:
    member_no: str
    kind: str  # "scout" | "ledare"
    to: list[str]
    subject: str
    body: str
    unsendable: bool = False


def is_ledare_applicant(member: Member, config: KarConfig, n: int | None) -> bool:
    if member.unit and member.unit in set(config.eighteen_plus_avdelningar()):
        return True
    if member.bracket is Bracket.ANNAT:
        return True
    return bool(member.birth_year and n and (n - member.birth_year) >= 18)


def _ledare_recipients(member: Member) -> list[str]:
    """The person directly, never their parents (§10)."""
    for f in ("contact_email", "email"):
        v = member.emails.get(f)
        if v:
            return [v.strip()]
    return []


def _render(source: str, ctx: dict) -> str:
    return JinjaTemplate(source, trim_blocks=True, lstrip_blocks=True).render(**ctx)


def build_draft(
    member: Member, config: KarConfig, n: int | None, templates: dict[str, Template], kar_name: str
) -> EmailDraft:
    ctx = {
        "first_name": member.first_name,
        "full_name": member.full_name,
        "birth_year": member.birth_year,
        "pronoun": pronoun_sv(member.sex_code),
        "kar": kar_name,
    }
    if is_ledare_applicant(member, config, n):
        to = _ledare_recipients(member)
        tpl = templates["ledare_request"]
        kind = "ledare"
    else:
        to = resolve_recipients(member)
        bracket = eligible_bracket(member.birth_year, n, config)
        ctx["bracket_label"] = bracket_label(bracket)
        ctx["avdelningar_sentence"] = avdelningar_sentence(bracket, config) if bracket else ""
        tpl = templates["scout_request"]
        kind = "scout"
    return EmailDraft(
        member_no=member.member_no,
        kind=kind,
        to=to,
        subject=_render(tpl.subject, ctx).strip(),
        body=_render(tpl.body, ctx).strip() + "\n",
        unsendable=not to,
    )


def generate_drafts(
    members: list[Member],
    config: KarConfig,
    n: int | None,
    templates: dict[str, Template],
    kar_name: str,
) -> list[EmailDraft]:
    return [build_draft(m, config, n, templates, kar_name) for m in members]
