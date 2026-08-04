"""
Email templates: shipped defaults + DB overrides (§10).

Templates are stored in the database and editable in-app. The shipped defaults
are the fallback and serve as worked examples. The resolver returns the DB row
if present, otherwise the default — so drafts work with no seeding.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from scoutnet_membership_manager.db.models import EmailTemplate


@dataclass
class Template:
    """Template."""

    key: str
    subject: str
    body: str
    description: str = ""


_SCOUT_BODY = """\
Hej!

Tack för {{ first_name }}s intresse för {{ kar }}.

{% if bracket_label %}{{ first_name }} är född {{ birth_year }}, vilket gör att \
{{ pronoun }} kan bli {{ bracket_label }}. {{ avdelningar_sentence }}

Har ni något önskemål om vilken avdelning som passar bäst?
{% else %}Vi återkommer med information om vilken avdelning som passar {{ first_name }} bäst.
{% endif %}
Vänliga hälsningar,
{{ kar }}
"""

_LEDARE_BODY = """\
Hej {{ first_name }}!

Tack för ditt intresse för att bli ledare i {{ kar }}.
Vi återkommer med mer information om nästa steg och ett första möte.

Vänliga hälsningar,
{{ kar }}
"""

DEFAULT_TEMPLATES: dict[str, Template] = {
    "scout_request": Template(
        key="scout_request",
        subject="Välkommen till {{ kar }} – {{ first_name }}",
        body=_SCOUT_BODY,
        description="Medlemsansökan, scout – skickas till vårdnadshavare.",
    ),
    "ledare_request": Template(
        key="ledare_request",
        subject="Ledaransökan till {{ kar }} – {{ first_name }}",
        body=_LEDARE_BODY,
        description="Ledaransökan – skickas till personen själv, aldrig föräldrar.",
    ),
}


def get_template(session: Session, key: str) -> Template:
    """Get template."""
    row = session.execute(
        select(EmailTemplate).where(EmailTemplate.template_key == key)
    ).scalar_one_or_none()
    if row is not None:
        return Template(
            key=key,
            subject=row.subject,
            body=row.body,
            description=DEFAULT_TEMPLATES.get(key, Template(key, "", "")).description,
        )
    return DEFAULT_TEMPLATES[key]  # KeyError on an unknown key is intentional


def templates_by_key(session: Session) -> dict[str, Template]:
    """Templates by key."""
    return {key: get_template(session, key) for key in DEFAULT_TEMPLATES}


def effective_templates(session: Session) -> list[dict]:
    """Effective templates."""
    overrides = {r.template_key: r for r in session.execute(select(EmailTemplate)).scalars()}
    out = []
    for key, dflt in DEFAULT_TEMPLATES.items():
        r = overrides.get(key)
        out.append(
            {
                "key": key,
                "subject": r.subject if r else dflt.subject,
                "body": r.body if r else dflt.body,
                "description": dflt.description,
                "edited": r is not None,
            }
        )
    return out


def upsert_template(
    session: Session, key: str, subject: str, body: str, by: str | None = None
) -> None:
    """Upsert template."""
    if key not in DEFAULT_TEMPLATES:
        raise KeyError(key)
    row = session.execute(
        select(EmailTemplate).where(EmailTemplate.template_key == key)
    ).scalar_one_or_none()
    if row is not None:
        row.subject, row.body, row.updated_by = subject, body, by
    else:
        session.add(EmailTemplate(template_key=key, subject=subject, body=body, updated_by=by))
    session.flush()
