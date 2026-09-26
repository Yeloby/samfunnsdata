"""Text and export for the policy-rate result, independent of GTK/providers."""

import csv


def number(value):
    return "ikke oppgitt" if value is None else f"{value:g}".replace(".", ",")


def summary(result):
    series = result.series[0]
    facts = series.derived_facts
    lines = ["Norges Banks styringsrente",
             f"Siste observasjon: {facts.last_period}: {number(facts.last_value)} %"]
    if series.selection.operation == "history":
        lines += [f"Periode: {facts.first_period}–{facts.last_period}",
                  f"Endring: {number(facts.change)} prosentpoeng"]
    lines.extend(result.warnings)
    lines.append("Kilde: Norges Bank · IR/" + series.selection.series_code)
    return "\n".join(lines)


def raw_text(series):
    lines = ["Dato\tKildeverdi (%)\tStatus\tBeregningsmetode"]
    for _, item in series:
        lines.extend(f"{o.period}\t{o.source_value}\t{o.status or ''}\t{o.calculation_method or ''}"
                     for o in item.source_observations)
    return "\n".join(lines), "Kilde: Norges Bank · IR/B.KPRA.SD.R"


def export_csv(series, path, *, checkpoint=lambda: None):
    checkpoint()
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("Dato", "Styringsrente (%)", "status", "CALC_METHOD"))
        for _, item in series:
            for o in item.source_observations:
                checkpoint()
                writer.writerow((o.period, o.source_value, o.status, o.calculation_method))
    return f"Eksportert til {path}"
