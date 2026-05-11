import logging
import os
import threading

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docer.settings")
application = get_wsgi_application()

logger = logging.getLogger(__name__)


def _run_inprocess_huey_consumer() -> None:
    """Run djhuey's `run_huey` management command in this thread.

    Delegates to Huey's own consumer machinery so all settings.HUEY options
    (worker count, worker_type, periodic tasks) are honored. Wrapped in a
    try/except so a consumer crash doesn't kill the web process.
    """
    from django.core.management import call_command

    try:
        call_command("run_huey")
    except Exception:
        logger.exception("In-process Huey consumer crashed; web stays up")


# Demo-only: when DOCER_INPROCESS_HUEY=1, co-locate the Huey worker inside the
# gunicorn process so a single Railway service handles both web requests and
# background scans. REQUIRES gunicorn --workers=1 — otherwise each worker spawns
# its own consumer and they fight over the SQLite queue.
if os.environ.get("DOCER_INPROCESS_HUEY", "0") == "1":
    threading.Thread(
        target=_run_inprocess_huey_consumer,
        daemon=True,
        name="huey-inprocess",
    ).start()
