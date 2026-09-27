"""Raw quotations retain the source basis in every display and export."""

import csv
import json


def number(value):
    return (
        "ikke oppgitt"
        if value is None
        else str(value).removesuffix(".0").replace(".", ",")
    )


def summary(result):
    series = result.series[0]
    facts = series.derived_facts
    metadata = json.loads(series.provider_metadata_json)
    basis, currency = metadata["quotation_basis"], metadata["BASE_CUR"]
    lines = [
        result.title,
        f"Siste observasjon: {facts.last_period}",
        f"{basis} {currency} = {number(facts.last_value)} NOK",
    ]
    if series.selection.operation == "history":
        lines += [
            f"Periode: {facts.first_period}–{facts.last_period}",
            f"Absolutt endring: {number(facts.change)} {facts.change_unit}",
        ]
    lines.extend(result.warnings)
    lines.append("Kilde: Norges Bank · EXR/" + series.selection.series_code)
    return "\n".join(lines)


def raw_text(series):
    lines = []
    for _, item in series:
        unit = json.loads(item.provider_metadata_json)["quotation_unit"]
        lines.append(f"Dato\tKildeverdi ({unit})\tStatus\tBeregningsmetode")
        lines.extend(
            f"{o.period}\t{o.source_value}\t{o.status or ''}\t{o.calculation_method or ''}"
            for o in item.source_observations
        )
    return "\n".join(lines), "Kilde: Norges Bank · EXR"


def export_csv(series, path, *, checkpoint=lambda: None):
    checkpoint()
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ("Dato", "OBS_VALUE", "Enhet", "Serie", "status", "CALC_METHOD")
        )
        for _, item in series:
            unit = json.loads(item.provider_metadata_json)["quotation_unit"]
            for o in item.source_observations:
                checkpoint()
                writer.writerow(
                    (
                        o.period,
                        o.source_value,
                        unit,
                        item.selection.series_code,
                        o.status,
                        o.calculation_method,
                    )
                )
    return f"Eksportert til {path}"
