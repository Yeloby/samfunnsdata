"""Offline tests. Fixture shape captured from the official API; no live HTTP."""

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from samfunnsdata import cli, network
from samfunnsdata.cache import JsonCache
from samfunnsdata.catalog import SupportStatus, get_dataset, get_source
from samfunnsdata.concepts import find_concepts
from samfunnsdata.providers.norway import norges_bank as nb
from samfunnsdata.query_plan import (
    QueryPlan,
    execute_query_plan,
    plan_from_rate_question,
    validate_query_plan,
)
from samfunnsdata.questions import RateQuestion, parse_question
from samfunnsdata.results import AnalysisResult, DataReceipt

CSV = (Path(__file__).parent / "fixtures/norges_bank_policy_rate.csv").read_text()
LATEST = "\n".join([CSV.splitlines()[0], CSV.splitlines()[-1]]) + "\n"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected HTTP")
    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)
    network.set_mode(network.NetworkMode.ONLINE)
    yield
    network.set_mode(network.NetworkMode.ONLINE)


@pytest.fixture
def backend(monkeypatch, tmp_path):
    calls = []
    cache = JsonCache(tmp_path)
    monkeypatch.setattr(nb, "JsonCache", lambda: cache)

    def get(url, **kwargs):
        calls.append((url, kwargs))
        text = LATEST if kwargs["params"].get("lastNObservations") else CSV
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    return cache, calls


def plan(operation="history", since=2024):
    return plan_from_rate_question(RateQuestion(operation, since))


def test_official_fixture_semantics():
    observations = nb.parse_csv(CSV)
    assert len(observations) == 4
    assert observations[0].period == "2024-01-02"
    assert observations[-1].period == "2024-01-05"
    assert observations[0].source_value == "4.5"
    assert observations[0].usable_value == 4.5
    assert observations[0].status is None
    assert observations[0].calculation_method == ""
    # Jan 1 is not present: no substitution or fill.
    assert "2024-01-01" not in {o.period for o in observations}


def test_sort_without_interpolation():
    rows = CSV.splitlines()
    data = nb.parse_csv("\n".join([rows[0], rows[4], rows[1]]))
    assert [o.period for o in data] == ["2024-01-02", "2024-01-05"]


@pytest.mark.parametrize("old,new", [
    ("FREQ;", "FREQUENCY;"), ("B;Business", "M;Monthly"),
    ("KPRA;Key", "NOWA;Key"), ("SD;Policy", "ON;Policy"),
    ("R;Rate", "V;Volume"), (";E;End", ";A;Average"),
    (";2;E;", ";3;E;"), ("2024-01-02", "2024-02-30"),
    ("2024-01-02", "2024-01"), (";4.5;", ";NaN;"),
    (";4.5;", ";Infinity;"), (";4.5;", ";not-a-number;"),
])
def test_malformed_semantics_rejected(old, new):
    with pytest.raises(ValueError):
        nb.parse_csv(CSV.replace(old, new))


@pytest.mark.parametrize("text", ["", "<html>error</html>", CSV.splitlines()[0],
                                  CSV + CSV.splitlines()[1] + "\n",
                                  CSV.replace(";4.5;;", ";4.5;"),
                                  CSV.replace(";4.5;;", ";4.5;;;unexpected")])
def test_bad_shape_rejected(text):
    with pytest.raises(ValueError):
        nb.parse_csv(text)


@pytest.mark.parametrize("raw,value", [("0", 0), ("0.00", 0), ("", None), ("-0.25", -0.25)])
def test_source_values_preserved(raw, value):
    observation = nb.parse_csv(LATEST.replace(";4.5;", f";{raw};"))[0]
    assert observation.source_value == raw
    assert observation.usable_value == value


def test_calculation_method_not_confused_with_status():
    observation = nb.parse_csv(LATEST.replace(";4.5;;", ";4.5;E;Estimated"))[0]
    assert observation.source_value == "4.5"
    assert observation.calculation_method == "E"
    assert observation.status is None
    assert observation.usable_value is None


def test_optional_status_preserved_conservatively():
    rows = LATEST.splitlines()
    observation = nb.parse_csv(rows[0] + ";OBS_STATUS\n" + rows[1] + ";P\n")[0]
    assert observation.status == "P"
    assert observation.usable_value is None


@pytest.mark.parametrize("text", ["Hva er styringsrenta?", "Hva er styringsrenten?",
                                  "Vis styringsrenta", "Norges Banks styringsrente",
                                  "  Hva   er\u00a0styringsrenten?  "])
def test_latest_language_equivalence(text):
    assert "policy_rate" in find_concepts(text)
    assert plan_from_rate_question(parse_question(text)) == plan("latest", None)


@pytest.mark.parametrize("text", ["Styringsrente siden 2015", "Vis styringsrenten siden 2015",
                                  "Hvordan har styringsrenta utviklet seg siden 2015?"])
def test_history_language_equivalence(text):
    assert plan_from_rate_question(parse_question(text)) == plan("history", 2015)


def test_all_history_language():
    assert parse_question("Hvordan har styringsrenta utviklet seg?") == RateQuestion("history")


@pytest.mark.parametrize("text", ["Styringsrente siden", "Styringsrente siden 0000",
                                  "Styringsrenten i januar 2024", "Styringsrenten 30. februar 2024",
                                  "Forutsi styringsrenten", "Hva er boliglånsrenten?",
                                  "Styringsrenten https://evil.test", "Styringsrenten __import__('os')"])
def test_unsupported_language_fails_locally(text):
    with pytest.raises(ValueError):
        parse_question(text)


def test_local_plan_roundtrip_hash_and_validation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Planning must not call network boundary")
    monkeypatch.setattr(network, "request", forbidden)
    original = plan()
    restored = QueryPlan.from_json(original.to_json())
    assert validate_query_plan(restored) == original
    assert original.to_json() == restored.to_json()
    assert original.plan_hash() == restored.plan_hash()
    assert original.plan_hash() == original.plan_hash()
    assert "question" not in original.to_dict()


@pytest.mark.parametrize("changes", [
    {"dataset_id": "unknown"}, {"measure": "exchange_rate"}, {"operation": "forecast"},
    {"filters": {"since": True}}, {"filters": {"since": "2024"}},
    {"filters": {"since": 2024.5}}, {"filters": {"since": None}},
    {"filters": {"since": 0}}, {"filters": {"since": 10000}},
    {"filters": {"since": "2024-02-30"}}, {"filters": {"url": "https://evil.test"}},
    {"grouping": ["year"]}, {"ordering": ["date"]}, {"limit": 1},
    {"executor": "os:system"}, {"provider": "os"},
    {"operation": "latest", "filters": {"since": 2024}},
])
def test_invalid_plans_rejected_before_http(changes):
    data = plan().to_dict()
    data.update(changes)
    with pytest.raises(ValueError):
        execute_query_plan(data)


@pytest.mark.parametrize("support", [SupportStatus.DISCOVERED, SupportStatus.PLANNED])
def test_untrusted_status_rejected(support):
    dataset = replace(get_dataset(nb.DATASET_ID), support=support, adapter=None, interfaces=())
    with pytest.raises(ValueError, match="SUPPORTED"):
        validate_query_plan(plan(), dataset_override=dataset)


def test_catalog_truthful():
    dataset = get_dataset(nb.DATASET_ID)
    assert dataset.support == SupportStatus.SUPPORTED
    assert dataset.unit == "prosent"
    assert dataset.table_id == "IR/B.KPRA.SD.R"
    assert get_source("norges_bank").authority == "Norges Bank"


def test_result_receipt_cache_and_zero_http(backend, monkeypatch):
    _, calls = backend
    result = execute_query_plan(plan())
    assert isinstance(result, AnalysisResult)
    assert result.receipt.schema_version == "3"
    assert result.receipt.measure.unit == "prosent"
    assert result.series[0].derived_facts.change == 0
    assert result.series[0].derived_facts.change_unit == "prosentpoeng"
    assert result.receipt.query_plan_hash == plan().plan_hash()
    p = result.series[0].provenance
    assert p.network_occurred and not p.cache_hit and p.fetched_at
    assert p.content_hash is None
    assert p.requests[0].requested_host == "data.norges-bank.no"
    assert not p.requests[0].free_text
    assert DataReceipt.from_json(result.receipt.to_json()) == result.receipt
    assert result.receipt.to_json() == result.receipt.to_json()
    assert len(calls) == 1
    network.set_mode(network.NetworkMode.CACHE_ONLY)
    monkeypatch.setattr(network, "request", lambda *a, **kw: pytest.fail("Cache hit called HTTP boundary"))
    cached = execute_query_plan(plan())
    assert cached.series[0].source_observations == result.series[0].source_observations
    assert cached.series[0].provenance.cache_hit
    assert cached.series[0].provenance.fetched_at == p.fetched_at
    assert cached.series[0].provenance.network_occurred is False
    assert cached.series[0].provenance.requests == ()
    assert len(calls) == 1


def test_cache_only_miss_never_calls_http(backend, monkeypatch):
    network.set_mode(network.NetworkMode.CACHE_ONLY)
    monkeypatch.setattr(network, "request", lambda *a, **kw: pytest.fail("Cache miss called boundary"))
    with pytest.raises(network.CacheOnlyMiss):
        execute_query_plan(plan())


def test_corrupt_cache_is_miss(backend):
    cache, _ = backend
    execute_query_plan(plan())
    for path in cache.root.glob("*.json"):
        path.write_text("broken", encoding="utf-8")
    network.set_mode(network.NetworkMode.CACHE_ONLY)
    with pytest.raises(network.CacheOnlyMiss):
        execute_query_plan(plan())


def test_online_refreshes_latest(backend):
    _, calls = backend
    execute_query_plan(plan("latest", None))
    execute_query_plan(plan("latest", None))
    assert len(calls) == 2
    assert calls[0][0] == nb.URL
    assert calls[0][1]["params"] == {"format": "csv", "locale": "en", "lastNObservations": 1}


def test_missing_endpoint_never_falls_back(backend, monkeypatch):
    def get(url, **kwargs):
        text = CSV.replace("2024-01-05;4.5", "2024-01-05;")
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    result = execute_query_plan(plan())
    assert result.series[0].derived_facts.last_period == "2024-01-05"
    assert result.series[0].derived_facts.last_value is None
    assert result.series[0].derived_facts.change is None


@pytest.mark.parametrize("url", ["http://data.norges-bank.no/api", "https://evil.test/",
                                 "https://data.norges-bank.no:444/api", "https://user@data.norges-bank.no/api"])
def test_unsafe_destination_rejected(url):
    with pytest.raises(network.DestinationNotAllowed):
        network.request("norges_bank", "test", "GET", url)


def test_unsafe_redirect_rejected(monkeypatch, tmp_path):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return httpx.Response(302, headers={"location": "https://evil.test"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(network.DestinationNotAllowed):
        nb.policy_rate(cache=JsonCache(tmp_path))
    assert calls == [nb.URL]


def test_cli_receipt_and_cache_only(backend, monkeypatch, capsys, tmp_path):
    path = tmp_path / "receipt.json"
    monkeypatch.setattr("sys.argv", ["samfunnsdata", "rate", "--since", "2024", "--receipt", str(path)])
    assert cli.main() == 0
    assert "prosentpoeng" in capsys.readouterr().out
    assert json.loads(path.read_text())["query_plan_hash"] == plan().plan_hash()
    monkeypatch.setattr("sys.argv", ["samfunnsdata", "--cache-only", "rate", "--since", "2024"])
    assert cli.main() == 0
    assert "Lokal cache" in capsys.readouterr().out
    assert len(backend[1]) == 1


def test_cli_default_is_latest(backend, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["samfunnsdata", "rate"])
    assert cli.main() == 0
    assert "2024-01-05: 4,5 %" in capsys.readouterr().out


def test_fractional_change_is_percentage_points(backend, monkeypatch):
    def get(url, **kwargs):
        text = CSV.replace("2024-01-05;4.5", "2024-01-05;4.25")
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    result = execute_query_plan(plan())
    assert result.series[0].derived_facts.change == -0.25
    assert result.series[0].derived_facts.change_unit == "prosentpoeng"
    assert result.series[0].source_observations[-1].source_value == "4.25"


def test_flagged_latest_remains_latest(backend, monkeypatch):
    def get(url, **kwargs):
        text = LATEST.replace(";4.5;;", ";4.5;E;Estimated")
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    result = execute_query_plan(plan("latest", None))
    series = result.series[0]
    assert series.derived_facts.last_period == "2024-01-05"
    assert series.derived_facts.last_value is None
    assert series.source_observations[-1].calculation_method == "E"


def test_malformed_refresh_keeps_previous_cache(backend, monkeypatch):
    cache, _ = backend
    execute_query_plan(plan())
    before = {p.name: p.read_bytes() for p in cache.root.glob("*.json")}
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(
        200, text="<html>broken</html>", request=httpx.Request("GET", url)))
    with pytest.raises(ValueError):
        execute_query_plan(plan())
    assert before == {p.name: p.read_bytes() for p in cache.root.glob("*.json")}


@pytest.mark.parametrize("operation,since", [("latest", None), ("history", 2025)])
def test_response_must_match_requested_selection(backend, monkeypatch, operation, since):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(
        200, text=CSV, request=httpx.Request("GET", url)))
    with pytest.raises(ValueError):
        execute_query_plan(plan(operation, since))
    assert list(backend[0].root.glob("*.json")) == []


def test_new_receipt_cannot_claim_old_schema(backend):
    receipt = execute_query_plan(plan()).receipt
    with pytest.raises(ValueError, match="schema version"):
        replace(receipt, schema_version="2")
    with pytest.raises(ValueError, match="schema version"):
        replace(receipt, schema_version="99")
