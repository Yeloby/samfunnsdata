"""Policy-rate application service using the shared result/receipt contract."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from . import network
from .catalog import get_dataset, get_source
from .help import application_version
from .providers.norway import norges_bank
from .results import (
    AnalysisResult,
    DataReceipt,
    Measure,
    Provenance,
    SeriesFacts,
    SeriesSelection,
    Source,
    TimeSeries,
    Transformation,
)


def analyze_rate(operation="latest", since=None, *, checkpoint=lambda: None):
    checkpoint()
    with network.observe_requests() as requests:
        data = norges_bank.policy_rate(operation, since)
    checkpoint()
    observations = data.observations
    first, last = observations[0], observations[-1]
    change = None
    if operation == "history" and first.usable_value is not None and last.usable_value is not None:
        change = float(Decimal(last.source_value) - Decimal(first.source_value))
    warnings = []
    if any(o.usable_value is None for o in observations):
        warnings.append("Manglende eller merkede observasjoner beholdes; ingen eldre verdi erstatter et endepunkt.")
    if data.cache_hit:
        warnings.append("Lokal cache: siste lagrede observasjon er ikke nødvendigvis siste publiserte observasjon.")
    warnings.append("Virkedagsobservasjoner ved slutten av dagen; ingen utfylling av dager eller tolkning som vedtaksdato.")
    facts = SeriesFacts(first.period, last.period, first.usable_value, last.usable_value, change, "prosentpoeng")
    series = TimeSeries(
        "series-1", "Styringsrente",
        SeriesSelection(operation, since, norges_bank.SERIES),
        (first.period, last.period), observations, facts,
        any(o.status is not None for o in observations),
        json.dumps({"FREQ": "B", "INSTRUMENT_TYPE": "KPRA", "TENOR": "SD", "UNIT_MEASURE": "R",
                    "COLLECTION": "E", "DECIMALS": "2", "format": "csv", "locale": "en"}, sort_keys=True),
        Provenance(fetched_at=data.fetched_at, cache_hit=data.cache_hit,
                   network_mode=network.get_mode().value,
                   network_occurred=any(r.network_occurred for r in requests), requests=tuple(requests)),
        tuple(warnings),
    )
    transformations = [Transformation(
        "select_source_observations", (series.id,),
        "Velg siste publiserte observasjon eller historikk fra valgt år hos kilden. Sorter datoer stigende; ingen interpolasjon.",
        ("selection",), ("source_observations",),
    )]
    if operation == "history":
        transformations.append(Transformation(
            "absolute_change", (series.id,),
            "Siste minus første faktiske endepunkt, i prosentpoeng. Manglende eller merket endepunkt gir ukjent endring.",
            ("source_observations",), ("derived_facts.change",),
        ))
    dataset = get_dataset(norges_bank.DATASET_ID)
    source = get_source("norges_bank")
    receipt = DataReceipt(
        Source(source.id, source.authority, dataset.id, dataset.title, dataset.source_url, dataset.access_url),
        Measure("policy_rate", norges_bank.SERIES, "Styringsrente", "prosent"),
        (series,), tuple(transformations), datetime.now(UTC), application_version(), tuple(warnings),
        schema_version="3", adapter_version="norges-bank-policy-rate/1",
    )
    return AnalysisResult("Norges Banks styringsrente", receipt,
                          table_hint=("period", "source_value", "status", "calculation_method"))
