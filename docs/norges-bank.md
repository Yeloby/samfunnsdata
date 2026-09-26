# Norges Bank: styringsrente

Samfunnsdata støtter én serie: `IR/B.KPRA.SD.R`. Valutakurser, reserverente,
døgnlånsrente, prognoser og andre Norges Bank-serier er ikke implementert.

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
kolonnen hvis den finnes. Ikke-tom status eller beregningsmetode utelukker
verdien fra ukvalifiserte beregninger og graf; ukjente koder gis ingen oppdiktet
betydning. Kildeverdien og kodene beholdes i rådata, CSV og kvittering.
Manglende verdi og numerisk null behandles forskjellig.

Siste betyr siste publiserte observasjon med eksplisitt dato, ikke nødvendigvis
renten på dagens dato. Manglende/merket siste verdi erstattes ikke med en eldre.
Historikkens endring er siste minus første faktiske endepunkt i **prosentpoeng**,
ikke prosentvis endring. Et ukvalifisert endepunkt gir ukjent endring.
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
Spørsmål om bestemte datoer/måneder, gjennomsnitt, prognoser, andre renter og
valutakurser avvises. Befolkningsparserens tidsforståelse er uendret.

## Cache, kvittering og grensesnitt

ONLINE henter alltid denne serien på nytt, slik at «siste» ikke låses til et
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
