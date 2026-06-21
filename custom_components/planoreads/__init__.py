"""The PlanoReads water-usage integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNT,
    CONF_HISTORY_DAYS,
    CONF_METER,
    CONF_ZIP,
    DEFAULT_HISTORY_DAYS,
    DOMAIN,
)
from .coordinator import PlanoReadsCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type PlanoReadsConfigEntry = ConfigEntry[PlanoReadsCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: PlanoReadsConfigEntry
) -> bool:
    """Set up PlanoReads from a config entry."""
    data = {**entry.data, **entry.options}
    coordinator = PlanoReadsCoordinator(
        hass,
        account=data[CONF_ACCOUNT],
        zip_code=data[CONF_ZIP],
        meter_id=data[CONF_METER],
        history_days=data.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PlanoReadsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PlanoReadsConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
