"""Policy-rate questions use the existing real GTK background controller."""

from threading import Event, get_ident
from types import SimpleNamespace

import httpx
import pytest
from test_gui_jobs import pump_until
from test_norges_bank import CSV, LATEST

from samfunnsdata import gui, network
from samfunnsdata.cache import JsonCache
from samfunnsdata.providers.norway import norges_bank as nb
from samfunnsdata.results import DataReceipt


@pytest.fixture
def provider(monkeypatch, tmp_path):
    network.set_mode(network.NetworkMode.ONLINE)
    threads = []
    cache = JsonCache(tmp_path / "cache")
    monkeypatch.setattr(nb, "JsonCache", lambda: cache)
    def get(url, **kwargs):
        threads.append(get_ident())
        text = LATEST if kwargs["params"].get("lastNObservations") else CSV
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    yield threads
    network.set_mode(network.NetworkMode.ONLINE)


def test_question_background_receipt_and_exports(window, provider, monkeypatch, tmp_path):
    window.question.set_text("Vis styringsrenten siden 2024")
    window.on_question(None)
    pump_until(lambda: not window.jobs.active)
    assert provider and all(thread != get_ident() for thread in provider)
    assert window.current_kind == "rate"
    assert "prosentpoeng" in window.result.get_text()
    assert window.receipt_button.get_sensitive()
    shown = []
    monkeypatch.setattr(gui, "text_window", lambda *args: shown.append((get_ident(), args[-1])))
    window.on_show_receipt(None)
    pump_until(lambda: not window.jobs.active)
    assert shown[0][0] == get_ident()
    assert DataReceipt.from_json(shown[0][1]) == window.current_result.receipt
    window.on_show_raw(None)
    pump_until(lambda: not window.jobs.active)
    assert "2024-01-02" in shown[-1][1]
    csv_path = tmp_path / "rate.csv"
    dialog = SimpleNamespace(save_finish=lambda _: SimpleNamespace(get_path=lambda: str(csv_path)))
    window.on_export_finished(dialog, None)
    pump_until(lambda: not window.jobs.active)
    assert "Styringsrente (%)" in csv_path.read_text(encoding="utf-8-sig")
    path = tmp_path / "rate.receipt.json"
    dialog = SimpleNamespace(save_finish=lambda _: SimpleNamespace(get_path=lambda: str(path)))
    window.on_receipt_export_finished(dialog, None, window.current_result.receipt, window.jobs.generation)
    pump_until(lambda: not window.jobs.active)
    assert DataReceipt.from_json(path.read_text()) == window.current_result.receipt


@pytest.mark.parametrize("action", ["cancel", "replace", "close"])
def test_stale_rate_result_not_delivered(window, provider, monkeypatch, action):
    entered, release = Event(), Event()
    original = nb.policy_rate
    count = 0
    def blocking(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(nb, "policy_rate", blocking)
    window.question.set_text("Styringsrente siden 2024")
    window.on_question(None)
    try:
        pump_until(entered.is_set)
        if action == "cancel":
            window.on_cancel(None)
        elif action == "close":
            window.destroy()
        else:
            window.question.set_text("Hva er styringsrenta?")
            window.on_question(None)
            pump_until(lambda: not window.jobs.active)
            assert window.current_result.series[0].selection.operation == "latest"
    finally:
        release.set()
    pump_until(lambda: window.jobs.outstanding == 0)
    if action == "replace":
        assert window.current_result.series[0].selection.operation == "latest"
    else:
        assert window.current_result is None


def test_catalog_contains_supported_rate(window):
    from samfunnsdata.navigation import catalog_window

    catalog = catalog_window(window)
    items = [item for item in catalog.catalog_matches if item.id == nb.DATASET_ID]
    assert len(items) == 1
    assert "GUI" in items[0].support_label
