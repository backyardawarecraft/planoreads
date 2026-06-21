"""Constants for the PlanoReads water-usage integration."""

DOMAIN = "planoreads"

CONF_ACCOUNT = "account"
CONF_ZIP = "zip_code"
CONF_METER = "meter_id"
CONF_HISTORY_DAYS = "history_days"

# How many days of hourly history to request from the portal each poll.
# The portal keeps a short rolling window; HA accumulates beyond it over time.
DEFAULT_HISTORY_DAYS = 30

# The portal data lags hours-to-a-day, so polling a few times per day is plenty.
UPDATE_INTERVAL_HOURS = 8

BASE_URL = "https://cus.plano.gov/planoreads"

# External-statistics unit. HA's UnitOfVolume.GALLONS == "gal".
UNIT_GALLONS = "gal"
