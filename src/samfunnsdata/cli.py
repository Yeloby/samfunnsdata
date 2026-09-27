import argparse

from . import network
from .analysis import format_number
from .charts import population_chart
from .population import analyze_population
from .population_presentation import export_receipt, observation_text, summary_text
from .providers.norway.ssb import SsbClient, municipality_population


def main():
    parser = argparse.ArgumentParser(
        prog="samfunnsdata",
        description="Analyse norske offentlige data",
    )

    parser.add_argument("--cache-only", action="store_true", help="Bruk bare lokal cache; ingen HTTP-kall")

    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser(
        "search",
        help="Søk etter SSB-tabeller (søketeksten sendes til SSB ved cachebom)",
    )
    search.add_argument("query")

    population = sub.add_parser(
        "population",
        help="Vis befolkningsutvikling",
    )
    population.add_argument("place")
    population.add_argument(
        "--since",
        type=int,
        help="Vis befolkningsutvikling fra dette året",
    )
    population.add_argument(
        "--chart",
        action="store_true",
        help="Lagre utviklingen som PNG-graf",
    )

    compare = sub.add_parser(
        "compare",
        help="Sammenlign befolkningsutvikling mellom kommuner",
    )
    compare.add_argument(
        "places",
        nargs="+",
        help="Kommuner som skal sammenlignes",
    )
    compare.add_argument(
        "--since",
        type=int,
        help="Sammenlign fra dette året",
    )
    compare.add_argument(
        "--chart",
        action="store_true",
        help="Lagre sammenligningen som PNG-graf",
    )

    rate = sub.add_parser("rate", help="Vis Norges Banks styringsrente")
    rate_selection = rate.add_mutually_exclusive_group()
    rate_selection.add_argument("--since", type=int, help="Vis historikk fra og med året")
    rate_selection.add_argument("--history", action="store_true", help="Vis all tilgjengelig historikk")

    exchange = sub.add_parser("exchange", help="Vis Norges Banks valutakurser mot NOK")
    exchange.add_argument("currency", choices=("EUR", "USD", "GBP", "SEK", "DKK"), type=str.upper)
    exchange_selection = exchange.add_mutually_exclusive_group()
    exchange_selection.add_argument("--since", type=int, help="Vis historikk fra og med året")
    exchange_selection.add_argument("--history", action="store_true", help="Vis all tilgjengelig historikk")

    for command_parser in (population, compare, rate, exchange):
        command_parser.add_argument("--receipt", metavar="PATH",
                                    help="Lagre datakvittering som separat JSON-fil")

    for command_parser in (search, population, compare, rate, exchange):
        command_parser.add_argument("--cache-only", action="store_true", default=argparse.SUPPRESS,
                                    help="Bruk bare lokal cache; ingen HTTP-kall")
    args = parser.parse_args()
    network.set_mode(network.NetworkMode.CACHE_ONLY if args.cache_only else network.NetworkMode.ONLINE)

    if args.command == "exchange":
        from .exchange_presentation import raw_text, summary
        from .query_plan import execute_query_plan, plan_from_exchange_question
        from .questions import ExchangeQuestion

        operation = "history" if args.history or args.since is not None else "latest"
        try:
            result = execute_query_plan(plan_from_exchange_question(ExchangeQuestion(args.currency, operation, args.since)))
        except ValueError as error:
            parser.error(str(error))
        print(summary(result))
        if operation == "history":
            print(raw_text([(s.name, s) for s in result.series])[0])
        if args.receipt:
            export_receipt(result.receipt, args.receipt)
        return 0

    if args.command == "rate":
        from .query_plan import execute_query_plan, plan_from_rate_question
        from .questions import RateQuestion
        from .rate_presentation import raw_text, summary

        operation = "history" if args.history or args.since is not None else "latest"
        try:
            result = execute_query_plan(plan_from_rate_question(RateQuestion(operation, args.since)))
        except ValueError as error:
            parser.error(str(error))
        print(summary(result))
        if operation == "history":
            print(raw_text([(s.name, s) for s in result.series])[0])
        if args.receipt:
            export_receipt(result.receipt, args.receipt)
        return 0

    if args.command == "search":
        client = SsbClient()

        try:
            tables = client.search(args.query)
        except network.NetworkError as error:
            parser.error(str(error))
        for table in tables:
            print(f"{table.id}\t{table.title}")

        return 0

    if args.command == "population":
        try:
            result = analyze_population([args.place], args.since, provider=municipality_population)
        except ValueError as error:
            parser.error(str(error))
        series = result.series[0]
        municipality = series.selection
        summary = series.derived_facts
        first_value = summary.first_value
        last_value = summary.last_value
        first_year = summary.first_year
        last_year = summary.last_year

        print()
        print(
            f"{series.name}: "
            f"{format_number(first_value)} → {format_number(last_value)} "
            f"({first_year}–{last_year})"
            .replace(",", " ")
        )
        print(summary_text(series)[1])

        print()
        print(f"Befolkningsutvikling i {series.name}")
        print("=" * 35)

        for observation in series.source_observations:
            print(f"{observation.period_label}: {observation_text(observation)}")

        print()
        print("Kilde: Statistisk sentralbyrå")
        print("Tabell: 07459")
        print(f"Kommune: {series.name} ({municipality.municipality_code})")
        print(f"Periode: {first_year}–{last_year}")
        print(
            "Metode: SSBs aggregerte kommuneserie "
            "for sammenhengende historiske tall."
        )

        if args.chart:
            slug = args.place.casefold().replace(" ", "-")
            output = (
                f"population-{slug}-"
                f"{first_year}-{last_year}.png"
            )
            population_chart(
                [(series.name, series)],
                output,
                f"Befolkningsutvikling i {series.name}",
            )
            print(f"Graf: {output}")

        print()

        if args.receipt:
            export_receipt(result.receipt, args.receipt)

        return 0

    if args.command == "compare":
        if len(args.places) < 2:
            parser.error("Oppgi minst to kommuner som skal sammenlignes.")

        try:
            result = analyze_population(args.places, args.since, provider=municipality_population)
        except ValueError as error:
            parser.error(str(error))
        chart_series = [(s.name, s) for s in result.series]
        periods = {(s.derived_facts.first_year, s.derived_facts.last_year) for s in result.series}

        print()

        if len(periods) == 1:
            first_year, last_year = next(iter(periods))
            print(f"Sammenligning {first_year}–{last_year}")
        else:
            print("Sammenligning")

        print("=" * 35)

        for series in result.series:
            facts = series.derived_facts
            values, change = summary_text(series)
            print()
            print(series.name)
            print(f"{values} ({facts.first_year}–{facts.last_year})")
            print(change)

        print()
        print("Kilde: Statistisk sentralbyrå")
        print("Tabell: 07459")
        print(
            "Metode: SSBs aggregerte kommuneserier "
            "for sammenhengende historiske tall."
        )

        if args.chart:
            years = periods

            if len(years) == 1:
                chart_first, chart_last = next(iter(years))
                output = (
                    f"population-comparison-"
                    f"{chart_first}-{chart_last}.png"
                )
            else:
                output = "population-comparison.png"

            population_chart(
                chart_series,
                output,
                "Befolkningsutvikling",
            )
            print(f"Graf: {output}")

        print()

        if args.receipt:
            export_receipt(result.receipt, args.receipt)

        return 0

    return 1
