# Samfunnsdata: implementert arkitektur

Samfunnsdata er en lokal Python/GTK-applikasjon. Parseren gjenkjenner bestemte
spørsmålsformer; katalogen beskriver et lite utvalg datasett. En katalogoppføring
med SUPPORTED betyr eksplisitt adapter og grensesnitt, ikke støtte for vilkårlige
utvalg. DISCOVERED og PLANNED er ikke kjørbare. FHI-legemidler er fortsatt bare
Python/API. NAV, kommunevalg og stortingsvalg beholder sine eksisterende analyseveier.

## Befolkning: én applikasjonsgrense

```text
GUI-spørsmål / manuelle valg          CLI population / compare
             |                               |
      parser og routing                      |
             |                               |
      GuiJobs -> gui_work -------------------+
                             |
                 population.analyze_population
                             |
          eksisterende SSB municipality_population
          -> kommunenavn/kodeliste -> 07459 -> JsonCache/HTTP
          -> JSON-stat -> dataframe med status og metadata
                             |
          filter_since + summarize_series (eksisterende regler)
                             |
                  AnalysisResult + DataReceipt
                             |
           presentasjon / graf / rådata / CSV / JSON
```

`results.py` har frosne, enkle dataklasser for første befolkningsvertikal.
`AnalysisResult` har tittel, skjemaversjon, deklarative graf-/tabellhint og
`DataReceipt`. Serier og advarsler eksponeres gjennom resultatet, uten duplisert
sannhetskilde. Dette er ikke en universell providerrespons. Ingen provider får
ny signatur, og rå providerdata presses ikke inn i et nytt felles dataframeformat.

Hver `PopulationSeries` har stabil identitet innen resultatet, kommunenavn/-kode,
forespurt utvalg, kildens returnerte periode før lokalt årsfilter,
`source_observations`, `derived_facts`, status-tilgjengelighet, proveniens og
kildemetadata. Sammenligning støtter et vilkårlig antall navngitte serier i
applikasjonslaget og CLI; eksisterende GUI/parser har fortsatt to kommunevalg.
Kommunene beholder egne perioder. Den eldre befolkningssammenligningen viste
seriene side om side uten å beregne en differanse mellom kommunene; det beholdes.
Ulike perioder gir en eksplisitt advarsel i kvitteringen.

## Kildeverdier, beregninger og versjoner

`Observation.source_value` er kildeverdien (manglende representeres som `None`).
Rå statuskode og periodekode/-etikett beholdes. `usable_value` er verdien etter
analysens konservative status-/tallkontroll, brukt i graf og tekst. Det er ikke
et nytt kildetall. Alle ikke-tomme statuskoder utelates fra ukvalifiserte
beregninger, uten at ukjente koder gis en oppdiktet betydning.
`SeriesSummary` under `derived_facts` inneholder de faktiske endepunktene,
kvalifiserte endpointverdier og beregnet absolutt/prosentvis endring.

Milepæl A-reglene gjelder fortsatt: null er et tall, manglende endepunkter
byttes aldri ut med eldre verdier, og prosentvis endring fra null er ukjent.
Grafen har hull ved manglende/statusmerkede punkter, mens CSV beholder
originalverdier og status. Valgsammenligning bruker felles valgår og avviser
manglende/statusmerkede endepunkter; dette er ikke endret i D.

`AnalysisResult.schema_version` er fast `"1"` i dagens implementasjon. `DataReceipt.schema_version` har standardverdi `"2"`, og koden i `results.py` godtar `"1"` og `"2"` for befolkning og `"3"` for tidsserier fra milepæl I, men avviser andre verdier. Adapter-/beregningskontrakten identifiseres med `ssb-population/1`, og appversjonen registreres. Ukjente skjemaversjoner avvises ved innlesing. Brudd i feltenes betydning eller struktur krever ny versjon og eksplisitt lesestøtte.

`DataReceipt` har kilde, måltall/enhet, serier, strukturerte transformasjoner,
advarsler og brukstidspunkt. Stegene beskriver kommunevalg, lokal periodeavgrensning,
absolutt/prosentvis endring og sideordnet sammenligning; de er ikke kjørbar kode.
Referanser til input/output er relative til hver angitt serie.
Tabell-ID, måltallskode, utvalg og URL-er kommer fra eksisterende adapter/katalog.
Katalogtittelen «Befolkning» er ikke utgitt for å være en full offisiell tabelltittel.

Milestone F legger til et lokalt katalogregister som kombinerer kuraterte datasett,
oppdagede SSB-tabeller og støttestatus. Oppdaget metadata er data, ikke kode: det
kan beskrive tabellen, men det kan ikke self-approve som støttet eller kjørbart.
Data → Bla gjennom datakatalog viser den effektive katalogen; Data → Oppdater
datakatalog henter SSB-katalogmetadata i bakgrunnen når programmet er online. Katalogoppdateringer lagres som versjonerte JSON-snapshots i lokal cache og erstatter ikke eldre snapshot atomisk dersom oppdateringen feiler.

Kildens JSON-stat-metadata kopieres fra attrs til en uavhengig, uforanderlig
JSON-snapshot i kontrakten. I kvitteringens wireformat er `provider_metadata` et
vanlig JSON-objekt. GUI/CLI trenger ikke attrs eller SSB-kolonnenavn for å rekonstruere
svaret. Providerens rå metadata kan fortsatt inneholde egne dimensjonsnavn.

## Hentetid, cache og ærlig uvisshet

SSB-provider viderefører cachetreff og hentetid for dataforespørselen gjennom
`network_access`. `cache_hit` viser om data kom fra cache; `fetched_at` settes
fra nettverkskallets fullføringstid ved ny henting og er null ved cachetreff.
Eldre eller alternative providerresponser uten disse feltene gir null.
`content_hash` og `raw_data_reference` er fortsatt null.
`used_at` er UTC-tidspunktet da applikasjonsresultatet ble konstruert. Det er aldri
bevis på ny kildehenting. Kildens `updated` kopieres når tilgjengelig; ellers null.
Lisens er null fordi den ikke finnes i eksisterende konfigurasjon/metadataflyt.

Ingen fil-mtime leses som kildehentetid. Ingen historiske cacheposter omskrives.
Cachefilens SHA-256 identifiserer forespørselen, ikke responsinnholdet, og brukes
aldri som innholdshash. JsonCache publiserer JSON atomisk og behandler korrupt JSON
som cachebom (milepæl A). Cachen lagrer reserialisert JSON, ikke originale HTTP-bytes.
Det finnes en eksplisitt `ONLINE`/`CACHE_ONLY`-modi i den delte nettverksgrensen.
`CACHE_ONLY` tillater bare lokale cachetreff og feiler tydelig ved cachebom uten å
lage nye HTTP-kall. Det finnes ikke et bredt cachemanifest som er nødvendig for
nåværende datamodeller; eldre cacheposter leses fortsatt som før.

`None` skiller ukjent fra `False`, nullverdi og tom liste. Tom advarselliste betyr
ingen påviste advarsler i disse kontrollene, ikke komplett kvalitetsgaranti.
`status_available` skiller manglende statuskolonne fra en kjent kolonne uten
markeringer. Kildekodene `None`, tom streng og ikke-tomme koder beholdes separat.

## GUI, CLI og eksport

Milepæl B bruker `GuiJobs`: per vindu maks to arbeidstråder og én utskiftbar ventende
jobb. Generasjons-ID og kansellering hindrer eldre svar/feil i å overskrive nyere
resultat. GTK oppdateres bare på hovedtråden. Lukking og ny analyse ugyldiggjør jobber.
Et pågående HTTP-kall kan ikke avbrytes fysisk. Matplotlib opprettes/rendres/ryddes
under en prosesslås med unike midlertidige filer; bildebytes leveres tilbake.
NAVs eksisterende filcache beskyttes av en GUI-lås rundt henting og parsing.

Befolkningstjenesten sjekker jobbtokens mellom providerkall. `gui_work` renderer
resultatet; GTK leser ikke SSB-kolonner. Handlingene «Vis datakvittering» og
«Eksporter kvittering (JSON)» gjelder gjeldende befolknings-, rente- eller
valutaresultat.
Kvitteringstekst/eksport forberedes i arbeidstråd; sene filvalg og kvitteringsvinduer
følger samme generasjonsvern. Innsetting av ferdig tekst i GTK skjer på hovedtråden;
stor tabellvirtualisering er ikke implementert.

`population_presentation.summary_text` bruker samme fakta for GUI og CLI.
CLI-kommandoene beholder tekst/grafvalg og får `--receipt PATH`.
CSV beholder Kommune, År, Innbyggere og status når tilgjengelig, UTF-8 med BOM.
JSON eksporteres separat, eksempelvis `population.csv` og `population.receipt.json`.
Brukeren velger filene separat; ingen sidefil overskrives automatisk.
JSON bruker UTF-8, sorterte feltnavn, eksplisitt versjon, ISO 8601-tider og null.
Serialisering/gjenlesing bevarer semantikken; samme kvittering gir identiske bytes.
Nye analyser får nytt brukstidspunkt, så ulike kjøringer er ikke byteidentiske.

## QueryPlan: deklarative, validerte planer

QueryPlan er en liten, deklarativ plan for å beskrive en analyse uten å gi
vilkårlige remote metadata en egen utøvende rolle. En plan inneholder
`dataset_id`, `operation`, `filters`, `measure`, `grouping`, `ordering`, `limit`
og `schema_version`.

Valideringen skjer lokalt før en plan kan utføres. `validate_query_plan` kontrollerer
at schemaversionen er støttet, at datasettet faktisk finnes, at det er merket som
`SUPPORTED`, at operasjonen er tillatt, at måltallet er kjent og at filterene er
forventede dimensjoner med gyldige verdier. En plan kan ikke bli et kjørbart
program bare fordi en oppdaget SSB-tabell ser relevant ut i metadata.

Planutføreren har eksplisitte lokale bindinger for fire datasett:

- `ssb-07459-population`: `lookup` via `population.analyze_population`.
- `norges-bank-policy-rate`: `latest`/`history` via `rates.analyze_rate`.
- `norges-bank-exchange-rate`: `latest`/`history` via `exchange.analyze_exchange`.
- `statens-vegvesen-traffic-volume`: `latest`/`history` via
  `providers.norway.vegvesen.traffic_volume`.

NAV, valg og FHI bruker fortsatt sine egne analyseveier.
Ikke-tomme `grouping`/`ordering` og en satt `limit` avvises fordi utføreren
ikke implementerer dem. Ukjente felt og feil JSON-typer avvises; år og
skjemaversjon må være heltall, ikke tekst, desimaltall eller boolske verdier.
Kommunealiasene `municipality`, `geography` og `place` støttes likt ved
validering og kjøring, men flere aliaser i samme plan avvises som tvetydig.
Planens opprinnelige alias beholdes i serialisering og kvitteringshash.

Planer kan serialiseres med `to_json()`, parses tilbake med `from_json()`, og
konsistent normaliseres før hashberegning. Hashen er deterministisk og brukes i
kvitteringen som `query_plan_hash`, sammen med eksisterende proveniens og
kildemetadata. Det er derfor mulig å spore hvilken plan som ble brukt uten å
lagre det originale fritekstspørsmålet i kvitteringen.

Dette er et bevisst defensivt design: det gjør det tydelig hva som er planlagt,
validerbart og faktisk utørlig, og skiller det fra katalogisert metadata som bare
forteller at et datasett finnes.

## Videre arbeid, ikke implementert

Felles nettverks-/personverntransport, SSB-katalogoppdatering og et lokalt
begrepsregister er implementert. Generell discovery på tvers av kilder, fri
språkforståelse, RDF, nye databaser, krysskildeanalyse og migrering av FHI/NAV/valg
til den felles resultatkontrakten gjenstår. DuckDB er allerede deklarert som avhengighet, men brukes ikke
som nytt lager i dette prosjektet.
Se [personvern](privacy.md) for faktisk nettverks- og lokal lagringsatferd og
[README.md](../README.md) for prosjektets publiserte bruksscenarioer.


## Milepæl I: Norges Bank

Norges Bank bruker samme SourceRegistry/DatasetRegistry, nettverksgrense,
JsonCache, QueryPlan og AnalysisResult/DataReceipt. En eksplisitt lokal gren i
QueryPlan velger `rates.analyze_rate`; katalogens adaptertekst kjøres aldri.
`latest` krever tomt filter, `history` tillater bare valgfritt heltall `since`
(1–9999). Ukjente felt, URL-er og uimplementerte valg avvises før kildekontakt.
Planlegging, validering og hashing for rentedata er nettverksfrie.

Den eksisterende kommuneformen beholdes for befolkning, inkludert kvittering
v1/v2 og beregningene. Kvittering v3 bruker `TimeSeries`, `SeriesSelection`,
`SeriesFacts` og `TimeObservation` i samme resultatkontrakt. Datoer har egne
periodefelt; renter presses ikke inn i kommune-/innbyggertallfelter.
`TimeObservation` bevarer CALC_METHOD separat fra OBS_STATUS. V3 leses eksplisitt;
ukjente versjoner og feil serietype for valgt versjon avvises. Befolkningens
wireformat er uendret. AnalysisResult beholder versjon 1 og oppgir tabellhint.

GUI-spørsmål går via QueryPlan i eksisterende arbeidstråd. Samme generasjonsvern
beskytter resultater, kvittering og eksport; matplotlib beholder prosesslåsen.
CLI `rate` bruker samme tjeneste og presentasjon. Renteendring beregnes i
prosentpoeng med faktiske endepunkter, uten prosentvis endring eller interpolasjon.
[API-kontrakten](norges-bank.md) beskriver offisiell dokumentasjon, semantikk,
cache, begrensninger og livekontroll. Ingen nye avhengigheter er lagt til.

## Valutakurser

`norges_bank_exchange` validerer fem faste EXR-serier og alle kildeattributter
som styrer noteringen. QueryPlan har en eksplisitt lokal binding til
`exchange.analyze_exchange`; obligatorisk `currency` og valgfritt heltall `since`
er de eneste filtrene. Operasjonene er `latest` og `history`. Ingen metadata
velger utfører, URL eller nye parameternavn. Nettverksgrensen er uendret.

Kvittering v3 gjenbrukes uten endring av wireformatet. Kildens `OBS_VALUE`
beholdes som tekst, mens `usable_value` er den numeriske verdien når status
tillater bruk. Metadata bevarer kildeattributtene og et eksplisitt
noteringsgrunnlag. Manglende UNIT er null; NOK kommer fra QUOTE_CUR.
Presentasjonen er identitet, og ingen normalisert verdi beregnes. Historikkens
differanse bruker samme enhet som kilden, eksempelvis NOK per 100 DKK.

CLI og GUI bruker samme tjeneste og presentasjonsmodul. GUI bruker eksisterende
GuiJobs, generasjonsvern, kansellering, matplotlib-lås og eksportflyt. Grafen
viser bare kildepunkter. Permanente golden-tester bevarer befolkningens v1/v2-JSON.
Se [kildeoversikten](data-sources.md) for videre kandidater og
[Norges Bank-kontrakten](norges-bank.md) for kildebevis og cache.


## Trafikkdata

QueryPlan binder `statens-vegvesen-traffic-volume` til `vegvesen.traffic_volume`.
`road_reference` er obligatorisk; `history` tillater valgfritt heltall `since`
fra 1900. `latest` tillater ikke `since`. Adapteren velger ett
trafikkregistreringspunkt gjennom et GraphQL-søk og henter publiserte årsverdier.
Resultatet bruker `TimeSeries` og datakvittering v3. Trafikkdata lagres ikke i
cache; `CACHE_ONLY` feiler uten nettverkskall. Python/API og QueryPlan er
implementert, men CLI har ingen trafikkkommando og GUI har ingen trafikkhandler.
