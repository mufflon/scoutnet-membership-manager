"""WSGI entrypoint for gunicorn: ``gunicorn karverktyg.wsgi:app``.

Mode and credentials come from the environment (§6, §13). In read_only /
read_write this fails loudly at import if keys are missing — deliberate.
"""

from karverktyg.web import create_app

app = create_app()
