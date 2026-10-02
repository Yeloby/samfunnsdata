# Etterprøvbare befolkningsresultater (milepæl D)

Utgangspunkt: `576c756e6b449f75eca247d7a008fb79387afeb5` (193 tester).
Omfang: SSB 07459, én kommune og kommunesammenligning. Provider, parser og
cacheformat er uendret. Ingen nye avhengigheter.

## Spor gjennom eksisterende flyt

| Trinn | Tilgjengelig informasjon / betydning |
|---|---|
| Spørsmål/manuelle valg/CLI | Kommunenavn, valgfri sammenligningskommune, `since`. Ingen kommunekode ennå. |
| SSB kodeliste | Navn og kode i `agg_KommSummer`. |
| SSB dataforespørsel | Tabell 07459, Region, Personer1, Tid=*, aggregert kommuneserie, norsk JSON-stat2. |
| Cache/HTTP | JSON-payload; ingen hentemanifest; cachetreff og hentetid ved ny henting videreføres. Cachehash er forespørselsidentitet. |
| Konvertering | Periodekoder/etiketter, kildeverdier, status; øvrig JSON-stat-metadata i attrs. |
| Katalog | Befolkningstittel, kilde-/API-URL og enhet persons. Ingen registrert lisens. |
| Analyse | Lokal periodefiltrering, faktiske endepunkter, statuskontroll, absolutt/prosentvis endring. |
| Resultat D | Uavhengige typed felt/snapshots, kildeperiode før filter og faktisk brukt periode, kilde og beregning adskilt. |
| Presentasjon D | GUI/CLI/graf/rådata/CSV leser resultatsseriene; kvittering kan vises og eksporteres separat. |

Brukstid registreres separat. Ved ny henting registreres nettverkskallets
fullføringstid; opprinnelig hentetid for cacheposter er fortsatt ukjent. Metadata som ikke
finnes i payload/katalog fylles ikke med gjettede opplysninger.

## Bruk

GUI: analyser befolkning, velg «Vis datakvittering» eller «Eksporter kvittering
(JSON)». «Eksporter CSV» gir fortsatt separat tabell. Begge eksporter gjelder
gjeldende analyse. Ny analyse/nullstilling deaktiverer kvitteringshandlingene.

```sh
samfunnsdata population Trondheim --since 2000 --receipt population.receipt.json
samfunnsdata compare Trondheim Bergen Ås --since 2000 --receipt comparison.receipt.json
```

`DataReceipt.from_json(receipt.to_json())` bevarer kontrakten. JSON har eksplisitt
skjemaversjon og strukturerte kildeobservasjoner/beregningssteg. Metadata i wireformat
er ordinær JSON. `cache_hit` og `fetched_at` videreføres når provideren har dem;
`fetched_at` er null ved cachetreff. `content_hash`, `raw_data_reference` og
lisens er fortsatt ukjente; `used_at` er kun konstruksjonstidspunktet.

## Kompatibilitet og bevis

Offline regresjonstester dekker enkel-/flerkommuneresultat, null, manglende og
statusmerkede endepunkter og mellompunkter, egne perioder, source/derived,
metadata som overlever endrede attrs, deterministisk JSON/gjenlesing, cache uten
falsk hentetid, faktabaserte grafer, CSV, CLI og GUI-kvittering. GUI-testene dekker
arbeidstråd, avbryt/nullstill/lukk og foreldet eksportdialog. Milepæl B-testene
beholder samtidighetskravene; bare to dataframe-spesifikke metadataasserts er
oppdatert til tilsvarende kontraktfelt.

En separat sammenligning mot startcommit bestod 48 syntetiske scenarier
(12 datatilfeller × én/to kommuner × med/uten årsfilter) og kontrollerte
GUI-tekst, perioder, beregninger, grafpunkter, CSV-verdier, rådatatekst og CLI-output.
Bevisste presentasjonsendringer: nye kvitteringshandlinger og `--receipt`, tydelige
advarsler/ukjent proveniens i kvitteringen, samt escaping av kommunenavn i GTK-markup.
Manglende kildeverdier i statusmerket råtekst omtales med kontraktens `None` fremfor
pandas sin `nan`; kildeverdien er fortsatt manglende. Feilmelding ved tom periode
inkluderer nå kommune og ønsket fra-år. Ingen statistiske beregningsregler endres.
