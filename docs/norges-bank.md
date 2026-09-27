# Norges Bank: styringsrente og valutakurser

Samfunnsdata støtter styringsrenten `IR/B.KPRA.SD.R` og fem valutaserier
`EXR/B.<valuta>.NOK.SP`: EUR, USD, GBP, SEK og DKK. Reserverente, døgnlånsrente
og prognoser er ikke implementert.

## Offisielt grunnlag

Kontrollert 27. september 2026 (Europe/Oslo):

- [Norges Banks datatorg](https://www.norges-bank.no/tema/Statistikk/apne-data/)
  beskriver det offentlige REST-grensesnittet.
- [Veiledningen](https://www.norges-bank.no/en/topics/Statistics/open-data/guide-data-warehouse/)
  beskriver CSV-eksport og periodeparametre.
- [Offisiell dataflow og tilhørende strukturer](https://data.norges-bank.no/api/dataflow/NB/IR/latest?format=sdmx-json&references=all)
  identifiserer `NB:IR(1.1)` og `NB:DSD_IR(1.1)`.
- [Daglige observasjoner](https://www.norges-bank.no/en/topics/statistics/Key-policy-rate-daily/)
  viser styringsrenten med dato.
- [Styringsrenten](https://www.norges-bank.no/tema/pengepolitikk/Styringsrenten/)
  angir renten i prosent. En rentebeslutning eller prognose er ikke det samme
  som en observasjon i denne dataserien.
- [Opphavsrett og ansvar](https://www.norges-bank.no/Opphavsrett/) omtaler
  kildeangivelse og begrensninger ved gjenbruk. Ingen bestemt standardlisens
  er bekreftet for API-serien; kvitteringens lisensfelt er derfor null.

Ingen autentisering var nødvendig. Ingen numerisk kvote/rategrense ble funnet
på de gjennomgåtte offisielle sidene; dette er ikke et løfte om ubegrenset bruk.

## Kontrakt og observasjoner

Fast endpoint: `https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R`.
Parametre: `format=csv`, `locale=en`, og enten `lastNObservations=1`,
`startPeriod=YYYY-01-01` eller ingen periodeavgrensning for hele historikken.
Ingen bruker- eller metadatafelt får velge vert, sti eller serie.

| Felt | Krevd verdi / betydning |
|---|---|
| FREQ | B: virkedag |
| INSTRUMENT_TYPE | KPRA: styringsrente |
| TENOR | SD: styringsrente |
| UNIT_MEASURE | R: rente; vises i prosent |
| COLLECTION | E: slutten av dagen |
| DECIMALS | 2 |
| TIME_PERIOD | Kildens ISO-dato, YYYY-MM-DD |
| OBS_VALUE | Original CSV-verdi bevares som tekst; tom streng betyr manglende |
| CALC_METHOD | Original beregningsmetodekode bevares separat fra status |

Responsen er semikolonseparert CSV med én observasjon per rad. Parseren krever
kjente dimensjoner, avviser doble datoer og uventede felter og sorterer datoer
stigende. Dager som ikke forekommer, legges ikke til. Ingen interpolasjon,
fremføring eller erstatning med nærmeste dato skjer.

Den kontrollerte responsen har ikke `OBS_STATUS`. Parseren kan bevare denne
kolonnen hvis den finnes. Ikke-tom status eller annen beregningsmetode enn tom/`N` utelukker
verdien fra ukvalifiserte beregninger og graf; ukjente koder gis ingen oppdiktet
betydning. Kildeverdien og kodene beholdes i rådata, CSV og kvittering.
Manglende verdi og numerisk null behandles forskjellig.

Siste betyr siste publiserte observasjon med eksplisitt dato, ikke nødvendigvis
renten på dagens dato. Manglende/merket siste verdi erstattes ikke med en eldre.
Historikkens endring er siste minus første faktiske endepunkt i **prosentpoeng**,
ikke prosentvis endring. Et ubrukelig endepunkt gir ukjent endring.
Grafen viser punkter og forbinder ikke observasjoner over upubliserte dager.

## Bruk

```bash
samfunnsdata rate
samfunnsdata rate --since 2015 --receipt rente.receipt.json
samfunnsdata rate --history
samfunnsdata --cache-only rate --since 2015
```

GUI: «Hva er styringsrenta?», «Hva er styringsrenten?», «Vis styringsrenta»,
«Norges Banks styringsrente», «Styringsrente siden 2015» eller
«Hvordan har styringsrenta utviklet seg?». Den siste viser hele historikken;
«siden YEAR» avgrenser historikken. Normalisering, tolkning og planbygging er lokale.
Spørsmål om bestemte datoer/måneder, gjennomsnitt, prognoser, andre renter avvises. Befolkningsparserens tidsforståelse er uendret.

## Cache, kvittering og grensesnitt

ONLINE henter alltid valgt rente- eller valutaserie på nytt, slik at «siste» ikke låses til et
eldre cachetreff. Bare validerte svar publiseres atomisk i eksisterende JsonCache.
Tidligere cache beholdes ved mislykket henting; det skjer ingen skjult fallback.
CACHE_ONLY leser bare det samme lagrede utvalget. Cachebom eller korrupt post
feiler før nettverksgrensen kalles. Historikk og siste observasjon har separate
cachenøkler. Et større historikkutvalg brukes ikke automatisk til et annet utvalg.

Cacheposten inneholder responsens CSV og faktisk registrert hentetid.
Kvitteringen skiller denne fra analysens brukstid og registrerer cachetreff,
nettverksmodus, kildekontakt og QueryPlan-hash. Oppdateringstid hos kilden,
innholdshash og råfilreferanse er ukjent/null. Ingen lokal cachebane eller
spørsmålstekst inngår. Cachelagret «siste» vises med en eksplisitt advarsel.

Både CLI og GUI utfører en validert QueryPlan. GUI bruker eksisterende GuiJobs,
kansellering og generasjonsvern, og alle kildekall og grafer behandles i
arbeidstråden. Rådata, CSV, kvitteringsvisning og JSON-eksport er tilgjengelige.
Kvitteringsvisningen for denne serien viser strukturert JSON.

## Verifikasjon av API-kontrakten

Fixture `tests/fixtures/norges_bank_policy_rate.csv` er et lite offisielt svar
fra `startPeriod=2024-01-01&endPeriod=2024-01-05&format=csv&locale=en`:
fire observasjoner 2.–5. januar, alle med kildeverdi `4.5`. 1. januar finnes
ikke i responsen. Feil- og statusvarianter lages syntetisk i testene.

Etter fixturetestene ble én livekontroll kjørt gjennom provideren med
`lastNObservations=1`: HTTP 200, observasjonsdato `2026-09-24`, kildeverdi
`4.25`, tom CALC_METHOD, ingen OBS_STATUS-kolonne. Registrert hentetid:
`2026-09-26T23:53:09.565104+00:00`. Ingen redirect ble observert; forespurt og
endelig vert var `data.norges-bank.no`. Umiddelbar CACHE_ONLY-kjøring ga samme
observasjon og hentetid, `cache_hit=true`, `network_occurred=false` og ingen
HTTP-forespørsler. Livekontrollen inngår ikke i pytest og brukte midlertidig cache.

## Valuta: kildekontrakt og enheter

Kontrollert 27. september 2026. [EXR-strukturen](https://data.norges-bank.no/api/dataflow/NB/EXR/latest?format=sdmx-json&references=all)
oppgir NB:EXR(1.0), DSD_EXR(1.0) og dimensjonene FREQ, BASE_CUR, QUOTE_CUR,
TENOR og TIME_PERIOD. BASE_CUR er utenlandsk valuta; QUOTE_CUR er NOK.
FREQ=B er virkedag, TENOR=SP spot og COLLECTION=C bankens kode for
ECB-notering kl. 14:15 CET. Datoen er observasjonsdato, ikke hentedato.
[Bankens forklaring](https://www.norges-bank.no/en/topics/statistics/exchange_rates/valutakursar-faq/)
beskriver indikative midtkurser og publisering rundt kl. 16 på virkedager.

Alle eksemplene nedenfor er råverdier fra **2. januar 2024**, kontrollert i
[CSV](https://data.norges-bank.no/api/data/EXR/B.EUR+USD+GBP+SEK+DKK.NOK.SP?format=csv&locale=en&startPeriod=2024-01-02&endPeriod=2024-01-05)
og [Excel](https://data.norges-bank.no/api/data/EXR/B.EUR+USD+GBP+SEK+DKK.NOK.SP?format=excel-both&locale=en&startPeriod=2024-01-02&endPeriod=2024-01-02).

| Valuta | Serie i EXR | OBS_VALUE | UNIT | UNIT_MULT | DECIMALS | Offisielt noteringsgrunnlag / visning | Avledet normalisering |
|---|---|---|---|---|---|---|---|
| EUR | B.EUR.NOK.SP | 11.2815 | Ikke levert | 0 | 4 | 1 EUR = 11,2815 NOK | Ingen |
| USD | B.USD.NOK.SP | 10.2971 | Ikke levert | 0 | 4 | 1 USD = 10,2971 NOK | Ingen |
| GBP | B.GBP.NOK.SP | 13.0204 | Ikke levert | 0 | 4 | 1 GBP = 13,0204 NOK | Ingen |
| SEK | B.SEK.NOK.SP | 101.14 | Ikke levert | 2 | 2 | 100 SEK = 101,14 NOK | Ingen |
| DKK | B.DKK.NOK.SP | 151.33 | Ikke levert | 2 | 2 | 100 DKK = 151,33 NOK | Ingen |

**Kildefakta:** CSV/Excel leverer ingen UNIT, UNIT_MEASURE, OBS_STATUS eller
CALC_METHOD i dette utvalget. CALCULATED=false angir observert verdi.
UNIT_MULT-kodelisten navngir 0 som enheter og 2 som hundrere. DECIMALS angir
desimalpresisjon, ikke en ekstra skaleringsfaktor; originalteksten kan ha færre desimaler.

Den generelle UNIT_MULT-konseptteksten beskriver multiplikasjon med en tierpotens
for å uttrykke en verdi i UNIT. Den fastsetter ikke alene EXR-noteringsgrunnlaget,
og UNIT er ikke levert i EXR-strukturen. Samfunnsdata bruker derfor den eksplisitt
verifiserte valutakontrakten, ikke en generell SDMX-multiplikasjonsregel.

**Uavhengig kontroll av noteringen:** Norges Banks [Penger og Kreditt 4/2004,
tabell 35, trykt side 259](https://www.norges-bank.no/globalassets/upload/publikasjoner/penger_og_kreditt/2004-04/hele_heftet.pdf?v=09032017122249)
har kolonner merket 1 EUR, 100 DKK, 1 GBP, 100 SEK og 1 USD. For juli 2003
stemmer verdiene med [API-ets samme månedsserier](https://data.norges-bank.no/api/data/EXR/M.EUR+USD+GBP+SEK+DKK.NOK.SP?format=csv&locale=en&startPeriod=2003-07&endPeriod=2003-07):
EUR 8,2893; DKK 111,52; SEK 90,24; GBP 11,8356 og USD 7,2902 (de to siste
avrundet til 11,84 og 7,29 i trykksaken). Månedskontrollen underbygger
noteringsgrunnlaget; månedsgjennomsnitt implementeres ikke som analyse.

**Samfunnsdatas behandling:** Råtekst beholdes, tallet parses separat, og
presentasjonsverdien er identisk med den brukbare kildeverdien. Noteringsgrunnlag
er 1 eller 100 utenlandske valutaenheter. Verken `151.33 NOK per 1 DKK` eller
`15133 NOK per 100 DKK` er riktig presentasjon av DKK-eksemplet. Ingen verdi
normaliseres til NOK per én DKK/SEK. Kvitteringens metadata bevarer kildekoder,
UNIT=null, eksplisitt `quotation_basis`, `quotation_unit`,
`presentation_transform=identity` og `normalization=null`.

Parseren krever de verifiserte dimensjonene og CALCULATED=false. Ukjent
serie, multiplikator, metode for innsamling eller endret responsstruktur avvises.
Eventuelle OBS_STATUS/CALC_METHOD-kolonner bevares separat: ikke-tom status
og ukjent/avvikende metode gjør observasjonen ubrukelig i beregninger.
Tom metode og N er tillatt; N er bekreftet som normal metode i den
[gjeldende IR-kodelisten CALC_METHOD](https://data.norges-bank.no/api/dataflow/NB/IR/latest?format=sdmx-json&references=all).
Dette gjelder også styringsrenten. Tom kildeverdi håndteres konservativt som
manglende; tomme verdier og ekstra statuskolonner er syntetiske testtilfeller,
ikke påstått observert i det innhentede valutautvalget.

Fast endepunktstruktur er `https://data.norges-bank.no/api/data/EXR/B.<valuta>.NOK.SP`.
Bare fem lokalt validerte valutakoder kan fylle plassen. Parametre er `format=csv`,
`locale=en`, og `lastNObservations=1` for siste, valgfritt
`startPeriod=YYYY-01-01` for historikk. Cache bruker egen versjonert namespace,
hele serienøkkelen og samtlige parametre. Rente- og valutacache blandes ikke.

Historikkens eneste beregnede endring er siste minus første faktiske
observasjon i samme noteringsenhet, for eksempel **NOK per 100 DKK**.
Dette er verken prosent, prosentvis endring eller prosentpoeng. Manglende eller
merket endepunkt gir ukjent endring, også når andre observasjoner er brukbare.

```bash
samfunnsdata exchange EUR
samfunnsdata exchange USD --history
samfunnsdata exchange DKK --since 2020 --receipt valuta.receipt.json
samfunnsdata --cache-only exchange DKK --since 2020
```

GUI-former: «Hva er eurokursen?», «Hva er dollarkursen?», «Hva er EUR-kursen?»,
«Vis eurokursen siden 2020» og «Hvordan har dollarkursen utviklet seg?».
Pundkursen, GBP-/SEK-/DKK-kursen og «kursen på svenske/danske kroner» følger
samme mønster. Punktum, spørsmålstegn, utropstegn, store bokstaver og vanlig
variasjon i mellomrom håndteres lokalt. Ingen beløpsomregning, krysskurser,
andre valutaer, bestemte datoer, prognoser eller gjennomsnitt tolkes.

Valuta bruker uendret kvittering v3, samme GUI-jobber og samme eksportflyt som
renten. CSV og rådatavisning oppgir noteringsenheten; grafaksen gjør det samme.
Fixtures dekker alle fem valutaer og tester at råverdier aldri skaleres feil.

## Livekontroll av valuta

Etter grønne offline-tester ble `EXR/B.DKK.NOK.SP` hentet gjennom provideren
med `format=csv&locale=en&lastNObservations=1`. HTTP 200, endelig vert
`data.norges-bank.no`; FREQ=B, BASE_CUR=DKK, QUOTE_CUR=NOK, TENOR=SP,
UNIT_MULT=2, DECIMALS=2, COLLECTION=C, CALCULATED=false.
Observasjon: **2026-09-25**, råverdi **145.01**, uten OBS_STATUS/CALC_METHOD.
Hentetid: **2026-09-27T00:27:05.446108+00:00**.

Umiddelbar CACHE_ONLY-kjøring av identisk utvalg ga samme observasjoner og
hentetid, cachetreff og **null HTTP-kall**. Nettverksgrensen var erstattet med
en feilutløsende vakt under cachekontrollen.

Bankens [menneskelesbare Excel-uttrekk for samme dato](https://data.norges-bank.no/api/data/EXR/B.DKK.NOK.SP?format=excel-both&locale=en&startPeriod=2026-09-25&endPeriod=2026-09-25)
viste 145.01 og UNIT_MULT=2/Hundreds. Dette bekrefter samsvar mellom formater;
noteringsretningen støttes i tillegg av den uavhengige trykte tabellen ovenfor.
Direkte kontroll av nettsidens interaktive valutakomponent var utilgjengelig
på grunn av HTTP 429. Ingen gjentatte forsøk eller omgåelse ble brukt.
Livekontrollene er ikke del av pytest og bruker ingen permanent brukercache.
