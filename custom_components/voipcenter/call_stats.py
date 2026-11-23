"""Monthly call minutes from the VoipCenter call detail records.

Outgoing minutes are counted per SIP account from ``logs/cdr``. A call that a
dialplan forwards to an external number is a single incoming record without a
SIP account; its route (``logs/calldetail``) shows which dialplan forwarded it.
Routes are fetched once per call and kept in storage, since each takes a
request and PBXonline only keeps them for about 20 days.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from aiovoipcenter import VoipCenterClient, VoipCenterError
from aiovoipcenter.types import CallRecord, find_forward

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CALL_STATS_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from .coordinator import VoipCenterConfigEntry

_LOGGER = logging.getLogger(__name__)

# Version 2 tells routes that PBXonline no longer has apart from calls that
# were not forwarded.
STORAGE_VERSION = 2
# Call routes fetched at the same time.
ROUTE_CONCURRENCY = 4
# Stored for a call whose route PBXonline no longer has, so its forward is
# unknown.
ROUTE_UNKNOWN = "unknown"
# An empty route of a call that ended this recently is fetched again later
# instead of being stored as unknown.
RETRY_EMPTY_ROUTE = timedelta(days=1)
# Keep recomputing the previous month this long into a new month, so calls
# that were still going on at midnight are counted once they have ended.
PREVIOUS_MONTH_SETTLE = timedelta(days=1)


@dataclass
class CallTotals:
    """Calls and talk time of one SIP account or dialplan in a month."""

    calls: int = 0
    answered_calls: int = 0
    seconds: int = 0

    @property
    def minutes(self) -> float:
        """Return the talk time in minutes."""
        return round(self.seconds / 60, 1)

    def add(self, record: CallRecord) -> None:
        """Count one call."""
        self.calls += 1
        if talk := record.talk_seconds:
            self.answered_calls += 1
            self.seconds += talk


@dataclass
class MonthTotals:
    """Outgoing minutes per SIP account and forwarded minutes per dialplan."""

    outgoing: dict[int, CallTotals] = field(default_factory=dict)
    forwarded: dict[int, CallTotals] = field(default_factory=dict)
    # External numbers each dialplan forwarded to.
    forward_numbers: dict[int, set[str]] = field(default_factory=dict)
    # Calls answered without a SIP account whose route PBXonline no longer
    # has (or not yet), so whether they were forwarded is unknown.
    unknown_route_calls: int = 0


@dataclass
class CallStats:
    """Totals of the current and the previous month."""

    month_start: datetime
    current: MonthTotals
    previous: MonthTotals
    # Dialplans that forward to an external number: ID -> name.
    forwarding_dialplans: dict[int, str]


def _month_starts(now: datetime) -> tuple[datetime, datetime]:
    """Return the local start of this month and of the previous month."""
    month_start = dt_util.start_of_local_day(now.replace(day=1))
    previous_start = dt_util.start_of_local_day(
        (month_start - timedelta(days=1)).replace(day=1)
    )
    return month_start, previous_start


class _RouteStore(Store[dict[str, Any]]):
    """Storage of the call routes."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict[str, Any]:
        """Keep only the forwards; version 1 stored lost routes as not forwarded."""
        return {
            "routes": {
                call_id: route
                for call_id, route in old_data.get("routes", {}).items()
                if isinstance(route, list)
            }
        }


def _forwards_externally(dialplan: Any) -> bool:
    """Return whether a dialplan has a step that dials an external number."""
    return any(
        step.raw.get("action") == "externalNumber" for step in dialplan.steps or []
    )


class VoipCenterCallStatsCoordinator(DataUpdateCoordinator[CallStats]):
    """Polls the call detail records and sums the minutes per month."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VoipCenterConfigEntry,
        client: VoipCenterClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_call_stats",
            update_interval=CALL_STATS_INTERVAL,
        )
        self.client = client
        self._store = _RouteStore(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.call_routes"
        )
        # Call ID -> [dialplan ID, number] of its forward, None if not
        # forwarded, or ROUTE_UNKNOWN. Loaded from storage on the first update.
        self._routes: dict[int, list[Any] | str | None] | None = None
        # Whether routes changed since they were last written to storage.
        self._routes_changed = False
        # Start, totals and call IDs of the previous month, computed once.
        self._previous: tuple[datetime, MonthTotals, set[int]] | None = None

    async def _async_update_data(self) -> CallStats:
        if self._routes is None:
            stored = await self._store.async_load() or {}
            self._routes = {
                int(call_id): route
                for call_id, route in stored.get("routes", {}).items()
            }
        now = dt_util.now()
        month_start, previous_start = _month_starts(now)
        try:
            dialplans = await self.client.get_dialplans()
            records = await self.client.get_cdr_between(
                int(month_start.timestamp()), int(now.timestamp())
            )
            current = await self._totals(records)
            if (
                self._previous is None
                or self._previous[0] != previous_start
                or now - month_start < PREVIOUS_MONTH_SETTLE
            ):
                previous_records = await self.client.get_cdr_between(
                    int(previous_start.timestamp()), int(month_start.timestamp()) - 1
                )
                self._previous = (
                    previous_start,
                    await self._totals(previous_records),
                    {record.ID for record in previous_records if record.ID},
                )
        except VoipCenterError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            # Keep the routes fetched so far, also when a request failed.
            await self._save_routes()
        self._prune_routes(
            {record.ID for record in records if record.ID} | self._previous[2]
        )
        await self._save_routes()
        return CallStats(
            month_start=month_start,
            current=current,
            previous=self._previous[1],
            forwarding_dialplans={
                dialplan.ID: dialplan.logicalName or str(dialplan.ID)
                for dialplan in dialplans
                if dialplan.ID is not None and _forwards_externally(dialplan)
            },
        )

    async def _totals(self, records: list[CallRecord]) -> MonthTotals:
        """Sum the outgoing and forwarded calls of a month."""
        totals = MonthTotals()
        candidates: list[CallRecord] = []
        for record in records:
            if record.callDirection == "outgoing":
                origin = record.originInfo
                if origin is not None and origin.ID is not None:
                    totals.outgoing.setdefault(origin.ID, CallTotals()).add(record)
            elif (
                record.callDirection == "incoming"
                and record.isAnswered
                and record.ID is not None
                and not (record.answeredbyInfo and record.answeredbyInfo.sipUsername)
            ):
                # Answered without a SIP account: forwarded, or e.g. voicemail.
                candidates.append(record)
        await self._fetch_routes(candidates)
        assert self._routes is not None
        for record in candidates:
            if (
                record.ID not in self._routes
                or (route := self._routes[record.ID]) == ROUTE_UNKNOWN
            ):
                totals.unknown_route_calls += 1
                continue
            if not isinstance(route, list) or route[0] is None:
                continue
            dialplan_id, number = route
            totals.forwarded.setdefault(dialplan_id, CallTotals()).add(record)
            if number:
                totals.forward_numbers.setdefault(dialplan_id, set()).add(number)
        return totals

    async def _fetch_routes(self, records: list[CallRecord]) -> None:
        """Fetch and store the forward of calls whose route is not known yet."""
        assert self._routes is not None
        missing = [record for record in records if record.ID not in self._routes]
        if not missing:
            return
        semaphore = asyncio.Semaphore(ROUTE_CONCURRENCY)
        retry_after = (dt_util.utcnow() - RETRY_EMPTY_ROUTE).timestamp()

        async def fetch(record: CallRecord) -> None:
            assert record.ID is not None
            async with semaphore:
                route = await self.client.get_call_route(record.ID)
            assert self._routes is not None
            if not route:
                # PBXonline keeps routes for about 20 days; a recent call may
                # just not have one yet, so try it again next time.
                if (record.endTs or 0) < retry_after:
                    self._routes[record.ID] = ROUTE_UNKNOWN
                return
            forward = find_forward(route)
            self._routes[record.ID] = (
                [forward.dialplanID, forward.number] if forward else None
            )

        self._routes_changed = True
        await asyncio.gather(*(fetch(record) for record in missing))

    def _prune_routes(self, call_ids: set[int]) -> None:
        """Forget the routes of calls before the previous month."""
        assert self._routes is not None
        stale = set(self._routes) - call_ids
        for call_id in stale:
            del self._routes[call_id]
        if stale:
            self._routes_changed = True

    async def _save_routes(self) -> None:
        """Write the routes to storage if they changed."""
        if not self._routes_changed or self._routes is None:
            return
        self._routes_changed = False
        await self._store.async_save(
            {"routes": {str(k): v for k, v in self._routes.items()}}
        )
