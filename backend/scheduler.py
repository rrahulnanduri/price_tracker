"""Background re-checks of watchlist products, so history builds without anyone searching."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .config import get_region
from .search import SearchService

logger = logging.getLogger(__name__)

POLL_SECONDS = 300          # how often to look for due products
PAUSE_BETWEEN_CHECKS = 20   # spacing between live fetches, to stay under source limits


def is_due(watch: dict, refresh_hours: float, now: datetime | None = None) -> bool:
    if not watch["last_checked_at"]:
        return True
    last = datetime.fromisoformat(watch["last_checked_at"])
    return (now or datetime.now(timezone.utc)) - last >= timedelta(hours=refresh_hours)


async def refresh_due(service: SearchService, pause: float = PAUSE_BETWEEN_CHECKS) -> int:
    """Re-check every due watchlist product once. Returns how many were checked."""
    due = [w for w in service.storage.list_watches() if is_due(w, service.settings.refresh_hours)]
    for index, watch in enumerate(due):
        region = get_region(watch["country"])
        if region is None:
            continue
        try:
            result = await service.search(watch["product"], region, refresh=True)
            error = None if result["results"] else "No matching offers found"
        except Exception as exc:
            logger.warning("Scheduled check failed for %s: %s", watch["product"], exc)
            error = str(exc) or type(exc).__name__
        # A failed check still counts as checked, so one broken product is not retried every poll.
        service.storage.update_watch(
            watch["id"], last_checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            last_error=error,
        )
        if index < len(due) - 1:
            await asyncio.sleep(pause)
    return len(due)


async def run_forever(service: SearchService) -> None:
    while True:
        try:
            await refresh_due(service)
        except Exception:
            logger.exception("Watchlist refresh loop failed")
        await asyncio.sleep(POLL_SECONDS)
