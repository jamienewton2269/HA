"""RLM - Runtime Lease Manager."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .manager import RuntimeLeaseManager

_LOGGER = logging.getLogger(__name__)

START_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("max_runtime_seconds"): vol.All(vol.Coerce(int), vol.Range(min=1, max=604800)),
        vol.Optional("activate", default=True): cv.boolean,
        vol.Optional("source"): cv.string,
    }
)
ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("reason"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up RLM from YAML."""
    manager = RuntimeLeaseManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager

    async def handle_start(call: ServiceCall) -> None:
        await manager.async_start(
            call.data["entity_id"],
            call.data["max_runtime_seconds"],
            activate=call.data.get("activate", True),
            source=call.data.get("source"),
        )

    async def handle_complete(call: ServiceCall) -> None:
        await manager.async_complete(
            call.data["entity_id"], call.data.get("reason", "normal")
        )

    async def handle_cancel(call: ServiceCall) -> None:
        await manager.async_cancel(
            call.data["entity_id"], call.data.get("reason", "cancelled")
        )

    async def handle_reconcile(_call: ServiceCall) -> None:
        result = await manager.async_reconcile()
        _LOGGER.info("RLM manual reconciliation: %s", result)

    hass.services.async_register(DOMAIN, "start", handle_start, schema=START_SCHEMA)
    hass.services.async_register(DOMAIN, "complete", handle_complete, schema=ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, "cancel", handle_cancel, schema=ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, "reconcile", handle_reconcile)

    async def _startup_reconcile(_event) -> None:
        result = await manager.async_reconcile()
        _LOGGER.info("RLM startup reconciliation: %s", result)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _startup_reconcile)
    return True
