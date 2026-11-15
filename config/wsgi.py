"""
WSGI config for S-angel project.

Exposes the module-level ``application`` used by gunicorn.
"""

import os
import sys
from pathlib import Path

import django
from django.core.wsgi import get_wsgi_application

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "s_angel"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")


def _prepare_on_start():
    """Apply migrations / cache table / static manifest at boot.

    Render may be configured with a build command that skips build.sh, so do the
    essential steps here too. Idempotent; a Postgres advisory lock keeps multiple
    gunicorn workers from running them at the same time. Disable with
    DJANGO_PREPARE_ON_START=0.
    """
    if os.environ.get("DJANGO_PREPARE_ON_START", "1") != "1":
        return
    if not os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("production"):
        return
    import logging

    from django.core.management import call_command
    from django.db import connection

    log = logging.getLogger("s_angel.startup")
    lock_id = 4_242_042
    is_pg = connection.vendor == "postgresql"
    try:
        if is_pg:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(%s)", [lock_id])
        call_command("migrate", interactive=False, verbosity=1)
        call_command("createcachetable", verbosity=0)
        call_command("collectstatic", interactive=False, verbosity=0)
    except Exception:  # never block the web server from starting
        log.exception("Startup preparation failed")
    finally:
        if is_pg:
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
            except Exception:
                log.exception("Could not release startup lock")
        connection.close()


# Prepare BEFORE building the WSGI app: WhiteNoise indexes STATIC_ROOT when its
# middleware is created, so collectstatic must have finished by then
# (otherwise the hashed /static/ URLs return 404).
django.setup(set_prefix=False)
_prepare_on_start()
application = get_wsgi_application()
