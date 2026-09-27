"""Existing GUI calculations/presentation preparation, without GTK widgets.

Population uses the application result contract. Other analyses retain private
presentation dictionaries. Providers and statistical rules remain unchanged.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

import matplotlib
import pandas as pd

# GUI charts are rasterized off-screen; never create a GTK matplotlib canvas.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import exchange_presentation, population_presentation, rate_presentation
from .analysis import (
    align_election_series,
    format_number,
    observation_value,
)
from .charts import election_figure, population_figure
from .population import analyze_population
from .providers.norway.elections import (
    municipality_party_history,
    storting_party_history,
)
from .providers.norway.nav import municipality_unemployment_since
from .providers.norway.ssb import municipality_population
from .results import PopulationSeries

_chart_lock = Lock()
# NAV's existing FileCache publishes CSV files in place. Keep GUI fetch+parse
# calls serial so concurrent requests cannot read a partially written CSV.
_nav_lock = Lock()


@contextmanager
def chart_session(token):
    token.checkpoint()
    with _chart_lock:
        token.checkpoint()
        previous = set(plt.get_fignums())
        try:
            yield
        finally:
            for number in set(plt.get_fignums()) - previous:
                plt.close(number)
    token.checkpoint()


def render_chart(fig):
    """Called inside chart_session; bytes outlive the unique temporary file."""
    with tempfile.NamedTemporaryFile(
        prefix="samfunnsdata-chart-", suffix=".png"
    ) as file:
        fig.savefig(file.name, dpi=180)
        return Path(file.name).read_bytes()


def population(token, place, compare_place, since):
    places = [place, compare_place] if compare_place else [place]
    result = analyze_population(places, since, provider=municipality_population,
                                checkpoint=token.checkpoint)
    first = result.series[0]
    facts = first.derived_facts
    chart_series = [(s.name, s) for s in result.series]
    view = {
        "analysis_result": result,
        "status": f"{first.name} · {facts.first_year}–{facts.last_year}",
        "source": "Kilde: Statistisk sentralbyrå · Tabell 07459\n" + population_presentation.source_activity(result),
        "result": (True, population_presentation.gui_summary(result)),
        "series": chart_series,
        "kind": "population",
    }
    with chart_session(token):
        fig = population_figure(chart_series, result.title)
        view["chart"] = render_chart(fig)
    token.checkpoint()
    return view


def _time_series_chart(token, result, ylabel):
    series = result.series[0]
    with chart_session(token):
        fig, ax = plt.subplots(figsize=(12, 6))
        # Points only: do not visually interpolate non-published days.
        ax.plot(pd.to_datetime([o.period for o in series.source_observations]),
                [o.usable_value if o.usable_value is not None else float("nan")
                 for o in series.source_observations], linestyle="none", marker=".")
        ax.set_title(result.title)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Observasjonsdato")
        fig.tight_layout()
        return render_chart(fig)


def rate_question(token, question):
    from .query_plan import execute_query_plan, plan_from_rate_question

    result = execute_query_plan(plan_from_rate_question(question), checkpoint=token.checkpoint)
    series = result.series[0]
    chart = _time_series_chart(token, result, "Styringsrente (%)")
    token.checkpoint()
    return {"analysis_result": result, "status": result.title,
            "source": "Kilde: Norges Bank · IR/B.KPRA.SD.R\n" + population_presentation.source_activity(result),
            "result": (False, rate_presentation.summary(result)),
            "series": [(series.name, series)], "kind": "rate", "chart": chart}


def exchange_question(token, question):
    from .query_plan import execute_query_plan, plan_from_exchange_question

    result = execute_query_plan(plan_from_exchange_question(question), checkpoint=token.checkpoint)
    series = result.series[0]
    chart = _time_series_chart(token, result, result.receipt.measure.unit)
    token.checkpoint()
    return {"analysis_result": result, "status": result.title,
            "source": "Kilde: Norges Bank · EXR/" + series.selection.series_code + "\n" + population_presentation.source_activity(result),
            "result": (False, exchange_presentation.summary(result)),
            "series": [(series.name, series)], "kind": "exchange", "chart": chart}


def unemployment_question(token, question):
    view = {}
    token.checkpoint()
    since = question.since
    if since is None:
        since = 1995
    token.checkpoint()
    with _nav_lock:
        token.checkpoint()
        frame = municipality_unemployment_since(question.municipality, since)
    token.checkpoint()
    first = frame.iloc[0]
    last = frame.iloc[-1]
    first_period = f"{int(first['year'])}-{int(first['month']):02d}"
    last_period = f"{int(last['year'])}-{int(last['month']):02d}"
    latest_unemployed = observation_value(last, "unemployed")
    latest_percent = last["percent"]
    if latest_percent is not None and (not pd.isna(latest_percent)):
        percent_text = f"{float(latest_percent):.1f}".replace(".", ",") + " %"
    else:
        percent_text = "ikke oppgitt"
    view["status"] = (
        f"Arbeidsledighet · {question.municipality} · {first_period}–{last_period}"
    )
    latest_text = format_number(latest_unemployed, ",.0f")
    view["result"] = (
        True,
        f"<b>Registrerte helt ledige i {question.municipality}</b>\n<span size='x-large' weight='bold'>{latest_text}</span>\nAndel av arbeidsstyrken: {percent_text}\n\nSiste observasjon: {last_period}\nMetode: NAVs månedlige kommunestatistikk for registrerte helt ledige.",
    )
    view["series"] = [(question.municipality, frame)]
    view["kind"] = "unemployment"
    dates = pd.to_datetime(
        {
            "year": frame["year"].astype(int),
            "month": frame["month"].astype(int),
            "day": 1,
        }
    )
    with chart_session(token):
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(dates, frame["percent"])
        ax.set_title(f"Registrerte helt ledige i {question.municipality}")
        ax.set_xlabel("Tid")
        ax.set_ylabel("Prosent av arbeidsstyrken")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        view["chart"] = render_chart(fig)
    view["source"] = "Kilde: NAV · registrerte helt ledige"
    token.checkpoint()
    return view


def election_comparison(token, question):
    view = {}
    token.checkpoint()
    first_frame = storting_party_history(
        municipality=question.municipality,
        party_code=question.first_party_code,
        since=question.since,
    )
    token.checkpoint()
    second_frame = storting_party_history(
        municipality=question.municipality,
        party_code=question.second_party_code,
        since=question.since,
    )
    token.checkpoint()
    first_comparison, second_comparison = align_election_series(
        first_frame, second_frame
    )
    first_name = str(first_comparison.iloc[-1]["party_name"])
    second_name = str(second_comparison.iloc[-1]["party_name"])
    first_start = float(first_comparison.iloc[0]["percent"])
    first_end = float(first_comparison.iloc[-1]["percent"])
    second_start = float(second_comparison.iloc[0]["percent"])
    second_end = float(second_comparison.iloc[-1]["percent"])
    first_change = first_end - first_start
    second_change = second_end - second_start
    latest_difference = first_end - second_end

    def pct(value):
        return f"{value:.2f}".replace(".", ",")

    def pp(value):
        return f"{value:+.2f}".replace(".", ",")

    first_year = min(
        int(first_comparison.iloc[0]["year"]), int(second_comparison.iloc[0]["year"])
    )
    last_year = max(
        int(first_comparison.iloc[-1]["year"]), int(second_comparison.iloc[-1]["year"])
    )
    view["status"] = (
        f"{first_name} og {second_name} · {question.municipality} · {first_year}–{last_year}"
    )
    view["result"] = (
        True,
        f"<b>{first_name}</b>\n<span size='x-large' weight='bold'>{pct(first_start)} % → {pct(first_end)} %</span>\nEndring: {pp(first_change)} prosentpoeng\n\n<b>{second_name}</b>\n<span size='x-large' weight='bold'>{pct(second_start)} % → {pct(second_end)} %</span>\nEndring: {pp(second_change)} prosentpoeng\n\nSammenligningen bruker felles valgår.\nForskjell i {last_year}: {pct(abs(latest_difference))} prosentpoeng\n\nMetode: Partienes stemmeandeler ved stortingsvalg i {question.municipality}.",
    )
    view["series"] = [(first_name, first_frame), (second_name, second_frame)]
    view["kind"] = "election"
    with chart_session(token):
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(
            first_frame["year"], first_frame["percent"], marker="o", label=first_name
        )
        ax.plot(
            second_frame["year"], second_frame["percent"], marker="o", label=second_name
        )
        ax.set_title(
            f"{first_name} og {second_name} i {question.municipality} – stortingsvalg"
        )
        ax.set_xlabel("Valgår")
        ax.set_ylabel("Prosent")
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        view["chart"] = render_chart(fig)
    view["source"] = "Kilde: Valgdirektoratet · valgresultat.no"
    token.checkpoint()
    return view


def municipal_election_comparison(token, question):
    view = {}
    token.checkpoint()
    first_frame = municipality_party_history(
        municipality=question.municipality,
        party_code=question.first_party_code,
        since=question.since,
    )
    token.checkpoint()
    second_frame = municipality_party_history(
        municipality=question.municipality,
        party_code=question.second_party_code,
        since=question.since,
    )
    token.checkpoint()
    first_comparison, second_comparison = align_election_series(
        first_frame, second_frame
    )
    first_name = str(first_comparison.iloc[-1]["party_name"])
    second_name = str(second_comparison.iloc[-1]["party_name"])
    first_start = float(first_comparison.iloc[0]["percent"])
    first_end = float(first_comparison.iloc[-1]["percent"])
    second_start = float(second_comparison.iloc[0]["percent"])
    second_end = float(second_comparison.iloc[-1]["percent"])
    first_change = first_end - first_start
    second_change = second_end - second_start
    latest_difference = first_end - second_end

    def pct(value):
        return f"{value:.2f}".replace(".", ",")

    def pp(value):
        return f"{value:+.2f}".replace(".", ",")

    first_year = min(
        int(first_comparison.iloc[0]["year"]), int(second_comparison.iloc[0]["year"])
    )
    last_year = max(
        int(first_comparison.iloc[-1]["year"]), int(second_comparison.iloc[-1]["year"])
    )
    view["status"] = (
        f"{first_name} og {second_name} · {question.municipality} · {first_year}–{last_year}"
    )
    view["result"] = (
        True,
        f"<b>{first_name}</b>\n<span size='x-large' weight='bold'>{pct(first_start)} % → {pct(first_end)} %</span>\nEndring: {pp(first_change)} prosentpoeng\n\n<b>{second_name}</b>\n<span size='x-large' weight='bold'>{pct(second_start)} % → {pct(second_end)} %</span>\nEndring: {pp(second_change)} prosentpoeng\n\nSammenligningen bruker felles valgår.\nForskjell i {last_year}: {pct(abs(latest_difference))} prosentpoeng\n\nMetode: Partienes stemmeandeler ved kommunevalg i {question.municipality}.",
    )
    view["series"] = [(first_name, first_frame), (second_name, second_frame)]
    view["kind"] = "election"
    with chart_session(token):
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(
            first_frame["year"], first_frame["percent"], marker="o", label=first_name
        )
        ax.plot(
            second_frame["year"], second_frame["percent"], marker="o", label=second_name
        )
        ax.set_title(
            f"{first_name} og {second_name} i {question.municipality} – kommunevalg"
        )
        ax.set_xlabel("Valgår")
        ax.set_ylabel("Prosent")
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        view["chart"] = render_chart(fig)
    view["source"] = "Kilde: Valgdirektoratet · valgresultat.no"
    token.checkpoint()
    return view


def municipal_election_question(token, question):
    view = {}
    token.checkpoint()
    frame = municipality_party_history(
        municipality=question.municipality,
        party_code=question.party_code,
        since=question.since,
    )
    token.checkpoint()
    first = frame.iloc[0]
    last = frame.iloc[-1]
    party_name = str(last["party_name"])
    first_percent = observation_value(first, "percent")
    last_percent = observation_value(last, "percent")
    change = (
        last_percent - first_percent
        if first_percent is not None and last_percent is not None
        else None
    )
    first_year = int(first["year"])
    last_year = int(last["year"])
    view["status"] = (
        f"{party_name} · {question.municipality} · {first_year}–{last_year}"
    )
    first_percent_text = format_number(first_percent, ".2f")
    last_percent_text = format_number(last_percent, ".2f")
    change_text = format_number(change, "+.2f")
    view["result"] = (
        False,
        f"{party_name} · {question.municipality}\n{first_year}: {first_percent_text} %\n{last_year}: {last_percent_text} %\nEndring: {change_text} prosentpoeng",
    )
    view["series"] = [(party_name, frame)]
    view["kind"] = "election"
    with chart_session(token):
        fig = election_figure(frame, f"{party_name} i {question.municipality}")
        view["chart"] = render_chart(fig)
    view["source"] = "Kilde: Valgdirektoratet · valgresultat.no"
    token.checkpoint()
    return view


def election_question(token, question):
    view = {}
    token.checkpoint()
    frame = storting_party_history(
        municipality=question.municipality,
        party_code=question.party_code,
        since=question.since,
    )
    token.checkpoint()
    first = frame.iloc[0]
    last = frame.iloc[-1]
    party_name = str(last["party_name"])
    first_percent = observation_value(first, "percent")
    last_percent = observation_value(last, "percent")
    change = (
        last_percent - first_percent
        if first_percent is not None and last_percent is not None
        else None
    )
    first_text = format_number(first_percent, ".2f")
    last_text = format_number(last_percent, ".2f")
    change_text = format_number(change, "+.2f")
    view["status"] = (
        f"{party_name} · {question.municipality} · {int(first['year'])}–{int(last['year'])}"
    )
    view["result"] = (
        True,
        f"<b>{party_name}</b>\n<span size='x-large' weight='bold'>{first_text} % → {last_text} %</span>\n\nEndring: {change_text} prosentpoeng\n\nMetode: Partiets andel av godkjente stemmer ved stortingsvalg i {question.municipality}.",
    )
    view["series"] = [(party_name, frame)]
    view["kind"] = "election"
    with chart_session(token):
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(frame["year"], frame["percent"], marker="o")
        ax.set_title(f"{party_name} i {question.municipality} – stortingsvalg")
        ax.set_xlabel("Valgår")
        ax.set_ylabel("Prosent")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        view["chart"] = render_chart(fig)
    view["source"] = "Kilde: Valgdirektoratet · valgresultat.no"
    token.checkpoint()
    return view


def raw_text(token, kind, series):
    token.checkpoint()
    lines = []

    if kind == "exchange":
        return exchange_presentation.raw_text(series)
    if kind == "rate":
        return rate_presentation.raw_text(series)

    if kind == "population" and series and isinstance(series[0][1], PopulationSeries):
        return population_presentation.raw_text(series)

    if kind == "population":
        for label, frame in series:
            token.checkpoint()
            lines.append(label)
            lines.append("År      Innbyggere")
            lines.append("------------------")

            for _, row in frame.iterrows():
                year = str(row["Tid_code"])
                value_text = format_number(observation_value(row), ",.0f")
                status = row.get("status")
                if pd.notna(status) and status != "":
                    value_text += f" (status: {status}; kildeverdi: {row['value']})"
                lines.append(f"{year:<8}{value_text:>10}")

            lines.append("")

        source_text = "Kilde: Statistisk sentralbyrå · Tabell 07459"

    elif kind == "election":
        for label, frame in series:
            token.checkpoint()
            lines.append(label)
            lines.append("Valgår   Stemmer      Prosent")
            lines.append("-----------------------------")

            for _, row in frame.iterrows():
                year = int(row["year"])
                votes_text = format_number(observation_value(row, "votes"), ",.0f")
                percent_text = format_number(observation_value(row, "percent"), ".2f")

                lines.append(f"{year:<8}{votes_text:>8}{percent_text:>12} %")

            lines.append("")

        source_text = "Kilde: Valgdirektoratet · valgresultat.no"

    elif kind == "unemployment":
        for label, frame in series:
            token.checkpoint()
            lines.append(label)
            lines.append("År      Måned   Helt ledige   Andel")
            lines.append("-----------------------------------")

            for _, row in frame.iterrows():
                year = int(row["year"])
                month = int(row["month"])
                unemployed = row["unemployed"]
                percent = row["percent"]

                if pd.isna(unemployed):
                    unemployed_text = "—"
                else:
                    unemployed_text = f"{int(unemployed):,}".replace(",", " ")

                if pd.isna(percent):
                    percent_text = "—"
                else:
                    percent_text = f"{float(percent):.1f}".replace(".", ",") + " %"

                lines.append(
                    f"{year:<8}{month:<8}{unemployed_text:>11}{percent_text:>8}"
                )

            lines.append("")

        source_text = "Kilde: NAV · registrerte helt ledige"

    else:
        lines.append("Ingen rådata tilgjengelig.")
        source_text = ""

    token.checkpoint()
    return "\n".join(lines), source_text


def export_csv(token, kind, series, path):
    token.checkpoint()
    frames = []

    if kind == "exchange":
        return exchange_presentation.export_csv(series, path, checkpoint=token.checkpoint)
    if kind == "rate":
        return rate_presentation.export_csv(series, path, checkpoint=token.checkpoint)

    if kind == "population" and series and isinstance(series[0][1], PopulationSeries):
        return population_presentation.export_csv(series, path, checkpoint=token.checkpoint)

    if kind == "population":
        for label, frame in series:
            export = frame.copy()
            export.insert(0, "Kommune", label)

            export = export.rename(
                columns={
                    "Tid_code": "År",
                    "value": "Innbyggere",
                }
            )

            columns = [
                column
                for column in [
                    "Kommune",
                    "År",
                    "Innbyggere",
                    "status",
                ]
                if column in export.columns
            ]

            frames.append(export[columns])

    elif kind == "election":
        for label, frame in series:
            export = frame.copy()

            export = export.rename(
                columns={
                    "year": "Valgår",
                    "area_name": "Kommune",
                    "party_code": "Partikode",
                    "party_name": "Parti",
                    "votes": "Stemmer",
                    "percent": "Prosent",
                }
            )

            columns = [
                column
                for column in [
                    "Valgår",
                    "Kommune",
                    "Partikode",
                    "Parti",
                    "Stemmer",
                    "Prosent",
                ]
                if column in export.columns
            ]

            frames.append(export[columns])

    elif kind == "unemployment":
        for label, frame in series:
            export = frame.copy()
            export.insert(0, "Kommune", label)

            export = export.rename(
                columns={
                    "year": "År",
                    "month": "Måned",
                    "unemployed": "Helt ledige",
                    "percent": "Andel av arbeidsstyrken",
                    "municipality_code": "Kommunenummer",
                }
            )

            columns = [
                column
                for column in [
                    "Kommune",
                    "Kommunenummer",
                    "År",
                    "Måned",
                    "Helt ledige",
                    "Andel av arbeidsstyrken",
                ]
                if column in export.columns
            ]

            frames.append(export[columns])

    else:
        raise ValueError("Ingen data å eksportere.")

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    token.checkpoint()
    combined.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
    )

    return f"Eksportert til {path}"


def receipt_text(token, receipt):
    token.checkpoint()
    text = (receipt.to_json() if receipt.schema_version == "3"
            else population_presentation.receipt_text(receipt))
    token.checkpoint()
    return text


def export_receipt(token, receipt, path):
    token.checkpoint()
    return population_presentation.export_receipt(receipt, path, checkpoint=token.checkpoint)
