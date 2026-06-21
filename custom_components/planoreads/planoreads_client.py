"""Client for scraping the City of Plano 'planoreads' water portal.

The portal (cus.plano.gov/planoreads) is a custom ASP.NET WebForms app, NOT a
standard AquaHawk instance, so there is no JSON API to call. Auth is account
number + service-address ZIP, submitted as a WebForms postback:

    1. GET the page  -> scrape __VIEWSTATE / __VIEWSTATEGENERATOR / __EVENTVALIDATION
    2. POST those + account + zip + meter + date range + Button1=Search
    3. The response renders the full hourly reads table (#tableData) inline.

The table columns are:
    Read Date | Read Time | Reading | Previous Reading | Hourly Usage(gallons)

'Reading' is the cumulative meter odometer (gallons, tenths) and is what we
feed to HA statistics; the per-hour usage is derived by HA as the diff.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re

import aiohttp

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=45)

# The portal is flaky (intermittent empty GETs / error-page POSTs), so retry
# the whole login a few times before surfacing a failure.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_BACKOFF = 3  # seconds, multiplied by the attempt number

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}


class PlanoReadsError(Exception):
    """Base error for the PlanoReads client."""


class PlanoReadsAuthError(PlanoReadsError):
    """Raised when the portal rejects the account/ZIP or returns the error page."""


@dataclass(frozen=True)
class HourlyRead:
    """A single hourly meter read."""

    when: datetime  # tz-aware, aligned to the top of the hour (local time)
    reading: float  # cumulative meter odometer, gallons
    usage: float  # portal-reported usage for this hour, gallons


def _hidden(html: str, name: str) -> str:
    """Pull an ASP.NET hidden-field value out of the page HTML."""
    m = re.search(r'id="%s"\s+value="([^"]*)"' % re.escape(name), html) or re.search(
        r'name="%s"[^>]*value="([^"]*)"' % re.escape(name), html
    )
    return m.group(1) if m else ""


def _parse_table(html: str, tzinfo) -> list[HourlyRead]:
    """Parse the #tableData hourly reads table out of the rendered page."""
    tables = re.findall(r"<table\b.*?</table>", html, re.S | re.I)
    target = next(
        (t for t in tables if "Hourly Usage" in t or "Read Date" in t), None
    )
    if target is None:
        return []

    reads: dict[datetime, HourlyRead] = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", target, re.S | re.I):
        cells = [
            re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
            for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        ]
        if len(cells) < 5 or not re.match(r"\d\d/\d\d/\d\d", cells[0]):
            continue  # header / pagination / malformed row
        date_s, time_s, reading_s = cells[0], cells[1], cells[2]
        usage_s = cells[4]
        try:
            naive = datetime.strptime(f"{date_s} {time_s}", "%m/%d/%y %I:%M %p")
            reading = float(reading_s)
            usage = float(usage_s) if usage_s not in ("", "-") else 0.0
        except ValueError:
            continue
        when = naive.replace(minute=0, second=0, microsecond=0, tzinfo=tzinfo)
        # de-dupe on the hour; last value wins
        reads[when] = HourlyRead(when=when, reading=reading, usage=usage)

    return sorted(reads.values(), key=lambda r: r.when)


class PlanoReadsClient:
    """Logs into the portal and returns parsed hourly reads."""

    def __init__(self, account: str, zip_code: str, meter_id: str, tzinfo) -> None:
        self._account = account
        self._zip = zip_code
        self._meter = meter_id
        self._tz = tzinfo

    async def async_fetch(self, history_days: int) -> list[HourlyRead]:
        """Log in and return parsed hourly reads, retrying transient failures.

        Retries the whole login a few times so a single flaky GET/POST doesn't
        blank the sensors for an entire update cycle. Raises PlanoReadsAuthError
        if every attempt fails.
        """
        end = datetime.now(self._tz)
        start = end - timedelta(days=history_days)
        s_start = start.strftime("%m/%d/%Y")
        s_end = end.strftime("%m/%d/%Y")

        last_err: PlanoReadsError = PlanoReadsError("no attempt ran")
        for attempt in range(_MAX_FETCH_ATTEMPTS):
            try:
                return await self._attempt(s_start, s_end)
            except (PlanoReadsError, aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_err = (
                    err
                    if isinstance(err, PlanoReadsError)
                    else PlanoReadsError(f"network error: {err}")
                )
                _LOGGER.debug(
                    "Fetch attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_FETCH_ATTEMPTS,
                    last_err,
                )
                if attempt + 1 < _MAX_FETCH_ATTEMPTS:
                    await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
        raise last_err

    async def _attempt(self, s_start: str, s_end: str) -> list[HourlyRead]:
        """One full login + scrape attempt."""
        _LOGGER.debug(
            "Fetching meter %s, range %s..%s", self._meter, s_start, s_end
        )
        # A fresh session per fetch keeps the cookie jar isolated.
        async with aiohttp.ClientSession(headers=_HEADERS) as session:
            # The portal's first GET intermittently returns an empty body (it
            # just sets cookies); a follow-up GET on the warmed session returns
            # the real page. Retry until the ASP.NET tokens are present.
            landing = ""
            for attempt in range(3):
                async with session.get(BASE_URL, timeout=_TIMEOUT) as resp:
                    landing = await resp.text()
                _LOGGER.debug(
                    "GET landing attempt %d: status=%s len=%d",
                    attempt + 1,
                    resp.status,
                    len(landing),
                )
                if _hidden(landing, "__VIEWSTATE"):
                    break

            form = {
                "__VIEWSTATE": _hidden(landing, "__VIEWSTATE"),
                "__VIEWSTATEGENERATOR": _hidden(landing, "__VIEWSTATEGENERATOR"),
                "__EVENTVALIDATION": _hidden(landing, "__EVENTVALIDATION"),
                "ctl00$MainContent$txtAccount": self._account,
                "ctl00$MainContent$txtZip": self._zip,
                "ctl00$MainContent$txtStart": s_start,
                "ctl00$MainContent$txtEnd": s_end,
                # Submit the meter dropdown EMPTY on the search postback. On the
                # initial page the dropdown has no <option>s yet, so ASP.NET's
                # __EVENTVALIDATION rejects any non-empty value and bounces to
                # the error page. The server selects the meter from account+ZIP.
                "ctl00$MainContent$ddMeters": "",
                "ctl00$MainContent$Button1": "Search",
            }
            post_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": BASE_URL,
                "Origin": "https://cus.plano.gov",
            }
            _LOGGER.debug(
                "Login tokens: viewstate=%d eventvalidation=%d generator=%r",
                len(form["__VIEWSTATE"]),
                len(form["__EVENTVALIDATION"]),
                form["__VIEWSTATEGENERATOR"],
            )
            async with session.post(
                BASE_URL, data=form, headers=post_headers, timeout=_TIMEOUT
            ) as resp:
                page = await resp.text()
            _LOGGER.debug("POST search: status=%s len=%d", resp.status, len(page))

        # Success is determined purely by whether the hourly reads table
        # parsed. (Do NOT test for 'authenticated = "False"' — that string is
        # present even on the *successful* page as a JS default, so it produces
        # false rejections. The error page simply has no reads table.)
        reads = _parse_table(page, self._tz)
        _LOGGER.debug("Parsed %d hourly reads from response", len(reads))
        if not reads:
            _LOGGER.debug(
                "No reads parsed. Response starts: %s", page[:300].replace("\n", " ")
            )
            raise PlanoReadsAuthError(
                "Could not read the hourly table. The portal rejected the "
                "account / ZIP / meter, or is temporarily throttling logins. "
                "Double-check the values and try again in a few minutes."
            )
        return reads
