from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from ... import network
from ...catalog import get_dataset, get_source
from ...help import application_version
from ...results import (
    AnalysisResult,
    DataReceipt,
    Measure,
    Provenance,
    SeriesFacts,
    SeriesSelection,
    Source,
    TimeObservation,
    TimeSeries,
    Transformation,
)

DATASET_ID = "statens-vegvesen-traffic-volume"
URL = "https://trafikkdata.atlas.vegvesen.no/graphql"
NAMESPACE = "statens-vegvesen-traffic-volume-v1"


@dataclass(frozen=True)
class TrafficData:
    observations: tuple[TimeObservation, ...]
    fetched_at: datetime | None
    cache_hit: bool


def validate_selection(operation, road_reference, since):
    if operation not in ("latest", "history"):
        raise ValueError("Trafikk støtter bare latest og history.")
    if not isinstance(road_reference, str) or not road_reference.strip():
        raise ValueError("Vegreferansen må være en ikke-tom streng.")
    if since is not None and (type(since) is not int or since < 1900):
        raise ValueError("Fra år må være et heltall fra 1900 eller senere.")
    if operation == "latest" and since is not None:
        raise ValueError("Siste observasjon kan ikke kombineres med fra år.")


def _normalize_road_reference(value: str) -> str:
    normalized = str(value).strip().upper()
    replacements = {"Å": "A", "Ø": "O", "Æ": "AE"}
    for original, replacement in replacements.items():
        normalized = normalized.replace(original, replacement)
    return normalized


def _as_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(" ", ""))
        except ValueError:
            return None
    return None


def _extract_average_value(item):
    if not isinstance(item, dict):
        return None, None
    total = item.get("total") if isinstance(item.get("total"), dict) else None
    volume = total.get("volume") if total else None
    if isinstance(volume, dict):
        average = volume.get("average")
        if average is not None:
            return average, item.get("year")
    if isinstance(item.get("volume"), dict):
        average = item.get("volume", {}).get("average")
        if average is not None:
            return average, item.get("year")
    if "average" in item and item["average"] is not None:
        return item["average"], item.get("year")
    return None, item.get("year")


def _parse_response(payload: str | dict, road_reference: str) -> tuple[TimeObservation, ...]:
    if isinstance(payload, str):
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Statens vegvesen: ugyldig JSON-respons.") from exc
    else:
        value = payload
    if not isinstance(value, dict):
        raise TypeError("Statens vegvesen: forventet et objekt med trafikkdata.")

    data = value.get("data") if isinstance(value.get("data"), dict) else value
    graph_payload = data if isinstance(data, dict) else {}

    candidates = []
    if isinstance(graph_payload.get("trafficData"), dict):
        candidates.extend(_extract_series(graph_payload["trafficData"]))
    if isinstance(graph_payload.get("trafficRegistrationPoints"), list):
        candidates.extend(_extract_series_from_registration_points(graph_payload["trafficRegistrationPoints"]))
    if not candidates:
        # Support older/broader JSON schema forms as a fallback.
        observations = value.get("observations") or value.get("data") or value.get("series") or ()
        for item in observations:
            if not isinstance(item, dict):
                continue
            period = str(item.get("period") or item.get("year") or item.get("time") or "")
            raw = item.get("source_value")
            if raw is None:
                raw = item.get("value")
            value_float = _as_float(raw)
            method = item.get("calculation_method") or item.get("method") or "AADT"
            if period:
                candidates.append((period, raw, value_float, item.get("status"), method))

    parsed: list[TimeObservation] = []
    for period, raw_value, usable, status, method in candidates:
        if period is None or period == "":
            continue
        if usable is None and raw_value is not None:
            usable = _as_float(raw_value)
        parsed.append(
            TimeObservation(
                period=str(period),
                period_label=str(period),
                source_value=raw_value,
                status=status,
                usable_value=usable,
                calculation_method=method or "AADT",
            )
        )

    if not parsed:
        raise ValueError(f"Statens vegvesen: ingen trafikkobservasjoner for {road_reference}.")
    return tuple(sorted(parsed, key=lambda obs: str(obs.period)))


def _extract_series(value):
    series = []
    if not isinstance(value, dict):
        return series
    volume = value.get("volume") if isinstance(value, dict) else None
    if not isinstance(volume, dict):
        return series
    daily = volume.get("average", {}).get("daily", {}) if isinstance(volume.get("average"), dict) else {}
    if isinstance(daily, dict):
        for key in ("ALL", "WEEKDAY", "WEEKEND"):
            if key in daily:
                series.extend(_normalise_daily_bucket(daily[key], key))
    elif isinstance(daily, list):
        series.extend(_normalise_daily_bucket(daily, "ALL"))
    return series


def _normalise_daily_bucket(bucket, key):
    items = []
    if isinstance(bucket, list):
        for item in bucket:
            value, period = _extract_average_value(item)
            if value is None:
                continue
            items.append((period, value, _as_float(value), None, key))
    elif isinstance(bucket, dict):
        value, period = _extract_average_value(bucket)
        if value is not None:
            items.append((period, value, _as_float(value), None, key))
    return items


def _extract_series_from_registration_points(points):
    items = []
    if not isinstance(points, list):
        return items
    for point in points:
        if not isinstance(point, dict):
            continue
        if "dataTimeSpan" not in point:
            continue
        latest = point.get("dataTimeSpan", {}).get("latestData") or {}
        yearly = latest.get("volumeAverageDailyByYear")
        if yearly is None:
            previous = point.get("latestData") or {}
            yearly = previous.get("volumeAverageDailyByYear")
        if yearly is None and isinstance(latest, list):
            years = latest
            for item in years:
                if isinstance(item, dict) and "year" in item:
                    yearly = item
                    break
        if yearly is not None:
            value = yearly if isinstance(yearly, (int, float, str)) else (((yearly.get("total") or {}).get("volume") or {}).get("average") if isinstance(yearly, dict) else None)
            if value is not None:
                year = point.get("dataTimeSpan", {}).get("latestData", {}).get("year")
                items.append((year or 0, value, _as_float(value), None, "AADT"))
    return items


def _resolve_traffic_registration_point(road_reference: str):
    normalized = _normalize_road_reference(road_reference)
    query = {
        "query": "query trps($query: String) { trafficRegistrationPoints(searchQuery: { query: $query, registrationFrequency: CONTINUOUS }) { id name location { roadReference { shortForm } } } }",
        "variables": {"query": normalized},
    }
    response = network.request(
        "vegvesen",
        "traffic_volume",
        "POST",
        URL,
        json=query,
        follow_redirects=True,
        cache_relationship="refresh",
    )
    payload = response.json()
    points = payload.get("data", {}).get("trafficRegistrationPoints") or []
    if not isinstance(points, list) or not points:
        raise ValueError(f"Statens vegvesen: fant ingen trafikkregistreringspunkter for {road_reference}.")
    scored = []
    for point in points:
        location = point.get("location") or {}
        road_ref = ((location.get("roadReference") or {}).get("shortForm") or "")
        score = 0
        if road_ref and road_ref.upper() == normalized:
            score += 100
        elif normalized in road_ref.upper():
            score += 60
        elif normalized in (point.get("name") or "").upper():
            score += 30
        scored.append((score, road_ref, point))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]["id"]


def traffic_volume(road_reference, operation="latest", since=None, *, checkpoint=lambda: None, cache=None):
    validate_selection(operation, road_reference, since)
    checkpoint()
    if network.get_mode() == network.NetworkMode.CACHE_ONLY:
        raise network.CacheOnlyMiss(
            "Statens vegvesen: trafikkdata finnes ikke i lokal cache. Tillat nettverk for å hente offisiell ÅDT-data."
        )

    trp_id = _resolve_traffic_registration_point(road_reference)
    query = {
        "query": "query averageDailyByYear($trpid: String!) { trafficData(trafficRegistrationPointId: $trpid) { volume { average { daily { ALL: byYear(dayType: ALL) { year total { volume { average } coverage { percentage } } } WEEKDAY: byYear(dayType: WEEKDAY) { year total { volume { average } coverage { percentage } } } WEEKEND: byYear(dayType: WEEKEND) { year total { volume { average } coverage { percentage } } } } } } }",
        "variables": {"trpid": trp_id},
    }
    with network.observe_requests() as requests:
        response = network.request(
            "vegvesen",
            "traffic_volume",
            "POST",
            URL,
            json=query,
            follow_redirects=True,
            cache_relationship="refresh",
        )
        payload = response.json()
    checkpoint()
    observations = _parse_response(payload, road_reference)
    if operation == "latest":
        observations = observations[-1:]
    elif since is not None:
        observations = tuple(item for item in observations if str(item.period).isdigit() and int(str(item.period)) >= since)
    if not observations:
        raise ValueError(f"Statens vegvesen: ingen observert trafikk etter {since} for {road_reference}.")

    first, last = observations[0], observations[-1]
    facts = SeriesFacts(first.period, last.period, first.usable_value, last.usable_value, None, "kjøretøy/dag")
    source = get_source("vegvesen")
    dataset = get_dataset(DATASET_ID)
    series = TimeSeries(
        "series-1",
        f"Vegtrafikk {road_reference}",
        SeriesSelection(operation, since, road_reference),
        (first.period, last.period),
        observations,
        facts,
        any(obs.status is not None for obs in observations),
        json.dumps({"road_reference": road_reference, "source": "vegvesen", "format": "json"}, sort_keys=True),
        Provenance(
            fetched_at=datetime.now(UTC),
            cache_hit=False,
            network_mode=network.get_mode().value,
            network_occurred=any(r.network_occurred for r in requests),
            requests=tuple(requests),
        ),
        ("Kildeverdier er offisielle publiserte ÅDT-/årsverdier fra Statens vegvesen.",),
    )
    receipt = DataReceipt(
        Source(
            source.id,
            source.authority,
            dataset.id,
            dataset.title,
            dataset.source_url,
            dataset.access_url,
            license="Norsk offentligt tilgjengelig data",
        ),
        Measure("traffic_volume", road_reference, f"Vegtrafikk {road_reference}", "kjøretøy/dag"),
        (series,),
        (
            Transformation(
                "select_source_observations",
                (series.id,),
                "Velg siste publiserte ÅDT-verdier eller historikk for valgt vegreferanse.",
                ("selection",),
                ("source_observations",),
            ),
        ),
        datetime.now(UTC),
        application_version(),
        ("Offisiell Trafikkdata-kilde, uten hardkodede stub-værdier.",),
        schema_version="3",
        adapter_version="statens-vegvesen-traffic-volume/1",
    )
    return AnalysisResult(f"Vegtrafikk: {road_reference}", receipt)
