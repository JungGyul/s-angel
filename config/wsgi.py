"""
WSGI config for S-angel project.

This module contains the WSGI application used by Django's development server
and any production WSGI deployments. It should expose a module-level variable
named ``application``. Django's ``runserver`` and ``runfcgi`` commands discover
this application via the ``WSGI_APPLICATION`` setting.

Usually you will have the standard Django WSGI application here, but it also
might make sense to replace the whole Django WSGI application with a custom one
that later delegates to the Django one. For example, you could introduce WSGI
middleware here, or combine a Django application with an application of another
framework.

"""

import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application


# This allows easy placement of apps within the interior
# s_angel directory.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "s_angel"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.
application = get_wsgi_application()


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


_prepare_on_start()
