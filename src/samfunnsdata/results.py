"""Shared application contracts; no GTK or provider frames.

Population receipts retain v1/v2; non-municipal time series use receipt v3.

Source observations and derived facts are separate. None denotes unknown/missing,
not false, zero, or an empty collection. Provider metadata is an immutable JSON
snapshot, not an executable object or a dependency on DataFrame.attrs.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from .analysis import SeriesSummary
from .network import RequestRecord


@dataclass(frozen=True)
class Source:
    provider: str
    authority: str
    dataset_id: str
    dataset_title: str | None
    source_url: str | None
    access_url: str | None
    license: str | None = None


@dataclass(frozen=True)
class Measure:
    id: str
    source_code: str
    label: str
    unit: str


@dataclass(frozen=True)
class Selection:
    requested_place: str
    municipality: str
    municipality_code: str | None
    since: int | None
    measure_code: str
    source_period: str = "*"
    source_language: str = "no"
    source_format: str = "json-stat2"
    geography_codelist: str = "agg_KommSummer"
    geography_output: str = "aggregated"


@dataclass(frozen=True)
class Observation:
    period: str
    period_label: str
    source_value: int | float | str | None
    status: str | None
    usable_value: int | float | None


@dataclass(frozen=True)
class Provenance:
    fetched_at: datetime | None = None
    cache_hit: bool | None = None
    source_updated_at: str | None = None
    content_hash: str | None = None
    raw_data_reference: str | None = None
    network_mode: str | None = None
    network_occurred: bool | None = None
    requests: tuple[RequestRecord, ...] = ()

    def __post_init__(self):
        if self.fetched_at is not None and self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must include a timezone")


@dataclass(frozen=True)
class PopulationSeries:
    id: str
    selection: Selection
    source_returned_period: tuple[str, str]
    source_observations: tuple[Observation, ...]
    derived_facts: SeriesSummary
    status_available: bool
    provider_metadata_json: str | None
    provenance: Provenance
    warnings: tuple[str, ...] = ()

    @property
    def name(self):
        return self.selection.municipality


@dataclass(frozen=True)
class TimeObservation(Observation):
    calculation_method: str | None = None


@dataclass(frozen=True)
class SeriesSelection:
    operation: str
    since: int | None
    series_code: str


@dataclass(frozen=True)
class SeriesFacts:
    first_period: str
    last_period: str
    first_value: float | None
    last_value: float | None
    change: float | None
    change_unit: str


@dataclass(frozen=True)
class TimeSeries:
    id: str
    name: str
    selection: SeriesSelection
    source_returned_period: tuple[str, str]
    source_observations: tuple[TimeObservation, ...]
    derived_facts: SeriesFacts
    status_available: bool
    provider_metadata_json: str | None
    provenance: Provenance
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Transformation:
    operation: str
    series_ids: tuple[str, ...]
    description: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataReceipt:
    source: Source
    measure: Measure
    series: tuple[PopulationSeries | TimeSeries, ...]
    transformations: tuple[Transformation, ...]
    used_at: datetime
    application_version: str
    warnings: tuple[str, ...] = ()
    schema_version: str = "2"
    adapter_version: str = "ssb-population/1"
    query_plan_hash: str | None = None

    def __post_init__(self):
        if self.schema_version not in {"1", "2", "3"}:
            raise ValueError("Unsupported DataReceipt schema version")
        expected_series = TimeSeries if self.schema_version == "3" else PopulationSeries
        if any(not isinstance(item, expected_series) for item in self.series):
            raise ValueError("Series type does not match DataReceipt schema version")
        if self.used_at.utcoffset() is None:
            raise ValueError("used_at must include a timezone")

    def to_dict(self):
        value = asdict(self)
        value["used_at"] = self.used_at.isoformat()
        for series in value["series"]:
            stamp = series["provenance"]["fetched_at"]
            series["provenance"]["fetched_at"] = stamp.isoformat() if stamp else None
            if self.schema_version == "1":
                for key in ("network_mode", "network_occurred", "requests"):
                    series["provenance"].pop(key)
            # Expose an ordinary JSON object in the wire format, never escaped repr.
            metadata = series.pop("provider_metadata_json")
            series["provider_metadata"] = (
                json.loads(metadata) if metadata is not None else None
            )
        return value

    def to_json(self):
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )

    @classmethod
    def from_json(cls, text):
        value = json.loads(text)
        if value.get("schema_version") not in {"1", "2", "3"}:
            raise ValueError("Unsupported DataReceipt schema version")
        series = []
        for item in value.pop("series"):
            metadata = item.pop("provider_metadata")
            item["provider_metadata_json"] = (
                json.dumps(
                    metadata, ensure_ascii=False, sort_keys=True, allow_nan=False
                )
                if metadata is not None
                else None
            )
            is_time_series = value["schema_version"] == "3"
            selection_type = SeriesSelection if is_time_series else Selection
            item["selection"] = selection_type(**item["selection"])
            item["source_returned_period"] = tuple(item["source_returned_period"])
            item["source_observations"] = tuple(
                (TimeObservation if is_time_series else Observation)(**o) for o in item["source_observations"]
            )
            item["derived_facts"] = (SeriesFacts if is_time_series else SeriesSummary)(**item["derived_facts"])
            provenance = item["provenance"]
            if provenance["fetched_at"] is not None:
                provenance["fetched_at"] = datetime.fromisoformat(
                    provenance["fetched_at"]
                )
            provenance["requests"] = tuple(RequestRecord(**r) for r in provenance.get("requests", ()))
            item["provenance"] = Provenance(**provenance)
            item["warnings"] = tuple(item["warnings"])
            series.append((TimeSeries if is_time_series else PopulationSeries)(**item))
        transformations = tuple(
            Transformation(
                t["operation"],
                tuple(t["series_ids"]),
                t["description"],
                tuple(t["inputs"]),
                tuple(t["outputs"]),
            )
            for t in value.pop("transformations")
        )
        return cls(
            source=Source(**value.pop("source")),
            measure=Measure(**value.pop("measure")),
            series=tuple(series),
            transformations=transformations,
            used_at=datetime.fromisoformat(value.pop("used_at")),
            warnings=tuple(value.pop("warnings")),
            **value,
        )


@dataclass(frozen=True)
class AnalysisResult:
    title: str
    receipt: DataReceipt
    schema_version: str = "1"
    chart_hint: str = "time_series"
    table_hint: tuple[str, ...] = ("municipality", "period", "source_value", "status")

    def __post_init__(self):
        if self.schema_version != "1":
            raise ValueError("Unsupported AnalysisResult schema version")
        if not self.receipt.series:
            raise ValueError("An analysis needs at least one series")

    @property
    def series(self):
        return self.receipt.series

    @property
    def warnings(self):
        return self.receipt.warnings
