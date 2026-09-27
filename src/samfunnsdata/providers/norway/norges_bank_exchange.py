"""Bounded Norges Bank EXR quotations; raw values retain their quotation basis.

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

DATASET_ID = "norges-bank-exchange-rate"
NAMESPACE = "norges-bank-exchange-rate-v1"
# Explicit verified quotation contracts, not generic SDMX scaling rules.
CURRENCIES = {
    "EUR": (1, "4", "0"),
    "USD": (1, "4", "0"),
    "GBP": (1, "4", "0"),
    "SEK": (100, "2", "2"),
    "DKK": (100, "2", "2"),
}


def validate_currency(currency):
    if not isinstance(currency, str) or currency not in CURRENCIES:
        raise ValueError("Valuta må være EUR, USD, GBP, SEK eller DKK.")
    return currency


def series_code(currency):
    return f"B.{validate_currency(currency)}.NOK.SP"


def unit(currency):
    validate_currency(currency)
    return f"NOK per {CURRENCIES[currency][0]} {currency}"


def dimensions(currency):
    validate_currency(currency)
    _, decimals, multiplier = CURRENCIES[currency]
    return {
        "FREQ": "B",
        "BASE_CUR": currency,
        "QUOTE_CUR": "NOK",
        "TENOR": "SP",
        "DECIMALS": decimals,
        "UNIT_MULT": multiplier,
        "COLLECTION": "C",
        "CALCULATED": "false",
    }


@dataclass(frozen=True)
class ExchangeData:
    observations: tuple[TimeObservation, ...]
    fetched_at: datetime | None
    cache_hit: bool


def validate_selection(operation, since):
    if operation not in ("latest", "history"):
        raise ValueError("Valutakurser støtter bare latest og history.")
    if since is not None and (type(since) is not int or not 1 <= since <= 9999):
        raise ValueError("Fra år må være et heltall mellom 1 og 9999.")
    if operation == "latest" and since is not None:
        raise ValueError("Siste observasjon kan ikke kombineres med fra år.")


def parse_csv(text, currency):
    """Preserve numeric spelling, flags and dates; never fill calendar gaps."""
    validate_currency(currency)
    if not isinstance(text, str):
        raise ValueError("Norges Bank: CSV-respons mangler.")  # noqa: TRY004
    try:
        reader = csv.DictReader(
            io.StringIO(text.lstrip("\ufeff")), delimiter=";", strict=True
        )
        required = set(dimensions(currency)) | {"TIME_PERIOD", "OBS_VALUE"}
        allowed = required | {
            "Frequency",
            "Base Currency",
            "Quote Currency",
            "Tenor",
            "Unit Multiplier",
            "Collection Indicator",
            "OBS_STATUS",
            "Observation Status",
            "CALC_METHOD",
            "Calculation Method",
        }
        headers = reader.fieldnames or []
        if (
            not required <= set(headers)
            or set(headers) - allowed
            or len(set(headers)) != len(headers)
        ):
            raise ValueError("Norges Bank: uventede eller manglende CSV-felt.")
        observations = {}
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Norges Bank: ufullstendig CSV-rad.")
            expected = dimensions(currency)
            if any(row[key] != value for key, value in expected.items()):
                raise ValueError(
                    "Norges Bank: uventet serie, enhet eller observasjonsmetode."
                )
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
            method = row.get("CALC_METHOD")
            # Only the officially documented normal method is usable.
            usable = (
                value if status in (None, "") and method in (None, "", "N") else None
            )
            observations[period] = TimeObservation(
                period, period, raw, status, usable, method
            )
    except csv.Error as exc:
        raise ValueError("Norges Bank: ugyldig CSV.") from exc
    if not observations:
        raise ValueError("Norges Bank: ingen observasjoner for utvalget.")
    return tuple(observations[key] for key in sorted(observations))


def exchange_rate(currency, operation="latest", since=None, *, cache=None):
    validate_currency(currency)
    validate_selection(operation, since)
    cache = cache if cache is not None else JsonCache()
    params = {"format": "csv", "locale": "en"}
    if operation == "latest":
        params["lastNObservations"] = 1
    elif since is not None:
        params["startPeriod"] = f"{since:04d}-01-01"
    key = {"series": series_code(currency), "params": params}
    if network.get_mode() == network.NetworkMode.CACHE_ONLY:
        cached = cache.get(NAMESPACE, key)
        try:
            if not isinstance(cached, dict) or cached.get("version") != 1:
                raise ValueError("Missing cache")
            observations = parse_csv(cached["csv"], currency)
            stamp = datetime.fromisoformat(cached["fetched_at"])
            if stamp.utcoffset() is None:
                raise ValueError("Missing timezone")
        except (KeyError, TypeError, ValueError) as exc:
            raise network.CacheOnlyMiss(
                "Norges Bank: utvalget finnes ikke i gyldig lokal cache."
            ) from exc
        hit = True
    else:
        response = network.request(
            "norges_bank",
            "exchange_rate",
            "GET",
            "https://data.norges-bank.no/api/data/EXR/" + series_code(currency),
            params=params,
            follow_redirects=True,
            cache_relationship="refresh",
        )
        observations = parse_csv(response.text, currency)
        stamp = datetime.now(UTC)
        hit = False
    if operation == "latest" and len(observations) != 1:
        raise ValueError("Norges Bank: forventet én siste observasjon.")
    if since is not None and any(o.period < f"{since:04d}-01-01" for o in observations):
        raise ValueError("Norges Bank: observasjoner utenfor forespurt periode.")
    if not hit:
        cache.set(
            NAMESPACE,
            key,
            {"version": 1, "csv": response.text, "fetched_at": stamp.isoformat()},
        )
    return ExchangeData(observations, stamp, hit)
