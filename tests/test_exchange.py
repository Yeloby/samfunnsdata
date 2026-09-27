"""Offline FX contract regressions, including the per-100 quotation trap."""

import csv
import io
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from samfunnsdata import cli, exchange_presentation, network
from samfunnsdata.cache import JsonCache
from samfunnsdata.catalog import SupportStatus, get_dataset
from samfunnsdata.providers.norway import norges_bank_exchange as nb
from samfunnsdata.query_plan import (
    QueryPlan,
    execute_query_plan,
    plan_from_exchange_question,
    validate_query_plan,
)
from samfunnsdata.questions import ExchangeQuestion, parse_question
from samfunnsdata.results import DataReceipt

CSV = (Path(__file__).parent / "fixtures/norges_bank_exchange.csv").read_text()


def fixture(currency="EUR", latest=False, **changes):
    reader = csv.DictReader(io.StringIO(CSV), delimiter=";")
    rows = [r for r in reader if r["BASE_CUR"] == currency]
    if latest:
        rows = rows[-1:]
    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=list(reader.fieldnames)
        + [k for k in changes if k not in reader.fieldnames],
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows({**r, **changes} for r in rows)
    return out.getvalue()


def plan(currency="EUR", operation="history", since=2024):
    return plan_from_exchange_question(ExchangeQuestion(currency, operation, since))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("Unexpected HTTP")

    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)
    network.set_mode(network.NetworkMode.ONLINE)
    yield
    network.set_mode(network.NetworkMode.ONLINE)


@pytest.fixture
def backend(monkeypatch, tmp_path):
    cache, calls = JsonCache(tmp_path / "cache"), []
    monkeypatch.setattr(nb, "JsonCache", lambda: cache)

    def get(url, **kwargs):
        calls.append((url, kwargs))
        currency = url.split("/")[-1].split(".")[1]
        return httpx.Response(
            200,
            text=fixture(currency, bool(kwargs["params"].get("lastNObservations"))),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", get)
    return cache, calls


@pytest.mark.parametrize(
    "currency,raw,basis,change",
    [
        ("EUR", "11.2815", 1, 0.0275),
        ("USD", "10.2971", 1, 0.0582),
        ("GBP", "13.0204", 1, 0.0976),
        ("DKK", "151.33", 100, 0.30),
        ("SEK", "101.14", 100, -0.48),
    ],
)
def test_source_unit_contract_and_receipt(backend, currency, raw, basis, change):
    result = execute_query_plan(plan(currency))
    series = result.series[0]
    assert series.source_observations[0].source_value == raw
    assert series.source_observations[0].usable_value == float(raw)
    assert series.source_observations[0].period == "2024-01-02"
    assert [o.period for o in series.source_observations] == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
    ]
    unit = f"NOK per {basis} {currency}"
    assert result.receipt.measure.unit == unit
    assert series.derived_facts.change == change
    assert series.derived_facts.change_unit == unit
    metadata = json.loads(series.provider_metadata_json)
    assert metadata["UNIT"] is None
    assert metadata["UNIT_MULT"] == ("2" if basis == 100 else "0")
    assert metadata["quotation_basis"] == basis
    assert metadata["presentation_transform"] == "identity"
    assert metadata["normalization"] is None
    assert metadata["QUOTE_CUR"] == "NOK" and metadata["BASE_CUR"] == currency
    expected_last = {
        "EUR": "11,309",
        "USD": "10,3553",
        "GBP": "13,118",
        "DKK": "151,63",
        "SEK": "100,66",
    }[currency]
    assert f"{basis} {currency} = {expected_last} NOK" in exchange_presentation.summary(
        result
    )
    assert unit in exchange_presentation.raw_text([(series.name, series)])[0]
    assert result.receipt.query_plan_hash == plan(currency).plan_hash()
    assert result.receipt.schema_version == "3"
    wire = result.receipt.to_json()
    assert DataReceipt.from_json(wire).to_json() == wire
    assert "/home/" not in wire and "question" not in wire
    request = series.provenance.requests[0]
    assert request.final_host == "data.norges-bank.no" and not request.free_text
    assert (
        backend[1][0][0]
        == f"https://data.norges-bank.no/api/data/EXR/B.{currency}.NOK.SP"
    )


@pytest.mark.parametrize(
    "text,currency,operation,since",
    [
        ("Hva er eurokursen?", "EUR", "latest", None),
        (" Hva  er EUR–kursen! ", "EUR", "latest", None),
        ("Hva er dollarkursen?", "USD", "latest", None),
        ("Vis pundkursen.", "GBP", "latest", None),
        ("Hva er kursen på svenske kroner?", "SEK", "latest", None),
        ("Vis DKK-kursen", "DKK", "latest", None),
        ("Vis eurokursen siden 2020", "EUR", "history", 2020),
        ("Hvordan har dollarkursen utviklet seg?", "USD", "history", None),
        ("Hvordan har SEK-kursen utviklet seg siden 2020?", "SEK", "history", 2020),
    ],
)
def test_local_language_and_plan(monkeypatch, text, currency, operation, since):
    monkeypatch.setattr(
        network, "request", lambda *a, **kw: pytest.fail("Planning called network")
    )
    question = parse_question(text)
    assert question == ExchangeQuestion(currency, operation, since)
    p = plan_from_exchange_question(question)
    assert validate_query_plan(QueryPlan.from_json(p.to_json())) == p
    assert QueryPlan.from_json(p.to_json()).plan_hash() == p.plan_hash()


@pytest.mark.parametrize(
    "text",
    [
        "Hva er CHF-kursen?",
        "100 euro til NOK",
        "EUR/USD",
        "Vis eurokursen i morgen",
        "Vis eurokursen siden 0000",
        "Vis eurokursen siden 01/02/2020",
        "Gjennomsnittlig eurokurs",
        "Vis eurokursen månedlig",
        "Forutsi dollarkursen",
    ],
)
def test_unsupported_question(text):
    with pytest.raises(ValueError):
        parse_question(text)


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "forecast"},
        {"measure": "policy_rate"},
        {"provider": "os"},
        {"executor": "os:system"},
        {"url": "https://evil.test"},
        {"grouping": ["year"]},
        {"ordering": ["date"]},
        {"limit": 1},
        *(
            {"filters": f}
            for f in [
                {},
                {"currency": "CHF"},
                {"currency": []},
                {"currency": "EUR/../USD"},
                {"currency": "eur"},
                {"currency": "EUR", "since": None},
                {"currency": "EUR", "since": True},
                {"currency": "EUR", "since": 0},
                {"currency": "EUR", "since": "2020"},
                {"currency": "EUR", "since": 10000},
                {"currency": "EUR", "url": "https://evil.test"},
            ]
        ),
        {"operation": "latest"},
        {"dataset_id": "ssb-10580-unemployment"},
    ],
)
def test_bad_plan_before_http(change):
    p = plan().to_dict()
    p.update(change)
    with pytest.raises(ValueError):
        execute_query_plan(p)


@pytest.mark.parametrize("status", [SupportStatus.DISCOVERED, SupportStatus.PLANNED])
def test_untrusted_catalog(status):
    dataset = replace(
        get_dataset(nb.DATASET_ID), support=status, adapter=None, interfaces=()
    )
    with pytest.raises(ValueError):
        validate_query_plan(plan(), dataset_override=dataset)


def test_supported_metadata_cannot_choose_executor():
    p = replace(plan(), dataset_id="remote-fx")
    with pytest.raises(ValueError, match="executor"):
        validate_query_plan(
            p,
            dataset_override={
                "id": "remote-fx",
                "support": SupportStatus.SUPPORTED,
                "measures": ["exchange_rate"],
            },
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"FREQ": "M"},
        {"BASE_CUR": "USD"},
        {"QUOTE_CUR": "EUR"},
        {"TENOR": "XX"},
        {"UNIT_MULT": "2"},
        {"DECIMALS": "2"},
        {"COLLECTION": "E"},
        {"CALCULATED": "true"},
        {"TIME_PERIOD": "2024-02-30"},
        {"TIME_PERIOD": "2024-01"},
        {"OBS_VALUE": "NaN"},
        {"OBS_VALUE": "inf"},
        {"OBS_VALUE": "1,5"},
        {"UNKNOWN": "x"},
    ],
)
def test_wrong_semantics(changes):
    with pytest.raises(ValueError):
        nb.parse_csv(fixture(**changes), "EUR")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "<html>error</html>",
        CSV,
        fixture() + fixture().splitlines()[1] + "\n",
        fixture().replace(";11.2815", ""),
        fixture().replace(";11.2815", ";11.2815;extra"),
    ],
)
def test_invalid_shape(text):
    with pytest.raises(ValueError):
        nb.parse_csv(text, "EUR")


@pytest.mark.parametrize("raw", ["0", "0.00", "", "11.2815"])
@pytest.mark.parametrize("method", ["", "N", "E", "UNKNOWN"])
@pytest.mark.parametrize("status", ["", "P"])
def test_missing_zero_and_flags(raw, method, status):
    observation = nb.parse_csv(
        fixture(latest=True, OBS_VALUE=raw, CALC_METHOD=method, OBS_STATUS=status),
        "EUR",
    )[0]
    assert observation.source_value == raw
    assert observation.calculation_method == method and observation.status == status
    expected = float(raw) if raw and method in ("", "N") and not status else None
    assert observation.usable_value == expected


def test_cache_exact_keys_and_no_http(backend, monkeypatch):
    cache, calls = backend
    selections = [
        plan(c, o, y)
        for c, o, y in [
            ("EUR", "latest", None),
            ("USD", "latest", None),
            ("EUR", "history", None),
            ("EUR", "history", 2024),
        ]
    ]
    original = [execute_query_plan(p) for p in selections]
    assert len(list(cache.root.glob("*.json"))) == 4
    original[0] = execute_query_plan(selections[0])
    assert len(calls) == 5
    network.set_mode(network.NetworkMode.CACHE_ONLY)
    monkeypatch.setattr(
        network, "request", lambda *a, **kw: pytest.fail("Cache called network")
    )
    for p, result in zip(selections, original, strict=True):
        cached = execute_query_plan(p).series[0]
        assert cached.source_observations == result.series[0].source_observations
        assert cached.provenance.fetched_at == result.series[0].provenance.fetched_at
        assert cached.provenance.cache_hit and not cached.provenance.network_occurred
        assert cached.provenance.requests == ()
    for p in [plan("DKK"), plan("EUR", "history", 2023)]:
        with pytest.raises(network.CacheOnlyMiss):
            execute_query_plan(p)


@pytest.mark.parametrize(
    "corruption",
    ["broken", "{}", '{"version":1,"csv":"invalid","fetched_at":"invalid"}'],
)
def test_corrupt_cache(backend, corruption):
    execute_query_plan(plan())
    for p in backend[0].root.glob("*.json"):
        p.write_text(corruption)
    network.set_mode(network.NetworkMode.CACHE_ONLY)
    with pytest.raises(network.CacheOnlyMiss):
        execute_query_plan(plan())


@pytest.mark.parametrize("failure", ["malformed", "http", "redirect", "selection"])
def test_failed_refresh_preserves_cache(backend, monkeypatch, failure):
    execute_query_plan(plan())
    before = {p.name: p.read_bytes() for p in backend[0].root.glob("*.json")}

    def get(url, **kw):
        if failure == "http":
            return httpx.Response(503, request=httpx.Request("GET", url))
        if failure == "redirect":
            return httpx.Response(
                302,
                headers={"location": "https://evil.test"},
                request=httpx.Request("GET", url),
            )
        text = "bad" if failure == "malformed" else fixture(TIME_PERIOD="2023-01-01")
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(ValueError):
        execute_query_plan(plan())
    assert before == {p.name: p.read_bytes() for p in backend[0].root.glob("*.json")}


@pytest.mark.parametrize("operation,since", [("latest", None), ("history", 2024)])
@pytest.mark.parametrize(
    "changes", [{"OBS_VALUE": ""}, {"CALC_METHOD": "E"}, {"OBS_STATUS": "P"}]
)
def test_unusable_endpoints_never_fallback(
    backend, monkeypatch, operation, since, changes
):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200,
            text=fixture(latest=operation == "latest", **changes),
            request=httpx.Request("GET", url),
        ),
    )
    series = execute_query_plan(plan("EUR", operation, since)).series[0]
    assert series.derived_facts.last_period == "2024-01-05"
    assert (
        series.derived_facts.last_value is None and series.derived_facts.change is None
    )


@pytest.mark.parametrize("options", [[], ["--history"], ["--since", "2024"]])
def test_cli_and_receipt_cache(backend, monkeypatch, capsys, tmp_path, options):
    path = tmp_path / "receipt.json"
    monkeypatch.setattr(
        "sys.argv",
        ["samfunnsdata", "exchange", "DKK", *options, "--receipt", str(path)],
    )
    assert cli.main() == 0
    assert "100 DKK = 151,63 NOK" in capsys.readouterr().out
    receipt = DataReceipt.from_json(path.read_text())
    assert receipt.measure.unit == "NOK per 100 DKK"
    monkeypatch.setattr(
        "sys.argv", ["samfunnsdata", "--cache-only", "exchange", "DKK", *options]
    )
    assert cli.main() == 0 and len(backend[1]) == 1


@pytest.mark.parametrize(
    "args", [["CHF"], ["EUR", "--since", "0"], ["EUR", "--cache-only"]]
)
def test_cli_error(monkeypatch, args, backend):
    monkeypatch.setattr("sys.argv", ["samfunnsdata", "exchange", *args])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


@pytest.mark.parametrize("index", [0, -1])
@pytest.mark.parametrize(
    "field,value", [("OBS_VALUE", ""), ("CALC_METHOD", "E"), ("OBS_STATUS", "P")]
)
def test_actual_endpoint_only_is_unusable(backend, monkeypatch, index, field, value):
    reader = csv.DictReader(io.StringIO(fixture()), delimiter=";")
    rows = list(reader)
    fields = list(reader.fieldnames)
    if field not in fields:
        fields.append(field)
    rows[index][field] = value
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200, text=out.getvalue(), request=httpx.Request("GET", url)
        ),
    )
    series = execute_query_plan(plan()).series[0]
    assert sum(o.usable_value is not None for o in series.source_observations) == 3
    assert series.source_observations[index].usable_value is None
    assert series.derived_facts.change is None
    assert series.derived_facts.first_period == "2024-01-02"
    assert series.derived_facts.last_period == "2024-01-05"


@pytest.mark.parametrize("operation,since", [("latest", None), ("history", 2025)])
def test_selection_response_validation_before_cache(
    backend, monkeypatch, operation, since
):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200, text=fixture(), request=httpx.Request("GET", url)
        ),
    )
    with pytest.raises(ValueError):
        execute_query_plan(plan("EUR", operation, since))
    assert list(backend[0].root.glob("*.json")) == []


def test_presentation_keeps_source_precision(backend, monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200,
            text=fixture(latest=True, OBS_VALUE="100.1234"),
            request=httpx.Request("GET", url),
        ),
    )
    result = execute_query_plan(plan("EUR", "latest", None))
    assert "1 EUR = 100,1234 NOK" in exchange_presentation.summary(result)
    assert result.series[0].source_observations[0].source_value == "100.1234"
