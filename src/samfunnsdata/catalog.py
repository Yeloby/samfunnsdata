from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from .config import CACHE_DIR


class SupportStatus(StrEnum):
    SUPPORTED = "supported"
    DISCOVERED = "discovered"
    PLANNED = "planned"


@dataclass(frozen=True)
class Source:
    id: str
    authority: str
    url: str
    provider: str | None = None
    official_reference: str | None = None
    discovery_capable: bool = False


SOURCES = (
    Source("norges_bank", "Norges Bank", "https://www.norges-bank.no",
           provider="norges_bank",
           official_reference="https://www.norges-bank.no/tema/Statistikk/apne-data/"),
    Source(
        "ssb",
        "Statistisk sentralbyrå",
        "https://www.ssb.no",
        provider="ssb",
        official_reference="https://www.ssb.no/tjenester/pxweb",
        discovery_capable=True,
    ),
    Source(
        "fhi",
        "Folkehelseinstituttet",
        "https://www.fhi.no",
        provider="fhi",
        official_reference="https://statistikk-data.fhi.no",
        discovery_capable=False,
    ),
    Source(
        "nav",
        "NAV",
        "https://www.nav.no",
        provider="nav",
        official_reference="https://www.nav.no",
        discovery_capable=False,
    ),
    Source(
        "elections",
        "Valgdirektoratet",
        "https://valgresultat.no",
        provider="elections",
        official_reference="https://valgresultat.no",
        discovery_capable=False,
    ),
    Source(
        "vegvesen",
        "Statens vegvesen",
        "https://trafikkdata.atlas.vegvesen.no",
        provider="vegvesen",
        official_reference="https://trafikkdata.atlas.vegvesen.no",
        discovery_capable=False,
    ),
)


class SourceRegistry:
    def __init__(self, sources: Iterable[Source] = SOURCES):
        self._sources = {source.id: source for source in sources}

    def list(self) -> tuple[Source, ...]:
        return tuple(self._sources.values())

    def get(self, source_id: str) -> Source:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"Ukjent datakilde: {source_id}") from exc

    def by_provider(self, provider: str) -> Source | None:
        for source in self._sources.values():
            if source.provider == provider:
                return source
        return None


SOURCE_REGISTRY = SourceRegistry()


def _canonical_dataset_key(provider: str | None, table_id: str | None) -> str | None:
    if not provider or not table_id:
        return None
    return f"{provider}:{table_id}"


def _normalize_remote_support(value: object) -> SupportStatus:
    if value is None:
        return SupportStatus.DISCOVERED
    if isinstance(value, SupportStatus):
        if value == SupportStatus.SUPPORTED:
            raise TypeError("Remote metadata kan ikke erklære datasettet som støttet.")
        return value
    if isinstance(value, str):
        try:
            support = SupportStatus(value.casefold())
        except ValueError as exc:
            raise TypeError("support må være en SupportStatus.") from exc
        if support == SupportStatus.SUPPORTED:
            raise TypeError("Remote metadata kan ikke erklære datasettet som støttet.")
        return support
    raise TypeError("support må være en SupportStatus.")


class DatasetRegistry:
    def __init__(self, curated: Iterable[Dataset] = (), discovered: Iterable[Dataset] = ()):
        self._curated = {dataset.id: dataset for dataset in curated}
        self._discovered = {}
        self._by_table = {}
        for dataset in curated:
            if dataset.provider and dataset.table_id:
                self._by_table[_canonical_dataset_key(dataset.provider, dataset.table_id)] = dataset
        for dataset in discovered:
            self.register_discovered(dataset)

    def register_discovered(self, dataset: Dataset) -> Dataset:
        if dataset.support == SupportStatus.SUPPORTED:
            raise TypeError("Remote metadata kan ikke erklære datasettet som støttet.")
        key = _canonical_dataset_key(dataset.provider, dataset.table_id)
        if key is not None and key in self._by_table:
            return self._curated[self._by_table[key].id]
        if dataset.id in self._curated:
            return self._curated[dataset.id]
        self._discovered[dataset.id] = dataset
        if key is not None:
            self._by_table[key] = dataset
        return dataset

    def effective_datasets(self) -> tuple[Dataset, ...]:
        datasets = list(self._curated.values())
        for dataset in self._discovered.values():
            if dataset.id not in {item.id for item in datasets}:
                datasets.append(dataset)
        return tuple(datasets)

    def get(self, dataset_id: str) -> Dataset:
        if dataset_id in self._curated:
            return self._curated[dataset_id]
        if dataset_id in self._discovered:
            return self._discovered[dataset_id]
        raise KeyError(f"Ukjent datasett: {dataset_id}")

    def get_by_table(self, provider: str, table_id: str) -> Dataset:
        key = _canonical_dataset_key(provider, table_id)
        if key in self._by_table:
            dataset = self._by_table[key]
            return dataset
        raise KeyError(f"Ukjent datasett for {provider}:{table_id}")

    def list(self, *, provider: str | None = None, support: SupportStatus | None = None) -> tuple[Dataset, ...]:
        items = self.effective_datasets()
        filtered = [
            dataset for dataset in items
            if (provider is None or dataset.provider == provider)
            and (support is None or dataset.support == support)
        ]
        return tuple(filtered)

    def search(self, query: str, *, provider: str | None = None, support: SupportStatus | None = None) -> list[Dataset]:
        candidates = self.list(provider=provider, support=support)
        words = set()
        for raw_word in query.casefold().split():
            word = raw_word.strip(" ,.?!:;()")
            if len(word) >= 3:
                for suffix in ("ene", "en", "et", "a"):
                    if word.endswith(suffix) and len(word) > len(suffix) + 3:
                        words.add(word[:-len(suffix)])
                words.add(word)
        if not words:
            return list(candidates)

        scored: list[tuple[int, Dataset]] = []
        for dataset in candidates:
            authority = get_source(dataset.provider).authority if dataset.provider in {source.id for source in SOURCES} else ""
            searchable_parts = [
                dataset.title,
                dataset.topic,
                dataset.description,
                dataset.provider,
                dataset.source,
                authority,
                dataset.definition,
                *dataset.dimensions,
                *dataset.measures,
                *dataset.aliases,
                dataset.table_id or "",
            ]
            if hasattr(dataset, "keywords"):
                searchable_parts.extend(dataset.keywords)
            searchable = " ".join(searchable_parts).casefold()
            score = sum(1 for word in words if word in searchable)
            if score:
                scored.append((score, dataset))
        scored.sort(key=lambda item: (-item[0], item[1].title.casefold()))
        return [dataset for _, dataset in scored]


DATASET_REGISTRY = DatasetRegistry(curated=(), discovered=())
DISCOVERED_DATASETS: tuple[Dataset, ...] = ()


def _dataset_from_record(record: dict, *, provider: str = "ssb") -> Dataset:
    table_id = str(
        record.get("table_id")
        or record.get("id")
        or record.get("tableId")
        or record.get("code")
        or ""
    )
    if not table_id:
        raise ValueError("Oppdaget SSB-metadata mangler tabell-ID.")

    title = str(
        record.get("title")
        or record.get("label")
        or record.get("name")
        or f"SSB-tabell {table_id}"
    )
    description = str(record.get("description") or record.get("text") or "")
    topic = str(record.get("topic") or record.get("category") or "ssb")
    source = str(record.get("source") or "SSB")
    dimensions = tuple(str(item) for item in (record.get("dimensions") or record.get("variables") or ()))
    period = str(record.get("period") or record.get("latestPeriod") or record.get("time_period") or "Ukjent")
    keywords = tuple(str(item) for item in (record.get("keywords") or ()))
    support_value = record.get("support")
    support = SupportStatus.DISCOVERED
    if support_value is not None:
        support = _normalize_remote_support(support_value)
    updated_value = (
        record.get("updated_at")
        or record.get("updated")
        or record.get("last_updated")
        or None
    )
    dataset_id = f"{provider}-{table_id}"
    return Dataset(
        id=dataset_id,
        provider=provider,
        title=title,
        topic=topic,
        source=source,
        geography=(),
        time_resolution=str(record.get("time_resolution") or record.get("timeResolution") or "unknown"),
        dimensions=dimensions,
        unit=str(record.get("unit") or "unknown"),
        description=description,
        period=period,
        measures=tuple(str(item) for item in (record.get("measures") or ())),
        definition=str(record.get("definition") or description or "Oppdaget fra SSB uten lokalt adapterstøtte."),
        support=support,
        table_id=table_id,
        source_url=str(record.get("source_url") or record.get("url") or f"https://www.ssb.no/statbank/table/{table_id}"),
        access_url=str(record.get("access_url") or record.get("data_url") or f"https://data.ssb.no/api/pxwebapi/v2/tables/{table_id}/data"),
        format=str(record.get("format") or "json-stat2"),
        updated_at=str(updated_value) if updated_value not in (None, "") else None,
        keywords=keywords,
    )


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            tmp = Path(handle.name)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _ssb_snapshot_path() -> Path:
    return CACHE_DIR / "metadata" / "ssb-discovery.json"


def _format_snapshot_entry(dataset: Dataset) -> dict:
    return {
        "id": dataset.id,
        "provider": dataset.provider,
        "title": dataset.title,
        "topic": dataset.topic,
        "source": dataset.source,
        "table_id": dataset.table_id,
        "description": dataset.description,
        "keywords": list(dataset.keywords if hasattr(dataset, "keywords") else ()),
        "support": dataset.support.value,
        "dimensions": list(dataset.dimensions),
        "period": dataset.period,
        "source_url": dataset.source_url,
        "access_url": dataset.access_url,
        "format": dataset.format,
        "updated_at": dataset.updated_at,
        "time_resolution": dataset.time_resolution,
        "measures": list(dataset.measures),
        "definition": dataset.definition,
        "geography": list(dataset.geography),
        "unit": dataset.unit,
    }


def _load_ssb_snapshot(path: Path | None = None) -> tuple[Dataset, ...]:
    path = path or _ssb_snapshot_path()
    if not path.exists():
        raise FileNotFoundError(f"Fant ingen lokal SSB-katalogsnapshot: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Katalogsnapshoten er korrupt: {path}") from exc
    if not isinstance(payload, dict):
        raise TypeError("Katalogsnapshoten er ikke et JSON-objekt.")
    schema_version = payload.get("schema_version", 1)
    if schema_version != 1:
        raise ValueError(f"Ustøttet katalogsnapshotversjon: {schema_version}")
    records = payload.get("tables") or []
    if not isinstance(records, list):
        raise TypeError("Snapshotens tabeller er ikke en liste.")
    datasets = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        try:
            datasets.append(_dataset_from_record(record, provider="ssb"))
        except ValueError:
            continue
    return tuple(datasets)


def _fetch_ssb_metadata_records(client=None, *, max_pages: int = 20, page_size: int = 100) -> tuple[dict, ...]:
    if client is None:
        from .providers.norway.ssb import SsbClient
        client = SsbClient()

    results: list[dict] = []
    seen_ids: set[str] = set()
    page = 1
    while page <= max_pages:
        response = client.search("")
        current = response if response else []
        if not current:
            break
        for item in current:
            if not isinstance(item, dict):
                continue
            table_id = str(item.get("id") or item.get("tableId") or item.get("code") or "")
            if not table_id or table_id in seen_ids:
                continue
            seen_ids.add(table_id)
            results.append(item)
        if len(current) < page_size:
            break
        page += 1
    return tuple(results)


def refresh_ssb_discovery_snapshot(path: Path | None = None, *, client=None) -> tuple[Dataset, ...]:
    path = path or _ssb_snapshot_path()
    current_mode = __import__("samfunnsdata.network", fromlist=["get_mode", "NetworkMode"]).get_mode()
    if current_mode == __import__("samfunnsdata.network", fromlist=["NetworkMode"]).NetworkMode.CACHE_ONLY:
        if path.exists():
            return _load_ssb_snapshot(path)
        raise __import__("samfunnsdata.network", fromlist=["CacheOnlyMiss"]).CacheOnlyMiss(
            "SSB-datakatalog kan ikke oppdateres i cache-only-modus. Bruk eksisterende lokal snapshot."
        )

    fetched = _fetch_ssb_metadata_records(client=client)
    unique_records: list[dict] = []
    seen_ids: set[str] = set()
    for record in fetched:
        table_id = str(record.get("id") or record.get("tableId") or record.get("code") or "")
        if not table_id or table_id in seen_ids:
            continue
        seen_ids.add(table_id)
        unique_records.append(record)
    datasets = tuple(_dataset_from_record(record, provider="ssb") for record in unique_records)
    payload = {
        "schema_version": 1,
        "provider": "ssb",
        "source": "ssb",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tables": [_format_snapshot_entry(dataset) for dataset in datasets],
    }
    _atomic_json_write(path, payload)
    global DISCOVERED_DATASETS
    DISCOVERED_DATASETS = datasets
    DATASET_REGISTRY._discovered = {dataset.id: dataset for dataset in datasets}
    DATASET_REGISTRY._by_table = {
        _canonical_dataset_key(dataset.provider, dataset.table_id): dataset
        for dataset in DATASET_REGISTRY.effective_datasets()
        if dataset.provider and dataset.table_id
    }
    return datasets


def load_discovered_ssb_snapshot(path: Path | None = None) -> tuple[Dataset, ...]:
    path = path or _ssb_snapshot_path()
    datasets = _load_ssb_snapshot(path)
    global DISCOVERED_DATASETS
    DISCOVERED_DATASETS = datasets
    DATASET_REGISTRY._discovered = {dataset.id: dataset for dataset in datasets}
    DATASET_REGISTRY._by_table = {
        _canonical_dataset_key(dataset.provider, dataset.table_id): dataset
        for dataset in DATASET_REGISTRY.effective_datasets()
        if dataset.provider and dataset.table_id
    }
    return datasets


DATABASE_REGISTRY_NOT_USED = None


def get_source(provider: str) -> Source:
    for source in SOURCES:
        if source.id == provider:
            return source
    raise KeyError(f"Ukjent datakilde: {provider}")


@dataclass(frozen=True)
class Dataset:
    id: str
    provider: str
    title: str
    topic: str
    source: str
    geography: tuple[str, ...]
    time_resolution: str
    dimensions: tuple[str, ...]
    unit: str
    description: str
    period: str
    measures: tuple[str, ...]
    definition: str
    limitations: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    support: SupportStatus = SupportStatus.PLANNED
    adapter: str | None = None
    interfaces: tuple[str, ...] = ()
    table_id: str | None = None
    source_url: str | None = None
    access_url: str | None = None
    format: str | None = None
    updated_at: str | None = None
    methodology: tuple[str, ...] = ()
    series_breaks: tuple[str, ...] = ()
    official_statistics: bool | None = None

    def __post_init__(self):
        if not isinstance(self.support, SupportStatus):
            if not isinstance(self.support, str):
                raise TypeError("support må være en SupportStatus.")
            try:
                support = SupportStatus(self.support)
            except ValueError as exc:
                raise TypeError("support må være en SupportStatus.") from exc
            if support == SupportStatus.SUPPORTED:
                raise TypeError("support må være en SupportStatus.")
            object.__setattr__(self, "support", support)

        if self.support == SupportStatus.SUPPORTED:
            if not self.adapter or not self.interfaces:
                raise ValueError("Støttede datasett må angi adapter og grensesnitt.")
        elif self.adapter or self.interfaces:
            raise ValueError("Katalogiserte/planlagte datasett kan ikke angi kjørbar støtte.")

    @property
    def queryable(self) -> bool:
        """Dataset-level support; this does not imply GUI or arbitrary query support."""
        return self.support == SupportStatus.SUPPORTED

    @property
    def support_label(self) -> str:
        if self.support == SupportStatus.SUPPORTED:
            channels = {"python": "Python/API", "gui": "GUI", "cli": "CLI"}
            return "Støttet: " + ", ".join(channels.get(x, x) for x in self.interfaces)
        if self.support == SupportStatus.DISCOVERED:
            return "Katalogisert – kan ikke hentes i Samfunnsdata"
        return "Planlagt – ikke støttet"


DATASETS = (
    Dataset(
        id="fhi-lmr-825-medicines",
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.medicines:medicine_history",
        interfaces=("python",),
        table_id="lmr/825",
        source_url="https://statistikk-data.fhi.no/api/open/v1/lmr/table/825/metadata",
        access_url="https://statistikk-data.fhi.no/api/open/v1/lmr/Table/825/data",
        format="json-stat2",
        provider="fhi",
        title="Legemidler etter ATC-kode",
        topic="health / medicines",
        source="FHI Legemiddelregisteret (lmr), tabell 825",
        geography=(),
        time_resolution="year",
        dimensions=("atc", "sex", "age", "year", "measure"),
        unit="measure_dependent",
        description="Legemiddelstatistikk etter ATC-kode, kjønn, alder og år.",
        period="2004– (tilgjengelige år hentes fra FHI)",
        measures=("users", "users_per_1000", "ddd", "population"),
        definition="FHI-tabellen «Per ATC-kode», med måltall levert av FHI.",
        limitations=(
            "Brukertall skal ikke summeres på tvers av ATC-koder.",
            "Manglende og skjulte observasjoner må beholde status.",
            "Enhet avhenger av valgt måltall.",
        ),
        aliases=("legemidler", "legemiddel", "medisiner", "ATC"),
    ),
    Dataset(
        id="norges-bank-exchange-rate", provider="norges_bank", title="Valutakurser",
        topic="economy / exchange rates", source="Norges Bank", geography=("Norway",),
        time_resolution="business_day", dimensions=("currency", "since"),
        unit="NOK per 1 EUR/USD/GBP eller per 100 SEK/DKK",
        description="Indikative midtkurser mot norske kroner: siste observasjon og historikk.",
        measures=("exchange_rate",), period="Publiserte virkedager",
        definition="EXR/B.<valuta>.NOK.SP; råverdier beholdes med kildens noteringsgrunnlag.",
        limitations=("Ingen beløpsomregning, krysskurser, prognose eller gjennomsnitt.",),
        aliases=("valutakurs", "eurokurs", "dollarkurs", "EUR", "USD", "GBP", "SEK", "DKK"),
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.norges_bank_exchange:exchange_rate",
        interfaces=("python", "cli", "gui"), table_id="EXR",
        source_url="https://www.norges-bank.no/tema/Statistikk/Valutakurser/",
        access_url="https://data.norges-bank.no/api/data/EXR", format="csv",
        methodology=("Absolutt differanse mellom faktiske endepunkter i samme kildeenhet; ingen interpolasjon.",),
    ),
    Dataset(
        id="norges-bank-policy-rate", provider="norges_bank",
        title="Styringsrente", topic="economy / interest rates", source="Norges Bank",
        geography=("Norway",), time_resolution="business_day", dimensions=("since",),
        unit="prosent", description="Norges Banks styringsrente: siste observasjon og historikk.",
        period="Tilgjengelige publiserte virkedager",
        measures=("policy_rate",),
        definition="IR/B.KPRA.SD.R: styringsrente, virkedag, slutten av dagen. Rente i prosent.",
        limitations=("Ingen interpolasjon eller utfylling av dager. Ingen prognose eller månedsgjennomsnitt.",
                     "Siste observasjon vises med dato; cache kan være eldre enn kilden."),
        aliases=("styringsrente", "styringsrenten", "styringsrenta"),
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.norges_bank:policy_rate",
        interfaces=("python", "cli", "gui"), table_id="IR/B.KPRA.SD.R",
        source_url="https://www.norges-bank.no/en/topics/statistics/Key-policy-rate-daily/",
        access_url="https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R", format="csv",
        methodology=("latest: siste publiserte observasjon; history: publiserte observasjoner fra valgt år.",
                     "Endring mellom faktiske endepunkter i prosentpoeng."),
    ),

    Dataset(
        id="ssb-07459-population",
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.ssb:municipality_population",
        interfaces=("python", "gui", "cli"),
        table_id="07459",
        source_url="https://www.ssb.no/statbank/table/07459",
        access_url="https://data.ssb.no/api/pxwebapi/v2/tables/07459/data",
        format="json-stat2",
        provider="ssb",
        title="Befolkning",
        topic="demography",
        source="SSB 07459",
        geography=("municipality",),
        time_resolution="year",
        dimensions=("geography", "year"),
        unit="persons",
        description=(
            "Folkemengde i norske kommuner over tid."
        ),
        period="1986–",
        measures=("population",),
        definition="Folkemengde etter SSBs kommunestatistikk.",
        aliases=("befolkning", "folketall", "innbyggere"),
    ),
    Dataset(
        id="valg-parliament-results",
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.elections:storting_party_history",
        interfaces=("python", "gui"),
        source_url="https://valgresultat.no",
        access_url="https://valgresultat.no/api",
        format="json",
        provider="elections",
        title="Stortingsvalg",
        topic="elections",
        source="Valgdirektoratet",
        geography=("municipality",),
        time_resolution="election",
        dimensions=("geography", "year", "party"),
        unit="votes_percent",
        description=(
            "Partienes resultater ved norske stortingsvalg."
        ),
        period="2009–2025 (implementerte årganger)",
        measures=("votes", "votes_percent"),
        definition=(
            "Offisielle valgresultater etter kommune og parti."
        ),
        limitations=(
            (
                "Historisk dekning avhenger av tilgjengelige "
                "valgdata."
            ),
        ),
        aliases=("stortingsvalg", "stortingsvalgresultat"),
    ),
    Dataset(
        id="valg-municipality-results",
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.elections:municipality_party_history",
        interfaces=("python", "gui"),
        source_url="https://valgresultat.no",
        access_url="https://valgresultat.no/api",
        format="json",
        provider="elections",
        title="Kommunevalg",
        topic="elections",
        source="Valgdirektoratet",
        geography=("municipality",),
        time_resolution="election",
        dimensions=("geography", "year", "party"),
        unit="votes_percent",
        description=(
            "Partienes resultater ved norske kommunevalg."
        ),
        period="2011–",
        measures=("votes", "votes_percent"),
        definition=(
            "Offisielle valgresultater etter kommune og parti."
        ),
        limitations=(
            (
                "Historisk dekning avhenger av tilgjengelige "
                "valgdata."
            ),
        ),
        aliases=("kommunevalg", "valgresultat", "valgresultater"),
    ),
    Dataset(
        id="nav-registered-unemployed",
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.nav:municipality_unemployment_since",
        interfaces=("python", "gui"),
        source_url="https://www.nav.no",
        format="csv",
        provider="nav",
        title="Registrerte helt ledige",
        topic="labour",
        source="NAV",
        geography=("municipality",),
        time_resolution="month",
        dimensions=("geography", "year", "month"),
        unit="persons_and_percent",
        description=(
            "NAV-registrerte helt ledige etter kommune og måned."
        ),
        period="1995–2025",
        measures=("unemployed", "percent"),
        definition=(
            "Personer registrert som helt ledige hos NAV."
        ),
        limitations=(
            "Serien kan inneholde brudd i statistikken.",
            "Må ikke forveksles med arbeidsledighet målt i AKU.",
        ),
        aliases=(
            "arbeidsledighet",
            "arbeidsledig",
            "arbeidsledige",
            "ledighet",
            "helt ledige",
        ),
    ),
    Dataset(
        id="statens-vegvesen-traffic-volume",
        support=SupportStatus.SUPPORTED,
        adapter="samfunnsdata.providers.norway.vegvesen:traffic_volume",
        interfaces=("python",),
        source_url="https://trafikkdata.atlas.vegvesen.no",
        access_url="https://trafikkdata.atlas.vegvesen.no/graphql",
        format="json",
        provider="vegvesen",
        title="Vegtrafikk / ÅDT",
        topic="transport / traffic",
        source="Statens vegvesen",
        geography=("road_reference",),
        time_resolution="year",
        dimensions=("road_reference", "since"),
        unit="vehicles_per_day",
        description="ÅDT-verdier for kjente vegreferanser med offisiell statens vegvesen-semantikk.",
        period="Publiserte ÅDT-/årsverdier",
        measures=("traffic_volume",),
        definition="Offisiell vegtrafikkmål for valgt vegreferanse; råkvalitet og beregningsmetode beholdes separat.",
        limitations=(
            "Sikkerst som historiske ÅDT-verdier for en konkret vegreferanse eller målepunkt.",
            "E6/E39 alene er ikke nok til å velge en stub eller et ukjent segment uten ekstra identifikator.",
        ),
        aliases=("trafikk", "trafikkmengde", "ådt", "adt", "vegtrafikk", "E6", "E39"),
    ),
)


DATASET_REGISTRY = DatasetRegistry(curated=DATASETS, discovered=DISCOVERED_DATASETS)


def rebuild_registry() -> DatasetRegistry:
    global DATASET_REGISTRY
    DATASET_REGISTRY = DatasetRegistry(curated=DATASETS, discovered=DISCOVERED_DATASETS)
    return DATASET_REGISTRY


def datasets() -> tuple[Dataset, ...]:
    return rebuild_registry().effective_datasets()


def _search_forms(word: str) -> set[str]:
    forms = {word}

    for suffix in ("ene", "en", "et", "a"):
        if word.endswith(suffix) and len(word) > len(suffix) + 3:
            forms.add(word[:-len(suffix)])

    return forms


def find_datasets(
    query: str,
    *,
    provider: str | None = None,
    support: SupportStatus | None = None,
) -> list[Dataset]:
    return rebuild_registry().search(query, provider=provider, support=support)


def get_dataset(dataset_id: str) -> Dataset:
    return rebuild_registry().get(dataset_id)
