"""Exchange-rate application service using the shared result/receipt contract."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from . import network
from .catalog import get_dataset, get_source
from .help import application_version
from .providers.norway import norges_bank_exchange as nb
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


def analyze_exchange(
    currency, operation="latest", since=None, *, checkpoint=lambda: None
):
    unit = nb.unit(currency)
    code = nb.series_code(currency)
    checkpoint()
    with network.observe_requests() as requests:
        data = nb.exchange_rate(currency, operation, since)
    checkpoint()
    observations = data.observations
    first, last = observations[0], observations[-1]
    change = None
    if (
        operation == "history"
        and first.usable_value is not None
        and last.usable_value is not None
    ):
        change = float(Decimal(last.source_value) - Decimal(first.source_value))
    warnings = []
    if any(o.usable_value is None for o in observations):
        warnings.append(
            "Manglende eller merkede observasjoner beholdes; ingen eldre verdi erstatter et endepunkt."
        )
    if data.cache_hit:
        warnings.append(
            "Lokal cache: siste lagrede observasjon er ikke nødvendigvis siste publiserte observasjon."
        )
    warnings.append(
        "Indikative midtkurser, ikke kjøps- eller salgstilbud. Ingen utfylling av dager eller normalisering av kildeverdier."
    )
    facts = SeriesFacts(
        first.period, last.period, first.usable_value, last.usable_value, change, unit
    )
    series = TimeSeries(
        "series-1",
        f"Valutakurs {currency}",
        SeriesSelection(operation, since, code),
        (first.period, last.period),
        observations,
        facts,
        any(o.status is not None for o in observations),
        json.dumps(
            {
                **nb.dimensions(currency),
                "UNIT": None,
                "quotation_basis": nb.CURRENCIES[currency][0],
                "quotation_unit": unit,
                "presentation_transform": "identity",
                "normalization": None,
                "format": "csv",
                "locale": "en",
            },
            sort_keys=True,
        ),
        Provenance(
            fetched_at=data.fetched_at,
            cache_hit=data.cache_hit,
            network_mode=network.get_mode().value,
            network_occurred=any(r.network_occurred for r in requests),
            requests=tuple(requests),
        ),
        tuple(warnings),
    )
    transformations = [
        Transformation(
            "select_source_observations",
            (series.id,),
            "Velg siste publiserte observasjon eller historikk fra valgt år hos kilden. Sorter datoer stigende; ingen interpolasjon.",
            ("selection",),
            ("source_observations",),
        )
    ]
    if operation == "history":
        transformations.append(
            Transformation(
                "absolute_change",
                (series.id,),
                f"Siste minus første faktiske endepunkt i {unit}. Ingen prosentberegning; ubrukelig endepunkt gir ukjent endring.",
                ("source_observations",),
                ("derived_facts.change",),
            )
        )
    dataset = get_dataset(nb.DATASET_ID)
    source = get_source("norges_bank")
    receipt = DataReceipt(
        Source(
            source.id,
            source.authority,
            dataset.id,
            dataset.title,
            dataset.source_url,
            dataset.access_url + "/" + code,
        ),
        Measure("exchange_rate", code, f"Valutakurs {currency}", unit),
        (series,),
        tuple(transformations),
        datetime.now(UTC),
        application_version(),
        tuple(warnings),
        schema_version="3",
        adapter_version="norges-bank-exchange-rate/1",
    )
    return AnalysisResult(
        f"Norges Banks valutakurs: {currency}",
        receipt,
        table_hint=("period", "source_value", "status", "calculation_method"),
    )
