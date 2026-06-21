"""Coordinator: poll the portal, import statistics, expose derived values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)

# HA replaced has_mean (bool) with mean_type (enum); breaks in 2026.11.
# Prefer the new field, fall back to the old one on older cores.
try:
    from homeassistant.components.recorder.models import StatsMeanType

    _MEAN_META: dict = {"mean_type": StatsMeanType.NONE}
except ImportError:  # HA cores predating StatsMeanType
    _MEAN_META = {"has_mean": False}
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    UNIT_GALLONS,
    UPDATE_INTERVAL_HOURS,
)
from .planoreads_client import HourlyRead, PlanoReadsClient, PlanoReadsError

_LOGGER = logging.getLogger(__name__)


@dataclass
class PlanoData:
    """Derived values surfaced to sensors."""

    latest_reading: float | None
    last_read: datetime | None
    today_usage: float | None


class PlanoReadsCoordinator(DataUpdateCoordinator[PlanoData]):
    """Fetches reads, imports them as external statistics, derives sensor state."""

    def __init__(
        self,
        hass: HomeAssistant,
        account: str,
        zip_code: str,
        meter_id: str,
        history_days: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {meter_id}",
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self._meter_id = meter_id
        self._history_days = history_days
        self._client = PlanoReadsClient(
            account, zip_code, meter_id, dt_util.DEFAULT_TIME_ZONE
        )
        # Fixed statistic_id (single meter). If you ever add a second meter,
        # make this per-meter to avoid a collision. The "_usage" series holds a
        # cumulative-usage sum (the earlier ":water" series held the odometer
        # and is now orphaned — delete it in Developer Tools → Statistics).
        self.statistic_id = f"{DOMAIN}:water_usage"

    async def _async_update_data(self) -> PlanoData:
        try:
            reads = await self._client.async_fetch(self._history_days)
        except PlanoReadsError as err:
            raise UpdateFailed(str(err)) from err

        await self._import_statistics(reads)
        return self._derive(reads)

    async def _import_statistics(self, reads: list[HourlyRead]) -> None:
        """Push hourly usage into HA long-term statistics.

        `sum` is a running total of *usage* (gallons), continued from whatever
        is already stored — NOT the raw meter odometer. Chaining off the last
        stored sum keeps the series continuous as the portal's rolling window
        moves, only ever appends new hours (idempotent), and makes the very
        first bucket start near zero instead of dumping the whole odometer
        reading into one bar.
        """
        metadata = StatisticMetaData(
            has_sum=True,
            name=f"Plano Water {self._meter_id}",
            source=DOMAIN,
            statistic_id=self.statistic_id,
            unit_of_measurement=UNIT_GALLONS,
            **_MEAN_META,
        )

        prev_sum, prev_ts = await self._last_sum()
        running = prev_sum
        stats: list[StatisticData] = []
        for r in reads:  # ascending by time
            if prev_ts is not None and r.when.timestamp() <= prev_ts:
                continue  # already imported in an earlier poll
            running = round(running + r.usage, 3)
            stats.append(StatisticData(start=r.when, state=r.reading, sum=running))

        if stats:
            async_add_external_statistics(self.hass, metadata, stats)
        _LOGGER.debug(
            "Imported %d new hourly statistics for %s (cumulative sum now %.1f)",
            len(stats),
            self.statistic_id,
            running,
        )

    async def _last_sum(self) -> tuple[float, float | None]:
        """Return (last cumulative sum, its start timestamp) already stored."""
        try:
            res = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, self.statistic_id, True, {"sum"}
            )
        except Exception:  # noqa: BLE001 — tolerate API drift across cores
            _LOGGER.debug("get_last_statistics failed", exc_info=True)
            return 0.0, None
        rows = res.get(self.statistic_id) if res else None
        if not rows:
            return 0.0, None
        row = rows[0]
        start = row.get("start")
        ts = start if isinstance(start, (int, float)) else getattr(start, "timestamp", lambda: None)()
        return float(row.get("sum") or 0.0), ts

    def _derive(self, reads: list[HourlyRead]) -> PlanoData:
        if not reads:
            return PlanoData(None, None, None)
        latest = reads[-1]
        today = dt_util.now().date()
        today_usage = round(
            sum(r.usage for r in reads if r.when.date() == today), 1
        )
        return PlanoData(
            latest_reading=latest.reading,
            last_read=latest.when,
            today_usage=today_usage,
        )
