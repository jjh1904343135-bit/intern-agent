from __future__ import annotations


def advance_pending_applications_once(limit: int = 10) -> int:
    # Manual real-world applications are user-controlled; the worker must not fake status progress.
    return 0
