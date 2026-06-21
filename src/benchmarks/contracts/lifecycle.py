from __future__ import annotations

from benchmarks.schemas.models import Lifecycle


def lifecycle_active(lifecycle: Lifecycle, prefix_end_event: int) -> bool:
    """Return true if a contract is active at the prefix end event."""
    if prefix_end_event < lifecycle.effective_from_event:
        return False
    if lifecycle.effective_until_event is not None and prefix_end_event >= lifecycle.effective_until_event:
        return False
    if lifecycle.revoked_at_event is not None and prefix_end_event >= lifecycle.revoked_at_event:
        return False
    return True
