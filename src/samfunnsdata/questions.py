import re
from dataclasses import dataclass

from .concepts import find_concepts, normalize_norwegian_text


@dataclass(frozen=True)
class RateQuestion:
    operation: str = "latest"
    since: int | None = None


def parse_rate_question(text: str) -> RateQuestion:
    text = normalize_norwegian_text(text).casefold().rstrip("?.!").strip()
    term = r"(?:norges banks )?styringsrent(?:e|en|a)"
    latest = rf"(?:(?:hva er|vis) )?{term}"
    history = rf"hvordan har {term} utviklet seg"
    since = re.fullmatch(rf"(?:(?:vis )?{term}|{history}) siden ([0-9]{{4}})", text)
    if since:
        year = int(since.group(1))
        if year == 0:
            raise ValueError("Fra år må være større enn null.")
        return RateQuestion("history", year)
    if re.fullmatch(history, text):
        return RateQuestion("history")
    if re.fullmatch(latest, text):
        return RateQuestion()
    raise ValueError("Styringsrenten støtter siste observasjon eller historikk: «Vis styringsrenten siden 2015».")


@dataclass(frozen=True)
class ExchangeQuestion:
    currency: str
    operation: str = "latest"
    since: int | None = None


def parse_exchange_question(text: str) -> ExchangeQuestion:
    text = normalize_norwegian_text(text).casefold().rstrip("?.!").strip()
    terms = {"eurokursen": "EUR", "dollarkursen": "USD", "pundkursen": "GBP",
             "kursen på svenske kroner": "SEK", "kursen på danske kroner": "DKK"}
    terms.update({f"{code}-kursen": code.upper() for code in ("eur", "usd", "gbp", "sek", "dkk")})
    for term, currency in terms.items():
        latest = rf"(?:(?:hva er|vis) )?{term}"
        history = rf"hvordan har {term} utviklet seg"
        since = re.fullmatch(rf"(?:(?:vis )?{term}|{history}) siden ([0-9]{{4}})", text)
        if since:
            year = int(since.group(1))
            if year == 0:
                raise ValueError("Fra år må være større enn null.")
            return ExchangeQuestion(currency, "history", year)
        if re.fullmatch(history, text):
            return ExchangeQuestion(currency, "history")
        if re.fullmatch(latest, text):
            return ExchangeQuestion(currency)
    raise ValueError("Valutakurser støtter siste observasjon eller historikk for EUR, USD, GBP, SEK og DKK; "
                     "for eksempel «Vis eurokursen siden 2020». Beløpsomregning støttes ikke.")


@dataclass(frozen=True)
class PopulationQuestion:
    place: str
    compare_place: str | None = None
    since: int | None = None


def parse_population_question(text: str) -> PopulationQuestion:
    text = normalize_norwegian_text(text)

    if not text:
        raise ValueError("Skriv inn et spørsmål.")

    year_match = re.search(
        r"\b(?:siden|fra|i)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    since = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(
        r"\b(?:siden|fra|i)\s+\d{4}\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .?")

    if not cleaned:
        raise ValueError("Jeg trenger et kommunenavn.")

    comparison_markers = ("sammenlign", "sammenligne", "sammenlikn", "sammenlikne", "mot", "versus")
    if "population" not in find_concepts(cleaned) and not any(marker in cleaned.casefold() for marker in comparison_markers):
        if any(term in cleaned.casefold() for term in ("befolkning", "folketall", "innbyggere")):
            pass
        else:
            raise ValueError("Jeg finner ikke hvilket tema du spør om.")

    compare_patterns = [
        (
            r"^sammenlign\s+(?:befolkningen\s+i\s+)?"
            r"(.+?)\s+og\s+(.+)$"
        ),
        r"^sammenlign\s+(.+?)\s+med\s+(.+)$",
    ]

    for pattern in compare_patterns:
        match = re.search(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            return PopulationQuestion(
                place=_clean_place(match.group(1)),
                compare_place=_clean_place(match.group(2)),
                since=since,
            )

    population_lead_terms = (
        "befolkning",
        "folketall",
        "innbyggere",
        "antall innbyggere",
    )
    single_patterns = [
        (
            r"^vis\s+(?:befolkningen|befolkning|folketallet|folketall|innbyggere|antall innbyggere)"
            r"(?:utviklingen)?\s+i\s+(.+)$"
        ),
        (
            r"^hvordan\s+har\s+(?:befolkningen|befolkning|folketallet|folketall|innbyggere|antall innbyggere)"
            r"(?:utviklingen)?\s+i\s+(.+?)\s+utviklet\s+seg$"
        ),
        (
            r"^(?:befolkningen|befolkning|folketallet|folketall|innbyggere|antall innbyggere)"
            r"(?:utviklingen)?\s+i\s+(.+)$"
        ),
        (
            r"^(?:hvor\s+mange\s+innbyggere|hvor\s+mange\s+innbyggertall|antall\s+innbyggere|antall\s+innbyggertall)"
            r"(?:\s+hadde|\s+har|\s+er|\s+finnes|.*?\s+i)?\s+(.+)$"
        ),
    ]

    for pattern in single_patterns:
        match = re.search(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            candidate = next(
                (
                    group
                    for group in (match.group(index) for index in range(1, len(match.groups()) + 1))
                    if group and group.strip()
                ),
                "",
            )
            if not candidate:
                raise ValueError("Jeg trenger et kommunenavn.")
            return PopulationQuestion(
                place=_clean_place(candidate),
                since=since,
            )

    if any(term in cleaned.casefold() for term in population_lead_terms):
        raise ValueError("Jeg forstår spørsmålet, men jeg trenger et kommunenavn.")

    raise ValueError(
        "Jeg finner ikke hvilket tema du spør om."
    )


def _clean_place(value: str) -> str:
    value = value.strip(" ,.?")
    value = re.sub(
        r"^(?:befolkningen|befolkning)\s+i\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip()



@dataclass(frozen=True)
class UnemploymentQuestion:
    municipality: str
    since: int | None = None


def parse_unemployment_question(
    text: str,
) -> UnemploymentQuestion:
    text = " ".join(text.strip().split())

    year_match = re.search(
        r"\b(?:siden|fra)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    since = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(
        r"\s+(?:siden|fra)\s+\d{4}\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .?")

    patterns = [
        (
            r"^hvordan\s+har\s+arbeidsledigheten\s+i\s+"
            r"(.+?)\s+utviklet\s+seg$"
        ),
        (
            r"^vis\s+arbeidsledigheten\s+i\s+(.+)$"
        ),
        (
            r"^arbeidsledigheten\s+i\s+(.+)$"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )

        if match:
            return UnemploymentQuestion(
                municipality=match.group(1).strip(" ,.?!"),
                since=since,
            )

    raise ValueError(
        "Jeg forstår foreløpig arbeidsledighetsspørsmål som "
        "«Hvordan har arbeidsledigheten i Trondheim "
        "utviklet seg siden 2015?»."
    )

@dataclass(frozen=True)
class ElectionQuestion:
    party_code: str
    municipality: str
    since: int | None = None


@dataclass(frozen=True)
class MunicipalElectionQuestion:
    party_code: str
    municipality: str
    since: int | None = None


@dataclass(frozen=True)
class MunicipalElectionComparisonQuestion:
    first_party_code: str
    second_party_code: str
    municipality: str
    since: int | None = None


@dataclass(frozen=True)
class ElectionComparisonQuestion:
    first_party_code: str
    second_party_code: str
    municipality: str
    since: int | None = None


PARTY_ALIASES = {
    "ap": "A",
    "arbeiderpartiet": "A",
    "frp": "FRP",
    "fremskrittspartiet": "FRP",
    "høyre": "H",
    "h": "H",
    "sv": "SV",
    "sosialistisk venstreparti": "SV",
    "sp": "SP",
    "senterpartiet": "SP",
    "krf": "KRF",
    "kristelig folkeparti": "KRF",
    "venstre": "V",
    "v": "V",
    "mdg": "MDG",
    "miljøpartiet de grønne": "MDG",
    "rødt": "RØDT",
}


def normalize_party(value: str) -> str:
    key = value.casefold().strip()

    if key in PARTY_ALIASES:
        return PARTY_ALIASES[key]

    if key.endswith("s") and key[:-1] in PARTY_ALIASES:
        return PARTY_ALIASES[key[:-1]]

    raise ValueError(f"Ukjent parti «{value}».")


def parse_election_comparison_question(
    text: str,
) -> ElectionComparisonQuestion:
    text = " ".join(text.strip().split())

    year_match = re.search(
        r"\b(?:siden|fra)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    since = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(
        r"\s+(?:siden|fra)\s+\d{4}\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .?")

    patterns = [
        (
            r"^sammenlign\s+(.+?)\s+og\s+(.+?)\s+"
            r"i\s+stortingsvalg(?:et)?\s+i\s+(.+)$"
        ),
        (
            r"^sammenlign\s+(.+?)\s+med\s+(.+?)\s+"
            r"i\s+stortingsvalg(?:et)?\s+i\s+(.+)$"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )

        if match:
            return ElectionComparisonQuestion(
                first_party_code=normalize_party(
                    match.group(1)
                ),
                second_party_code=normalize_party(
                    match.group(2)
                ),
                municipality=match.group(3).strip(" ,.?!"),
                since=since,
            )

    raise ValueError(
        "Jeg forstår foreløpig partisammenligninger som "
        "«Sammenlign FrP og Høyre i stortingsvalg "
        "i Trondheim siden 2009»."
    )


def parse_municipal_election_comparison_question(
    text: str,
) -> MunicipalElectionComparisonQuestion:
    text = " ".join(text.strip().split())

    year_match = re.search(
        r"\b(?:siden|fra)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    since = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(
        r"\s+(?:siden|fra)\s+\d{4}\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .?")

    patterns = [
        (
            r"^sammenlign\s+(.+?)\s+og\s+(.+?)\s+"
            r"i\s+kommunevalg(?:et)?\s+i\s+(.+)$"
        ),
        (
            r"^sammenlign\s+(.+?)\s+med\s+(.+?)\s+"
            r"i\s+kommunevalg(?:et)?\s+i\s+(.+)$"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )

        if match:
            return MunicipalElectionComparisonQuestion(
                first_party_code=normalize_party(match.group(1)),
                second_party_code=normalize_party(match.group(2)),
                municipality=match.group(3).strip(" ,.?!"),
                since=since,
            )

    raise ValueError(
        "Jeg forstår foreløpig kommunevalgsammenligninger som "
        "«Sammenlign Høyre og FrP i kommunevalg "
        "i Trondheim siden 2011»."
    )


def parse_municipal_election_question(
    text: str,
) -> MunicipalElectionQuestion:
    text = " ".join(text.strip().split())

    year_match = re.search(
        r"\b(?:siden|fra)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    since = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(
        r"\s+(?:siden|fra)\s+\d{4}\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .?")

    match = re.fullmatch(
        r"vis\s+(.+?)\s+kommunevalgresultater\s+i\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not match:
        raise ValueError(
            "Ugyldig kommunevalgspørsmål."
        )

    party = normalize_party(match.group(1))
    municipality = match.group(2).strip()

    return MunicipalElectionQuestion(
        party_code=party,
        municipality=municipality,
        since=since,
    )


def parse_election_question(text: str) -> ElectionQuestion:
    text = " ".join(text.strip().split())

    year_match = re.search(
        r"\b(?:siden|fra)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    since = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(
        r"\s+(?:siden|fra)\s+\d{4}\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .?")

    patterns = [
        (
            r"^vis\s+(.+?)\s+"
            r"stortingsvalgresultater\s+i\s+(.+)$"
        ),
        (
            r"^hvordan\s+har\s+(.+?)\s+gjort\s+det\s+"
            r"i\s+stortingsvalg(?:et)?\s+i\s+(.+)$"
        ),
        (
            r"^hvordan\s+har\s+(.+?)\s+utviklet\s+seg\s+"
            r"i\s+stortingsvalg(?:et)?\s+i\s+(.+)$"
        ),
        (
            r"^vis\s+(.+?)\s+i\s+stortingsvalg(?:et)?\s+"
            r"i\s+(.+)$"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )

        if match:
            return ElectionQuestion(
                party_code=normalize_party(match.group(1)),
                municipality=match.group(2).strip(" ,.?!"),
                since=since,
            )

    raise ValueError(
        "Jeg forstår foreløpig valgspørsmål som "
        "«Vis FrPs stortingsvalgresultater i Trondheim siden 2009» "
        "eller «Hvordan har FrP gjort det i stortingsvalg i "
        "Trondheim siden 2009?»."
    )


def parse_question(text: str):
    if "policy_rate" in find_concepts(text):
        return parse_rate_question(text)
    parsers = [
        parse_exchange_question,
        parse_unemployment_question,
        parse_election_comparison_question,
        parse_municipal_election_comparison_question,
        parse_municipal_election_question,
        parse_election_question,
        parse_population_question,
    ]

    errors = []

    for parser in parsers:
        try:
            return parser(text)
        except ValueError as error:
            errors.append(str(error))

    raise ValueError(
        "Jeg forstår ikke spørsmålet ennå. "
        "Prøv for eksempel «Vis befolkningen i Trondheim siden 2000» "
        "eller «Vis FrPs stortingsvalgresultater i Trondheim siden 2009»."
    )
