"""Huey async tasks for scan execution.

In tests we set settings.HUEY['immediate']=True so calling run_scan(scan_id) runs
synchronously in-process. In production a Huey worker consumer pulls tasks off
the SQLite-backed queue.
"""
from __future__ import annotations

import logging

from huey.contrib.djhuey import db_task

logger = logging.getLogger(__name__)


@db_task()
def run_scan(scan_id: int):
    """Async entry point. Defers to apps.extraction.extractor.run_extraction.

    Imports are deferred so this module can be imported even when the extraction
    pipeline is mid-build; only callers actually executing a scan need it.
    """
    from apps.extraction.extractor import run_extraction
    from apps.scans.models import Scan

    try:
        scan = Scan.objects.get(pk=scan_id)
    except Scan.DoesNotExist:
        logger.error("run_scan: scan id %s not found", scan_id)
        return

    try:
        run_extraction(scan)
    except Exception as exc:
        logger.exception("run_scan failed for scan %s", scan_id)
        scan.refresh_from_db()
        if not scan.is_terminal():
            scan.status = scan.FAILED
            scan.error_message = f"unhandled: {exc!r}"
            scan.save(update_fields=["status", "error_message"])
        raise
