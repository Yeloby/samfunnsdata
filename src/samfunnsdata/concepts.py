from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    id: str
    terms: tuple[str, ...]
    description: str = ""


POPULATION_TERMS = (
    "befolkning",
    "befolkningen",
    "folketall",
    "folketallet",
    "innbyggere",
    "innbyggertall",
    "antall innbyggere",
    "antall innbyggertall",
    "hvor mange innbyggere",
    "hvor mange innbyggertall",
)

UNEMPLOYMENT_TERMS = (
    "arbeidsledighet",
    "arbeidsledigheten",
    "arbeidsledige",
    "ledighet",
    "helt ledige",
    "registrerte arbeidsledige",
)

ELECTION_TERMS = (
    "valg",
    "valgresultat",
    "valgresultater",
    "stortingsvalg",
    "kommunevalg",
    "stemmer",
    "oppslutning",
)

TRAFFIC_TERMS = (
    "trafikk",
    "trafikken",
    "trafikkutvikling",
    "trafikkmengde",
    "ådt",
    "adt",
    "årsdøgntrafikk",
    "aadt",
    "kjøretøy",
    "veitrafikk",
    "tellepunkt",
    "trafikkregistreringspunkt",
    "målestasjon",
)

COMPARISON_TERMS = (
    "sammenlign",
    "sammenligne",
    "sammenlikn",
    "sammenlikne",
    "mot",
    "versus",
    "mellom",
)

TIME_TERMS = (
    "siden",
    "fra",
    "i",
    "utvikling",
    "over tid",
    "mellom",
)

CONCEPTS = (
    Concept("policy_rate", ("styringsrente", "styringsrenten", "styringsrenta"), "Norges Banks styringsrente."),
    Concept("population", POPULATION_TERMS, "Befolkningsspørsmål."),
    Concept("unemployment", UNEMPLOYMENT_TERMS, "Arbeidsledighet."),
    Concept("election", ELECTION_TERMS, "Valgresultat."),
    Concept("comparison", COMPARISON_TERMS, "Sammenligning."),
    Concept("traffic", TRAFFIC_TERMS, "Vegtrafikk og ÅDT."),
    Concept("time", TIME_TERMS, "Tidsuttrykk."),
)


def normalize_norwegian_text(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ")
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_concepts(text: str) -> tuple[str, ...]:
    normalized = normalize_norwegian_text(text).casefold()
    matches: list[str] = []
    for concept in CONCEPTS:
        if any(term in normalized for term in concept.terms):
            matches.append(concept.id)
    return tuple(matches)


__all__ = [
    "CONCEPTS",
    "Concept",
    "find_concepts",
    "normalize_norwegian_text",
]
