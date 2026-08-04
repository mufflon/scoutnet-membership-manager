"""
WSGI entrypoint for gunicorn: ``gunicorn scoutnet_membership_manager.wsgi:app``.

Mode and credentials come from the environment (§6, §13). In read_only /
read_write this fails loudly at import if keys are missing — deliberate.
"""

from scoutnet_membership_manager.web import create_app

app = create_app()
