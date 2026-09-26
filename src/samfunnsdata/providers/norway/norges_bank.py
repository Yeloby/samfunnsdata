"""Norges Bank IR/B.KPRA.SD.R only: business-day, end-of-day rates.

The CSV representation and DSD were verified against the official API.
No URL, series identifier or parser binding comes from user/remote metadata.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import isfinite

from ... import network
from ...cache import JsonCache
from ...results import TimeObservation

DATASET_ID = "norges-bank-policy-rate"
SERIES = "B.KPRA.SD.R"
URL = "https://data.norges-bank.no/api/data/IR/" + SERIES
NAMESPACE = "norges-bank-policy-rate-v1"


@dataclass(frozen=True)
class RateData:
    observations: tuple[TimeObservation, ...]
    fetched_at: datetime | None
    cache_hit: bool


def validate_selection(operation, since):
    if operation not in ("latest", "history"):
        raise ValueError("Styringsrenten støtter bare latest og history.")
    if since is not None and (type(since) is not int or not 1 <= since <= 9999):
        raise ValueError("Fra år må være et heltall mellom 1 og 9999.")
    if operation == "latest" and since is not None:
        raise ValueError("Siste observasjon kan ikke kombineres med fra år.")


def parse_csv(text):
    """Preserve numeric spelling, flags and dates; never fill calendar gaps."""
    if not isinstance(text, str):
        raise ValueError("Norges Bank: CSV-respons mangler.")  # noqa: TRY004
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";", strict=True)
        required = {"FREQ", "INSTRUMENT_TYPE", "TENOR", "UNIT_MEASURE", "DECIMALS",
                    "COLLECTION", "TIME_PERIOD", "OBS_VALUE", "CALC_METHOD"}
        allowed = required | {"Frequency", "Instrument Type", "Tenor", "Unit of Measure",
                              "Collection Indicator", "Calculation Method", "OBS_STATUS", "Observation Status"}
        headers = reader.fieldnames or []
        if not required <= set(headers) or set(headers) - allowed or len(set(headers)) != len(headers):
            raise ValueError("Norges Bank: uventede eller manglende CSV-felt.")
        observations = {}
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Norges Bank: ufullstendig CSV-rad.")
            expected = {"FREQ": "B", "INSTRUMENT_TYPE": "KPRA", "TENOR": "SD",
                        "UNIT_MEASURE": "R", "COLLECTION": "E", "DECIMALS": "2"}
            if any(row[key] != value for key, value in expected.items()):
                raise ValueError("Norges Bank: uventet serie, enhet eller observasjonsmetode.")
            period = row["TIME_PERIOD"]
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", period):
                raise ValueError("Norges Bank: ugyldig observasjonsdato.")
            date.fromisoformat(period)
            if period in observations:
                raise ValueError("Norges Bank: doble observasjonsdatoer.")
            raw = row["OBS_VALUE"]
            value = None
            if raw != "":
                if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", raw):
                    raise ValueError("Norges Bank: ugyldig kildeverdi.")
                value = float(raw)
                if not isfinite(value):
                    raise ValueError("Norges Bank: ikke-endelig kildeverdi.")
            status = row.get("OBS_STATUS")
            method = row["CALC_METHOD"]
            # Unknown/nonempty method flags are retained, not interpreted as normal.
            usable = value if status in (None, "") and method == "" else None
            observations[period] = TimeObservation(period, period, raw, status, usable, method)
    except csv.Error as exc:
        raise ValueError("Norges Bank: ugyldig CSV.") from exc
    if not observations:
        raise ValueError("Norges Bank: ingen observasjoner for utvalget.")
    return tuple(observations[key] for key in sorted(observations))


def policy_rate(operation="latest", since=None, *, cache=None):
    validate_selection(operation, since)
    cache = cache if cache is not None else JsonCache()
    params = {"format": "csv", "locale": "en"}
    if operation == "latest":
        params["lastNObservations"] = 1
    elif since is not None:
        params["startPeriod"] = f"{since:04d}-01-01"
    key = {"series": SERIES, "params": params}
    if network.get_mode() == network.NetworkMode.CACHE_ONLY:
        cached = cache.get(NAMESPACE, key)
        try:
            if not isinstance(cached, dict) or cached.get("version") != 1:
                raise ValueError("Missing cache")
            observations = parse_csv(cached["csv"])
            stamp = datetime.fromisoformat(cached["fetched_at"])
            if stamp.utcoffset() is None:
                raise ValueError("Missing timezone")
        except (KeyError, TypeError, ValueError) as exc:
            raise network.CacheOnlyMiss("Norges Bank: utvalget finnes ikke i gyldig lokal cache.") from exc
        hit = True
    else:
        response = network.request("norges_bank", "policy_rate", "GET", URL,
                                   params=params, follow_redirects=True, cache_relationship="refresh")
        observations = parse_csv(response.text)
        stamp = datetime.now(UTC)
        hit = False
    if operation == "latest" and len(observations) != 1:
        raise ValueError("Norges Bank: forventet én siste observasjon.")
    if since is not None and any(o.period < f"{since:04d}-01-01" for o in observations):
        raise ValueError("Norges Bank: observasjoner utenfor forespurt periode.")
    if not hit:
        cache.set(NAMESPACE, key, {"version": 1, "csv": response.text, "fetched_at": stamp.isoformat()})
    return RateData(observations, stamp, hit)
