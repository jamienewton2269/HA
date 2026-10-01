"""Runtime lease manager for bounded Home Assistant actuators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store

from .const import (
    EVENT_LEASE_CANCELLED,
    EVENT_LEASE_COMPLETED,
    EVENT_LEASE_ERROR,
    EVENT_LEASE_EXPIRED,
    EVENT_LEASE_RECOVERED,
    EVENT_LEASE_RESUMED,
    EVENT_LEASE_STARTED,
    STORE_KEY,
    STORE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Lease:
    """One active runtime lease."""

    entity_id: str
    started_at: str
    expires_at: str
    max_runtime_seconds: int
    source: str | None = None

    @property
    def expiry(self) -> datetime:
        return datetime.fromisoformat(self.expires_at)


class RuntimeLeaseManager:
    """Persist and reconcile active runtime leases."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)
        self.leases: dict[str, Lease] = {}
        self._cancel_timers: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load only active leases from persistent storage."""
        raw = await self.store.async_load() or {}
        leases = raw.get("leases", {})
        for entity_id, item in leases.items():
            try:
                self.leases[entity_id] = Lease(**item)
            except (TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid RLM lease for %s", entity_id)

    async def _async_save(self) -> None:
        await self.store.async_save(
            {"leases": {entity_id: asdict(lease) for entity_id, lease in self.leases.items()}}
        )

    def _event(self, event_type: str, lease: Lease, **extra: Any) -> None:
        """Emit a small structured lifecycle event for logging/syslog consumers."""
        data: dict[str, Any] = asdict(lease)
        data.update(extra)
        self.hass.bus.async_fire(event_type, data)

    def _cancel_timer(self, entity_id: str) -> None:
        cancel = self._cancel_timers.pop(entity_id, None)
        if cancel is not None:
            cancel()

    def _schedule(self, lease: Lease) -> None:
        self._cancel_timer(lease.entity_id)

        @callback
        def _expired(_now: datetime) -> None:
            self.hass.async_create_task(
                self.async_expire(lease.entity_id, reason="deadline")
            )

        self._cancel_timers[lease.entity_id] = async_track_point_in_utc_time(
            self.hass, _expired, lease.expiry
        )

    async def async_start(
        self,
        entity_id: str,
        max_runtime_seconds: int,
        *,
        activate: bool = True,
        source: str | None = None,
    ) -> Lease:
        """Create/replace a lease and optionally turn the entity on."""
        now = datetime.now(timezone.utc)
        lease = Lease(
            entity_id=entity_id,
            started_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=max_runtime_seconds)).isoformat(),
            max_runtime_seconds=max_runtime_seconds,
            source=source,
        )

        self.leases[entity_id] = lease
        await self._async_save()
        self._schedule(lease)

        if activate:
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on",
                    {"entity_id": entity_id},
                    blocking=True,
                )
            except Exception as err:
                self._cancel_timer(entity_id)
                self.leases.pop(entity_id, None)
                await self._async_save()
                self._event(EVENT_LEASE_ERROR, lease, operation="activate", error=str(err))
                raise

        self._event(EVENT_LEASE_STARTED, lease, activate=activate)
        return lease

    async def async_complete(self, entity_id: str, reason: str = "normal") -> bool:
        """Clear a lease after a normal completion."""
        lease = self.leases.pop(entity_id, None)
        if lease is None:
            return False
        self._cancel_timer(entity_id)
        await self._async_save()
        self._event(EVENT_LEASE_COMPLETED, lease, reason=reason)
        return True

    async def async_cancel(self, entity_id: str, reason: str = "cancelled") -> bool:
        """Clear a lease without changing the device state."""
        lease = self.leases.pop(entity_id, None)
        if lease is None:
            return False
        self._cancel_timer(entity_id)
        await self._async_save()
        self._event(EVENT_LEASE_CANCELLED, lease, reason=reason)
        return True

    async def async_expire(self, entity_id: str, *, reason: str) -> bool:
        """Turn off an expired leased entity and clear its lease."""
        lease = self.leases.get(entity_id)
        if lease is None:
            return False

        state = self.hass.states.get(entity_id)
        if state is not None and state.state == STATE_OFF:
            return await self.async_complete(entity_id, reason="already_off")

        try:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
            )
        except Exception as err:
            self._event(EVENT_LEASE_ERROR, lease, operation="expire", reason=reason, error=str(err))
            _LOGGER.exception("RLM failed to expire %s", entity_id)
            return False

        self.leases.pop(entity_id, None)
        self._cancel_timer(entity_id)
        await self._async_save()
        self._event(EVENT_LEASE_EXPIRED, lease, reason=reason)
        return True

    async def async_reconcile(self) -> dict[str, int]:
        """Reconcile active leases after Home Assistant startup."""
        now = datetime.now(timezone.utc)
        result = {"resumed": 0, "expired": 0, "cleared": 0, "errors": 0}

        for entity_id, lease in list(self.leases.items()):
            state = self.hass.states.get(entity_id)

            if state is not None and state.state == STATE_OFF:
                if await self.async_complete(entity_id, reason="off_during_restart"):
                    result["cleared"] += 1
                continue

            if lease.expiry <= now:
                ok = await self.async_expire(entity_id, reason="expired_during_restart")
                if ok:
                    result["expired"] += 1
                    self._event(EVENT_LEASE_RECOVERED, lease, recovery="expired_and_stopped")
                else:
                    result["errors"] += 1
                continue

            self._schedule(lease)
            result["resumed"] += 1
            remaining = max(0, int((lease.expiry - now).total_seconds()))
            self._event(EVENT_LEASE_RESUMED, lease, remaining_seconds=remaining)

            if state is not None and state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                _LOGGER.warning(
                    "RLM resumed %s while entity state is %s", entity_id, state.state
                )

        return result
