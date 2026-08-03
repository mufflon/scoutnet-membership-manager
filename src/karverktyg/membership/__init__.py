"""Membership-request email drafts (§5, §10).

Phase 1 generates *drafts* — recipients + subject + body — for the operator to
copy into their own mail client. Nothing is sent. Templates are stored in the
database and editable; shipped defaults are the fallback and the examples.
"""

from karverktyg.membership.drafts import EmailDraft, generate_drafts
from karverktyg.membership.eligibility import bracket_label, eligible_bracket, pronoun_sv
from karverktyg.membership.templates import (
    DEFAULT_TEMPLATES,
    effective_templates,
    get_template,
    upsert_template,
)

__all__ = [
    "DEFAULT_TEMPLATES",
    "EmailDraft",
    "bracket_label",
    "effective_templates",
    "eligible_bracket",
    "generate_drafts",
    "get_template",
    "pronoun_sv",
    "upsert_template",
]
