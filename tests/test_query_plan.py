import json

import pytest

from samfunnsdata import catalog
from samfunnsdata.catalog import SupportStatus, get_dataset
from samfunnsdata.population import analyze_population, parse_population_question
from samfunnsdata.providers.norway.ssb import municipality_population
from samfunnsdata.query_plan import (
    QueryPlan,
    QueryPlanValidationError,
    execute_query_plan,
    plan_from_population_question,
    validate_query_plan,
)


def _valid_population_plan(**overrides):
    plan = {
        "schema_version": 1,
        "dataset_id": "ssb-07459-population",
        "operation": "lookup",
        "filters": {"municipality": "5001", "year": 2024},
        "measure": "population",
        "grouping": [],
        "ordering": [],
        "limit": None,
    }
    plan.update(overrides)
    return plan


def test_query_plan_round_trip_and_hash():
    plan = QueryPlan(
        dataset_id="ssb-07459-population",
        operation="lookup",
        filters={"municipality": "5001", "year": 2024},
        measure="population",
        grouping=(),
        ordering=(),
        limit=None,
    )
    encoded = plan.to_json()
    loaded = QueryPlan.from_json(encoded)
    assert loaded == plan
    assert plan.canonical_json() == loaded.canonical_json()
    assert len(plan.plan_hash()) == 64
    assert plan.plan_hash() == loaded.plan_hash()


def test_query_plan_rejects_unsupported_schema_version():
    with pytest.raises(QueryPlanValidationError, match="schema"):
        validate_query_plan(_valid_population_plan(schema_version=99))


def test_query_plan_rejects_unknown_dataset():
    with pytest.raises(QueryPlanValidationError, match="dataset"):
        validate_query_plan(_valid_population_plan(dataset_id="missing-dataset"))


def test_query_plan_rejects_discovered_dataset():
    dataset = get_dataset("ssb-07459-population")
    assert dataset.support == SupportStatus.SUPPORTED
    discovered = {**dataset.__dict__, "support": SupportStatus.DISCOVERED}
    with pytest.raises(QueryPlanValidationError, match="SUPPORTED|supported"):
        validate_query_plan(_valid_population_plan(), dataset_override=discovered)


def test_query_plan_rejects_planned_dataset():
    dataset = get_dataset("ssb-07459-population")
    planned = {**dataset.__dict__, "support": SupportStatus.PLANNED}
    with pytest.raises(QueryPlanValidationError, match="SUPPORTED|supported"):
        validate_query_plan(_valid_population_plan(), dataset_override=planned)


def test_query_plan_rejects_unsupported_operation():
    with pytest.raises(QueryPlanValidationError, match="Unsupported operation"):
        validate_query_plan(_valid_population_plan(operation="aggregate"))


def test_query_plan_rejects_unknown_measure():
    with pytest.raises(QueryPlanValidationError, match="measure"):
        validate_query_plan(_valid_population_plan(measure="not-real"))


def test_query_plan_rejects_unknown_filter_dimension():
    with pytest.raises(QueryPlanValidationError, match="filter|dimension"):
        validate_query_plan(_valid_population_plan(filters={"municipality": "5001", "year": 2024, "alien": "value"}))


def test_query_plan_rejects_missing_required_population_selection():
    with pytest.raises(QueryPlanValidationError, match="municipality"):
        validate_query_plan(_valid_population_plan(filters={"year": 2024}))


def test_query_plan_rejects_invalid_value_types():
    with pytest.raises(QueryPlanValidationError, match="municipality"):
        validate_query_plan(_valid_population_plan(filters={"municipality": "   ", "year": 2024}))

    with pytest.raises(QueryPlanValidationError, match="year|integer"):
        validate_query_plan(_valid_population_plan(filters={"municipality": "5001", "year": "not-a-year"}))


def test_population_question_creates_expected_plan():
    question = parse_population_question("Vis befolkningen i Trondheim i 2024")
    plan = plan_from_population_question(question)
    assert plan.dataset_id == "ssb-07459-population"
    assert plan.operation == "lookup"
    assert plan.measure == "population"
    assert plan.filters["municipality"] == "5001"
    assert plan.filters["year"] == 2024


def test_query_plan_validation_and_planning_are_local_only(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("Network access forbidden during validation or planning")

    monkeypatch.setattr("samfunnsdata.network.request", fail_network)

    validate_query_plan(_valid_population_plan())
    plan = plan_from_population_question(parse_population_question("Vis befolkningen i Trondheim i 2024"))
    validate_query_plan(plan)
    assert plan.dataset_id == "ssb-07459-population"


def test_population_plan_construction_uses_local_municipality_lookup_only(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("Network access forbidden during planning")

    monkeypatch.setattr("samfunnsdata.network.request", fail_network)

    plan = plan_from_population_question(parse_population_question("Vis befolkningen i Trondheim i 2024"))

    assert plan.dataset_id == "ssb-07459-population"
    assert plan.filters["municipality"] == "5001"
    assert plan.filters["year"] == 2024


def test_remote_metadata_cannot_create_executable_binding():
    with pytest.raises(TypeError, match="SupportStatus|støttet|supported"):
        catalog._normalize_remote_support("supported")

    with pytest.raises(TypeError, match="SupportStatus|støttet|supported"):
        catalog.Dataset(
            id="ssb-remote-test",
            provider="ssb",
            title="Eksempel",
            topic="test",
            source="SSB",
            geography=(),
            time_resolution="year",
            dimensions=("geography", "year"),
            unit="persons",
            description="",
            period="2024",
            measures=("population",),
            definition="",
            support="supported",
            adapter="samfunnsdata.providers.norway.ssb:municipality_population",
            interfaces=("python",),
            table_id="99999",
        )


def test_execute_query_plan_uses_local_mapping_and_produces_result():
    plan = QueryPlan(
        dataset_id="ssb-07459-population",
        operation="lookup",
        filters={"municipality": "5001", "year": 2025},
        measure="population",
    )
    result = execute_query_plan(plan)
    assert result.title
    assert result.receipt.schema_version in {"1", "2"}
    assert result.receipt.query_plan_hash == plan.plan_hash()
    assert result.receipt.series
    assert result.receipt.series[0].provenance.network_occurred is not None
    assert "question" not in json.dumps(result.receipt.to_dict()).lower()


def test_execute_query_plan_preserves_existing_population_result_semantics():
    question = parse_population_question("Vis befolkningen i Trondheim i 2025")
    plan = plan_from_population_question(question)
    baseline = analyze_population(["Trondheim"], 2025, provider=municipality_population)
    result = execute_query_plan(plan)

    assert result.title == baseline.title
    assert result.receipt.source == baseline.receipt.source
    assert result.receipt.measure == baseline.receipt.measure
    assert result.receipt.series[0].derived_facts == baseline.receipt.series[0].derived_facts


@pytest.mark.parametrize("overrides", [
    {"grouping": ["year"]},
    {"ordering": ["year"]},
    {"limit": 1},
    {"schema_version": True},
    {"schema_version": 1.5},
    {"schema_version": "1"},
    {"filters": {"municipality": "5001", "year": True}},
    {"filters": {"municipality": "5001", "year": 2024.5}},
    {"filters": {"municipality": "5001", "year": "2024"}},
    {"filters": {"municipality": None, "year": 2024}},
    {"filters": {"municipality": ["5001"], "year": 2024}},
    {"filters": {"municipality": "5001", "place": "Oslo", "year": 2024}},
    {"filters": []},
    {"grouping": "year"},
    {"ordering": None},
    {"unexpected": "ignored previously"},
])
def test_invalid_plans_fail_before_provider_access(monkeypatch, overrides):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid plan reached provider")

    monkeypatch.setattr("samfunnsdata.query_plan.municipality_population", forbidden)
    monkeypatch.setattr("samfunnsdata.query_plan.municipalities", forbidden)
    with pytest.raises(QueryPlanValidationError):
        execute_query_plan(_valid_population_plan(**overrides))


@pytest.mark.parametrize("payload", ['[]', 'null', '42', '{', '{"dataset_id": null}'])
def test_malformed_wire_plan_has_validation_error(payload):
    with pytest.raises(QueryPlanValidationError):
        QueryPlan.from_json(payload)


@pytest.mark.parametrize("alias", ["municipality", "geography", "place"])
def test_all_municipality_aliases_execute(monkeypatch, alias):
    from types import SimpleNamespace

    import pandas as pd

    calls = []

    def provider(place):
        calls.append(place)
        return SimpleNamespace(name=place, code="5001"), pd.DataFrame({
            "Tid_code": ["2024", "2025"], "value": [100, 110],
        })

    monkeypatch.setattr("samfunnsdata.query_plan.municipality_population", provider)
    plan = QueryPlan.from_json(_valid_population_plan(
        filters={alias: "Trondheim", "year": 2024},
    ))
    result = execute_query_plan(plan)
    assert len(calls) == 1
    assert calls[0].casefold() == "trondheim"
    assert result.receipt.query_plan_hash == plan.plan_hash()


def test_other_supported_dataset_has_no_population_executor():
    dataset = get_dataset("ssb-07459-population")
    other = {**dataset.__dict__, "id": "other-supported"}
    with pytest.raises(QueryPlanValidationError, match="executor"):
        validate_query_plan(_valid_population_plan(dataset_id="other-supported"),
                            dataset_override=other)
