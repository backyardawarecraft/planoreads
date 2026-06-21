# PlanoReads Water — Home Assistant integration

Bring your **City of Plano, TX** water-meter data into Home Assistant.

The city's [PlanoReads portal](https://cus.plano.gov/planoreads) exposes **hourly**
meter reads, but only through a web page (a custom ASP.NET WebForms app — there is
no API). This integration logs in for you, scrapes the hourly reads, and feeds
them into Home Assistant as **long-term statistics** plus a few at-a-glance
sensors.

> **Scope:** This is specific to the City of Plano's portal. It is **not** an
> AquaHawk/EyeOnWater/SmartHub integration and will not work with other cities'
> water portals.

> **Unofficial:** Not affiliated with or endorsed by the City of Plano. It reads
> the same data you can see when you log in yourself; if the city changes the
> portal, the integration may break until updated.

## What you get

**Long-term statistics** (the useful part — hourly + daily bars in the Energy /
History views and `statistic-graph` cards):

- `planoreads:water_<meter>` — cumulative meter reading (gallons), from which HA
  derives per-hour and per-day usage.

**Sensors** (for dashboard tiles):

| Sensor | Description |
|--------|-------------|
| `Water used today` | Usage so far today (gallons) |
| `Meter reading` | Latest cumulative odometer reading (gallons) |
| `Last meter read` | Timestamp of the most recent read — shows how stale the portal data is |

> The portal lags hours-to-a-day, so "today" backfills late. The integration
> polls a few times per day; that is plenty.

## Install

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/backyardawarecraft/planoreads`, category **Integration**.
3. Install **PlanoReads Water**, then restart Home Assistant.

### Manual

Copy `custom_components/planoreads/` into your HA `config/custom_components/`
directory and restart.

## Configure

**Settings → Devices & Services → Add Integration → PlanoReads Water.** Enter the
same details you use to log in at `cus.plano.gov/planoreads`:

| Field | Where to find it |
|-------|------------------|
| Account number | Your Plano utility account number |
| Service address ZIP | The ZIP of the service address |
| Meter ID | Shown on the portal after you log in, next to your account |
| Days of history per poll | Default 30; the portal keeps a short rolling window and HA accumulates beyond it over time |

Each meter is a separate config entry, so multi-meter accounts are supported.

## Requirements

- Home Assistant **2024.12** or newer.
- The `recorder` integration (default in HA) — statistics are stored there.

## License

[MIT](LICENSE).
