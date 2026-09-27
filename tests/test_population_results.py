"""Offline contract, source fidelity and application/presentation boundaries."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from samfunnsdata import cli, gui_work, population_presentation
from samfunnsdata.charts import population_figure
from samfunnsdata.population import analyze_population
from samfunnsdata.providers.norway.ssb import Municipality, jsonstat_to_frame
from samfunnsdata.results import AnalysisResult, DataReceipt

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
TOKEN = SimpleNamespace(checkpoint=lambda: None)


def frame(
    values=(100, 120, 150), status=(None, "", ""), years=("2000", "2010", "2020")
):
    result = pd.DataFrame(
        {"Tid_code": years, "Tid": years, "value": values, "status": status}
    )
    result.attrs["jsonstat_metadata"] = {
        "label": "Kildetittel",
        "updated": "2026-01-01T00:00:00Z",
        "note": ["Original merknad"],
        "extension": {"test": 1},
    }
    return result


def analyze(data=None, places=("Ås",), since=None):
    data = frame() if data is None else data
    return analyze_population(
        places,
        since,
        used_at=NOW,
        provider=lambda name: (Municipality(f"K-{name}", name), data),
    )


def test_contract_structure_and_source_derived_separation():
    result = analyze()
    assert isinstance(result, AnalysisResult)
    assert result.schema_version == "1"
    assert result.receipt.schema_version == "2"
    assert result.chart_hint == "time_series"
    series = result.series[0]
    assert series.selection.municipality_code == "K-Ås"
    assert [o.source_value for o in series.source_observations] == [100, 120, 150]
    assert series.derived_facts.change == 50
    assert series.derived_facts.percent_change == 50
    assert result.receipt.measure.unit == "persons"
    assert result.receipt.measure.source_code == "Personer1"
    assert result.receipt.source.dataset_id == "07459"
    assert "<span" not in result.receipt.to_json()
    with pytest.raises(FrozenInstanceError):
        result.title = "changed"


def test_receipt_deterministic_roundtrip_and_explicit_unknowns():
    result = analyze()
    receipt = result.receipt
    assert receipt.to_json() == analyze().receipt.to_json()
    restored = DataReceipt.from_json(receipt.to_json())
    assert restored == receipt
    assert restored.to_json() == receipt.to_json()
    document = json.loads(receipt.to_json())
    assert document["used_at"] == "2026-09-22T12:00:00+00:00"
    assert document["source"]["license"] is None
    provenance = document["series"][0]["provenance"]
    for field in ("fetched_at", "cache_hit", "content_hash", "raw_data_reference"):
        assert provenance[field] is None
    assert provenance["source_updated_at"] == "2026-01-01T00:00:00Z"
    assert document["warnings"] == []
    assert "Ås" in receipt.to_json() and "\\u00c5" not in receipt.to_json()
    assert not any(
        marker in receipt.to_json() for marker in ("/home/", "PosixPath", "DataFrame")
    )


@pytest.mark.parametrize("kind", ["receipt", "result", "wire"])
def test_unknown_schema_rejected(kind):
    result = analyze()
    with pytest.raises(ValueError, match="schema version"):
        if kind == "receipt":
            replace(result.receipt, schema_version="99")
        elif kind == "result":
            replace(result, schema_version="99")
        else:
            DataReceipt.from_json(
                result.receipt.to_json().replace(
                    '"schema_version": "2"', '"schema_version": "99"'
                )
            )


def test_empty_result_and_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone"):
        replace(analyze().receipt, used_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="at least one series"):
        AnalysisResult("Empty", replace(analyze().receipt, series=()))


@pytest.mark.parametrize(
    "values,status,first,last,change,percent,warning_count",
    [
        ((0, 10, 20), (None, "", ""), 0, 20, 20, None, 1),
        ((20, 10, 0), (None, "", ""), 20, 0, -20, -100, 0),
        ((None, 10, 20), (None, "", ""), None, 20, None, None, 2),
        ((20, 10, None), (None, "", ""), 20, None, None, None, 2),
        ((100, 110, 120), ("p", "", ""), None, 120, None, None, 2),
        ((100, 110, 120), ("", "", "unknown"), 100, None, None, None, 2),
        ((100, None, 120), ("", "", ""), 100, 120, 20, 20, 1),
        ((100, 110, 120), ("", "p", ""), 100, 120, 20, 20, 1),
    ],
)
@pytest.mark.parametrize("places", [("Ås",), ("Ås", "Bergen", "Trondheim")])
def test_population_semantics(
    values, status, first, last, change, percent, warning_count, places
):
    result = analyze(frame(values, status), places)
    assert len(result.series) == len(places)
    for s in result.series:
        facts = s.derived_facts
        assert (
            facts.first_value,
            facts.last_value,
            facts.change,
            facts.percent_change,
        ) == (first, last, change, percent)
        assert [o.source_value for o in s.source_observations] == list(values)
        assert [o.status for o in s.source_observations] == list(status)
        assert (facts.first_year, facts.last_year) == ("2000", "2020")
        assert s.name in places
        assert len(s.warnings) == warning_count
    assert DataReceipt.from_json(result.receipt.to_json()) == result.receipt


def test_metadata_snapshot_survives_mutated_provider_attrs():
    data = frame()
    result = analyze(data)
    data.attrs["jsonstat_metadata"]["note"].append("mutated")
    data.loc[0, "value"] = 9999
    series = result.series[0]
    assert json.loads(series.provider_metadata_json)["note"] == ["Original merknad"]
    assert series.source_observations[0].source_value == 100


def test_unknown_metadata_and_absent_status_are_explicit():
    data = frame().drop(columns="status")
    data.attrs.clear()
    s = analyze(data).series[0]
    assert s.provider_metadata_json is None
    assert s.provenance.source_updated_at is None
    assert not s.status_available
    assert all(o.status is None for o in s.source_observations)
    # Unknown availability differs from known empty markers.
    assert analyze(frame(status=("", "", ""))).series[0].status_available


def test_period_filter_and_comparison_identity():
    frames = {"A": frame(), "B": frame(years=("1999", "2005", "2015"))}
    result = analyze_population(
        ["A", "B", "A"],
        2005,
        used_at=NOW,
        provider=lambda name: (Municipality(name, name), frames[name]),
    )
    assert result.series[0].source_returned_period == ("2000", "2020")
    assert [s.derived_facts.first_year for s in result.series] == [
        "2010",
        "2005",
        "2010",
    ]
    assert [s.derived_facts.last_year for s in result.series] == [
        "2020",
        "2015",
        "2020",
    ]
    assert len({s.id for s in result.series}) == 3
    assert result.warnings == ("Kommuneseriene har ulike faktiske perioder.",)
    assert all(
        s.selection.since == 2005 and s.selection.source_period == "*"
        for s in result.series
    )
    operations = [t.operation for t in result.receipt.transformations]
    assert operations.count("restrict_period") == 3
    assert operations[-1] == "compare_series"
    assert result.receipt.transformations[-1].outputs == ()
    with pytest.raises(ValueError, match="Ingen befolkningsdata"):
        analyze(since=9999)


def test_chart_csv_raw_and_receipt_share_source_and_calculations(tmp_path):
    result = analyze(frame((0, None, 50), ("", "", "p")), ("Ås", "Bergen"))
    series = [(s.name, s) for s in result.series]
    figure = population_figure(series, result.title)
    try:
        for line in figure.axes[0].lines:
            assert list(line.get_xdata()) == [2000, 2010, 2020]
            assert list(line.get_ydata()) == [0, None, None]
    finally:
        plt.close(figure)
    path = tmp_path / "population.csv"
    gui_work.export_csv(TOKEN, "population", series, path)
    csv = pd.read_csv(path)
    assert csv.columns.tolist() == ["Kommune", "År", "Innbyggere", "status"]
    assert csv["Innbyggere"].iloc[0] == 0
    assert pd.isna(csv["Innbyggere"].iloc[1])
    assert csv["Innbyggere"].iloc[2] == 50 and csv["status"].iloc[2] == "p"
    text, _ = gui_work.raw_text(TOKEN, "population", series)
    assert "kildeverdi: 50" in text
    assert "ikke beregnbart" in text
    json_path = tmp_path / "population.receipt.json"
    gui_work.export_receipt(TOKEN, result.receipt, json_path)
    assert DataReceipt.from_json(json_path.read_text()) == result.receipt
    human = population_presentation.receipt_text(result.receipt)
    for section in (
        "Kilde",
        "Utvalg",
        "Periode",
        "Måltall",
        "Henting/cache",
        "Beregninger",
        "Advarsler",
        "Tekniske detaljer",
    ):
        assert section in human
    assert "Ukjent / ikke registrert" in human


@pytest.mark.parametrize("command", ["population", "compare"])
def test_cli_consumes_application_result_and_exports_receipt(
    monkeypatch, capsys, tmp_path, command
):
    places = ["Ås"] if command == "population" else ["Ås", "Bergen", "Trondheim"]
    result = analyze(places=places)
    calls = []

    def service(selected, since, **kwargs):
        calls.append((selected, since))
        return result

    monkeypatch.setattr(cli, "analyze_population", service)
    path = tmp_path / "output.receipt.json"
    monkeypatch.setattr(
        "sys.argv",
        ["samfunnsdata", command, *places, "--since", "2000", "--receipt", str(path)],
    )
    assert cli.main() == 0
    assert calls == [(places, 2000)]
    text = capsys.readouterr().out
    assert "100 → 150" in text and "+50,0 %" in text
    assert DataReceipt.from_json(path.read_text()) == result.receipt


def test_cached_payload_never_acquires_false_fetch_time(tmp_path, monkeypatch):
    from samfunnsdata.cache import JsonCache
    from samfunnsdata.providers.norway import ssb

    payload = {
        "id": ["Tid"],
        "size": [2],
        "value": [0, 10],
        "dimension": {"Tid": {"category": {"index": ["2020", "2021"]}}},
    }
    client = ssb.SsbClient()
    client.cache = JsonCache(tmp_path)
    params = [("valueCodes[Region]", "K-1")]
    request = {"table": "07459", "params": params, "lang": "no"}
    path = client.cache.set("ssb-data", request, payload)
    original = path.read_bytes()
    monkeypatch.setattr(
        "httpx.get", lambda *a, **k: pytest.fail("Live request forbidden")
    )
    raw = client.get_data("07459", params)
    result = analyze(jsonstat_to_frame(raw))
    assert result.series[0].provenance.fetched_at is None
    assert result.series[0].provenance.cache_hit is None
    assert result.series[0].provenance.content_hash is None
    assert path.read_bytes() == original
    assert path.name not in result.receipt.to_json()
    assert str(Path(tmp_path)) not in result.receipt.to_json()


@pytest.mark.parametrize("cache_hit", [None, False, True])
def test_provenance_distinguishes_unknown_and_known_boolean(cache_hit):
    from samfunnsdata.results import Provenance

    result = analyze()
    provenance = Provenance(cache_hit=cache_hit, fetched_at=NOW)
    series = replace(
        result.series[0], provenance=provenance, provider_metadata_json="{}"
    )
    receipt = replace(result.receipt, series=(series,))
    decoded = DataReceipt.from_json(receipt.to_json())
    assert decoded.series[0].provenance.cache_hit is cache_hit
    assert decoded.series[0].provenance.fetched_at == NOW
    assert decoded.series[0].provider_metadata_json == "{}"
    with pytest.raises(ValueError, match="timezone"):
        replace(provenance, fetched_at=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("kind", ["csv", "receipt"])
def test_cancel_after_export_preparation_does_not_write(tmp_path, monkeypatch, kind):
    from concurrent.futures import CancelledError

    result = analyze()
    canceled = False

    def checkpoint():
        if canceled:
            raise CancelledError()

    token = SimpleNamespace(checkpoint=checkpoint)
    path = tmp_path / "canceled"
    if kind == "csv":
        concat = pd.concat

        def prepare(*args, **kwargs):
            nonlocal canceled
            combined = concat(*args, **kwargs)
            canceled = True
            return combined

        monkeypatch.setattr(pd, "concat", prepare)
        with pytest.raises(CancelledError):
            gui_work.export_csv(
                token, "population", [(s.name, s) for s in result.series], path
            )
    else:

        def prepare():
            nonlocal canceled
            encoded = result.receipt.to_json()
            canceled = True
            return encoded

        receipt = SimpleNamespace(to_json=prepare)
        with pytest.raises(CancelledError):
            gui_work.export_receipt(token, receipt, path)
    assert not path.exists()


@pytest.mark.parametrize("version", ["1", "2"])
def test_population_historical_wire_contract(version):
    """Golden wire captured from unchanged Milestone-I population contracts."""
    receipt = replace(
        analyze(frame((100, 0, None, 120), (None, "", "..", "P"),
                      ("2000", "2001", "2002", "2003"))).receipt,
        schema_version=version, application_version="compatibility-fixture",
    )
    golden = (Path(__file__).parent / f"fixtures/population_receipt_v{version}.json").read_text()
    assert receipt.to_json() == golden
    restored = DataReceipt.from_json(golden)
    assert restored.to_json() == golden
    assert restored.to_json() == restored.to_json()
    observations = restored.series[0].source_observations
    assert [o.source_value for o in observations] == [100, 0, None, 120]
    assert [o.usable_value for o in observations] == [100, 0, None, None]
    assert [o.status for o in observations] == [None, "", "..", "P"]
    provenance = json.loads(golden)["series"][0]["provenance"]
    assert ("network_mode" in provenance) == (version == "2")
