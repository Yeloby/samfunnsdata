from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from .catalog import SupportStatus, get_dataset
from .population import analyze_population
from .providers.norway.ssb import (
    find_municipality,
    find_municipality_local,
    municipalities,
    municipality_population,
)
from .results import AnalysisResult


class QueryPlanValidationError(ValueError):
    """Raised when a declarative query plan cannot be validated."""


@dataclass(frozen=True)
class QueryPlan:
    dataset_id: str
    operation: str = "lookup"
    filters: dict[str, Any] = field(default_factory=dict)
    measure: str | None = None
    grouping: tuple[str, ...] = ()
    ordering: tuple[str, ...] = ()
    limit: int | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "operation": self.operation,
            "filters": dict(self.filters),
            "measure": self.measure,
            "grouping": list(self.grouping),
            "ordering": list(self.ordering),
            "limit": self.limit,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            canonicalize_plan(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def plan_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"

    @classmethod
    def from_json(cls, payload: str | dict[str, Any]) -> QueryPlan:
        data = canonicalize_plan(payload)
        return cls(**{**data, "grouping": tuple(data["grouping"]),
                      "ordering": tuple(data["ordering"])})


def canonicalize_plan(plan: QueryPlan | dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(plan, QueryPlan):
        data = {key: getattr(plan, key) for key in plan.__dataclass_fields__}
    elif isinstance(plan, str):
        try:
            data = json.loads(plan)
        except (ValueError, TypeError) as exc:
            raise QueryPlanValidationError("Invalid QueryPlan JSON.") from exc
    else:
        data = plan
    if not isinstance(data, dict):
        raise QueryPlanValidationError("QueryPlan must be a JSON object.")
    fields = {"schema_version", "dataset_id", "operation", "filters", "measure",
              "grouping", "ordering", "limit"}
    if set(data) - fields:
        raise QueryPlanValidationError("Unknown QueryPlan fields.")
    for key in ("dataset_id", "operation", "measure"):
        value = data.get(key, "lookup" if key == "operation" else None)
        if not isinstance(value, str) or not value.strip():
            raise QueryPlanValidationError(f"Plan must include a non-empty {key}.")
    if type(data.get("schema_version", 1)) is not int:
        raise QueryPlanValidationError("schema_version must be an integer.")
    if not isinstance(data.get("filters", {}), dict):
        raise QueryPlanValidationError("filters must be an object.")
    for key in ("grouping", "ordering"):
        value = data.get(key, ())
        if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
            raise QueryPlanValidationError(f"{key} must be an array of strings.")
    limit = data.get("limit")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise QueryPlanValidationError("limit must be a positive integer.")
    return {
        "schema_version": data.get("schema_version", 1),
        "dataset_id": data["dataset_id"],
        "operation": data.get("operation", "lookup"),
        "filters": dict(data.get("filters", {})),
        "measure": data["measure"],
        "grouping": list(data.get("grouping", ())),
        "ordering": list(data.get("ordering", ())),
        "limit": limit,
    }


def _population_dataset_plan_filters(filters: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    aliases = {"municipality": "geography", "place": "geography", "geography": "geography", "year": "year"}
    for key, value in filters.items():
        normalized = aliases.get(str(key), str(key))
        if normalized in canonical:
            raise QueryPlanValidationError(f"Duplicate filter dimension: {normalized}")
        canonical[normalized] = value
    return canonical


def validate_query_plan(plan: QueryPlan | dict[str, Any] | str, *, dataset_override=None) -> QueryPlan:
    canonical = canonicalize_plan(plan)
    schema_version = canonical["schema_version"]
    if schema_version not in {1}:
        raise QueryPlanValidationError(f"Unsupported schema_version: {schema_version}")

    if dataset_override is not None:
        if isinstance(dataset_override, dict):
            dataset = SimpleNamespace(
                id=dataset_override.get("id"),
                support=dataset_override.get("support"),
                measures=tuple(dataset_override.get("measures") or ()),
                dimensions=tuple(dataset_override.get("dimensions") or ()),
            )
        else:
            dataset = dataset_override
    else:
        try:
            dataset = get_dataset(str(canonical["dataset_id"]))
        except KeyError as exc:
            raise QueryPlanValidationError(f"Unknown dataset: {canonical['dataset_id']}") from exc

    if getattr(dataset, "support", None) != SupportStatus.SUPPORTED:
        raise QueryPlanValidationError(
            f"Dataset {getattr(dataset, 'id', canonical['dataset_id'])} is not SUPPORTED for execution."
        )

    if canonical["dataset_id"] != "ssb-07459-population":
        raise QueryPlanValidationError("No query plan executor for this dataset.")
    for key in ("grouping", "ordering", "limit"):
        if canonical[key] not in ([], None):
            raise QueryPlanValidationError(f"Unsupported plan option: {key}")

    operation = canonical["operation"]
    if operation != "lookup":
        raise QueryPlanValidationError(f"Unsupported operation: {operation}")

    if canonical["measure"] is None:
        raise QueryPlanValidationError("Plan must include a measure.")
    if canonical["measure"] not in dataset.measures:
        raise QueryPlanValidationError(
            f"Unknown measure '{canonical['measure']}' for dataset {getattr(dataset, 'id', canonical['dataset_id'])}."
        )

    raw_filters = dict(canonical.get("filters") or {})
    normalized_filters = _population_dataset_plan_filters(raw_filters)
    if "geography" in dataset.dimensions and "geography" not in normalized_filters:
        if "municipality" in raw_filters:
            normalized_filters["geography"] = raw_filters["municipality"]
        elif "place" in raw_filters:
            normalized_filters["geography"] = raw_filters["place"]
        else:
            raise QueryPlanValidationError("Plan missing required filter: municipality")
    if "year" in dataset.dimensions and "year" not in normalized_filters:
        raise QueryPlanValidationError("Plan missing required filter: year")

    allowed_dimension_names = set(dataset.dimensions)
    for key in normalized_filters:
        if key not in allowed_dimension_names:
            raise QueryPlanValidationError(
                f"Unknown filter dimension '{key}' for dataset {getattr(dataset, 'id', canonical['dataset_id'])}."
            )

    if "year" in normalized_filters:
        raw_year = normalized_filters["year"]
        if type(raw_year) is not int:
            raise QueryPlanValidationError("Filter 'year' must be an integer.")

    geography = normalized_filters.get("geography")
    if not isinstance(geography, str) or not geography.strip():
        raise QueryPlanValidationError("Filter 'municipality' must be a non-empty string.")

    return QueryPlan(
        dataset_id=getattr(dataset, "id", canonical["dataset_id"]),
        operation=canonical["operation"],
        filters=raw_filters,
        measure=canonical["measure"],
        grouping=tuple(canonical.get("grouping") or ()),
        ordering=tuple(canonical.get("ordering") or ()),
        limit=canonical.get("limit"),
        schema_version=schema_version,
    )


def _resolve_municipality_filter(value: str) -> str:
    candidate = str(value).strip()
    if not candidate:
        raise ValueError("Municipality name is required.")

    if candidate.isdigit():
        for municipality in municipalities():
            if municipality.code == candidate or municipality.code == f"K-{candidate}":
                return candidate
        raise ValueError(f"Unknown municipality code: {candidate}")

    municipality = find_municipality_local(candidate)
    if municipality is None:
        raise ValueError(f"Fant ikke kommunen «{candidate}».")
    code = municipality.code.removeprefix("K-")
    return code


def plan_from_population_question(question) -> QueryPlan:
    if isinstance(question, str):
        from .population import parse_population_question

        question = parse_population_question(question)

    if getattr(question, "compare_place", None):
        raise ValueError("Comparison plans are not supported in this implementation.")

    place = getattr(question, "place", None)
    if not place:
        raise ValueError("Population question requires a municipality.")
    year = getattr(question, "since", None)
    if year is None:
        year = datetime.now(UTC).year

    return QueryPlan(
        dataset_id="ssb-07459-population",
        operation="lookup",
        filters={"municipality": _resolve_municipality_filter(place), "year": int(year)},
        measure="population",
        grouping=(),
        ordering=(),
        limit=None,
        schema_version=1,
    )


def execute_query_plan(plan: QueryPlan | dict[str, Any] | str):
    validated = validate_query_plan(plan)
    municipality = _population_dataset_plan_filters(validated.filters).get("geography")
    if municipality is None:
        raise QueryPlanValidationError("Plan missing required filter: municipality")

    code = str(municipality)
    if code.isdigit() or code.startswith("K-"):
        normalized = code.removeprefix("K-")
        municipality_name = next(
            (
                item.name
                for item in municipalities()
                if item.code == normalized or item.code == f"K-{normalized}"
            ),
            None,
        )
        if municipality_name is None:
            raise QueryPlanValidationError(f"Unknown municipality code: {code}")
    else:
        municipality_name = find_municipality_local(code)
        if municipality_name is None:
            municipality_name = find_municipality(code)
        municipality_name = municipality_name.name

    since = validated.filters.get("year")
    result = analyze_population([municipality_name], since, provider=municipality_population)
    receipt = replace(result.receipt, query_plan_hash=validated.plan_hash())
    return AnalysisResult(title=result.title, receipt=receipt)


__all__ = [
    "QueryPlan",
    "QueryPlanValidationError",
    "canonicalize_plan",
    "execute_query_plan",
    "plan_from_population_question",
    "validate_query_plan",
]
