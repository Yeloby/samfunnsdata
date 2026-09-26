# Samfunnsdata

**Offentlige data. Etterprøvbare svar.**

Samfunnsdata er et lokalt og åpent verktøy for å finne, forstå og bruke norske
offentlige data. Målet er å være tydelig om hva som faktisk er støttet, hva som
bare er katalogisert, og hva som fortsatt er planlagt. Programmet bygger på
lokale valg, tydelige grenser og etterprøvbare resultater, ikke på generiske
antagelser om store deler av det offentlige datagrunnlaget.

## Hva programmet kan gjøre i dag

- Se Norges Banks styringsrente og utviklingen i prosentpoeng
- Se befolkningsutvikling i en kommune over tid
- Sammenligne kommuner etter samme mål og samme tidsfilter
- Søk i en lokal katalog over offentlige datasett
- Se hvilke kilder som er støttet, hvilke som bare er oppdaget, og hvilke som
  fortsatt er planlagt
- Eksportere CSV og datakvitteringer når analysen faktisk støttes

## Eksempler

```bash
samfunnsdata population Trondheim --since 2010
samfunnsdata compare Trondheim Bergen --since 2010
samfunnsdata search "befolkning"
samfunnsdata rate
samfunnsdata rate --since 2015 --receipt rente.receipt.json
```

Dette er reelle kommandoer i prosjektet. De viser hvordan Samfunnsdata bruker en
lokalt validert analyseplan for å hente og presentere et kjent, støttet datasett
uten å gjøre vilkårlige antagelser om andre tabeller eller kilder.

## Støttet nå

Samfunnsdata støtter i dag et avgrenset, men tydelig utvalg av norske offentlige
kilder og analyser:

- SSB: befolkningsdata, sammenligninger og datakatalog
- Norges Bank: styringsrente, siste publiserte observasjon og historikk
- NAV: registrerte helt ledige
- Valgdirektoratet: partivalgssammenligninger der programmet faktisk har
  implementert støtten
- FHI: helsestatistikk og legemiddeldata via lokale Python- og API-løsninger

Dette er ikke et prosjekt som lover støtte for alle offentlige data. Det er et
lokalt, etterprøvbart verktøy med klare grenser.

## Katalogisert og planlagt

Samfunnsdata skiller tydelig mellom tre tilstander:

- Støttet: datasettet har en eksplisitt adapter og en faktisk analyseflyt i
  programmet.
- Katalogisert: metadata er oppdaget og lagret lokalt, men datasettet er ikke
  automatisk kjørbart eller semantisk støttet i Samfunnsdata.
- Planlagt: det finnes en realistisk målsetning om å støtte det senere, men det
  er ikke implementert ennå.

Den viktige regelen er enkel: oppdaget metadata kan fortelle deg at et datasett
finnes, men det kan ikke gi det kjørbar status i programmet.

## Et bredere offentlig datalandskap

Samfunnsdata er ment å vokse innenfor et realistisk, offentlig og norsk
datasettlandskap. Det omfatter blant annet:

- SSB / KOSTRA
- NAV
- FHI
- Valgdirektoratet
- Kartverket / Geonorge
- MET Norway / Frost
- Statens vegvesen / NVDB / Trafikkdata
- flere datasett fra Norges Bank
- NVE
- Brønnøysundregistrene
- Sokkeldirektoratet
- Enova
- Husbanken
- Udir / HK-dir / DBH
- relevante miljø-, transport-, fiskeri- og andre offentlige datakilder

Dette er en bred horisont, ikke en liste over noe som allerede er støttet. Det er
et mål for hvor Samfunnsdata kan bli nyttig, uten at det blir et løfte om å
støtte alt fra hver enkelt myndighet.

## Personvern og lokalt arbeid

Samfunnsdata prøver å gjøre mest mulig lokalt. GUI og CLI tolker spørsmål lokalt,
og analysene valideres før de kjøres. Katalogoppdateringer, cache og eksport
lagres i brukerens lokale miljø, og programmet har en eksplisitt `--cache-only`
modus som stopper nettverk uten å skjule hvilke datakilder som faktisk ble brukt.

Det betyr ikke at programmet er en anonymitetstjeneste eller en fullstendig
frakoblet løsning. Det betyr at nettverk, cache og datakilder håndteres med
klare grenser og tydelig dokumentasjon.

## Kom i gang

Installer prosjektet og skrivebordsintegrasjonen med:

```bash
./install.sh
```

Deretter kan du bruke CLI-en med:

```bash
samfunnsdata --help
```

Hvis du vil starte den grafiske brukerflaten, bruk den som passer for ditt miljø,
eller start prosjektet i ditt lokale utviklingsoppsett.

## Ambisjon

Samfunnsdata skal gjøre det enklere å bruke norske offentlige data uten å miste
kontrollen over kilde, metode og begrensning. Langsiktig mål er at brukeren skal
kunne finne relevante datasett, forstå hva som faktisk er støttet, og få
etterprøvbare svar som er tydelig knyttet til en reell datakilde.

Det er ikke et løfte om å støtte alle offentlige data eller å automatisere alt fra
alle myndigheter. Det er et arbeid mot mer forståelige, mer åpne og mer
etterprøvbare analyser innenfor et avgrenset og ryddig sett av datasett.

Styringsrenten vises med kildens observasjonsdato og enhet. I GUI kan du skrive
«Hva er styringsrenta?» eller «Vis styringsrenten siden 2015».
Se [styringsrente og begrensninger](docs/norges-bank.md) for detaljer.

Se [docs/architecture.md](docs/architecture.md) for mer om arkitekturen, og
[docs/privacy.md](docs/privacy.md) for personvern og nettverksmodell.
