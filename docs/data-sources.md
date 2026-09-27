# Norske offentlige datakilder

Samfunnsdata skal gjøre flere norske offentlige datasett tilgjengelige lokalt.
Oversikten nedenfor skiller dagens funksjoner fra mulige utvidelser. Tilgangspunkter
og dokumentasjon er kontrollert mot myndighetenes egne sider 27. september 2026;
dette er ikke en driftstest av alle tjenestene eller et løfte om framtidig støtte.

- **SUPPORTED / støttet:** et bestemt datasett har lokal adapter, validering og oppgitte grensesnitt.
- **DISCOVERED / katalogisert:** metadata finnes i programmets katalog, uten kjørbar analyse.
- **PLANNED / kandidat:** mulig framtidig integrasjon. Denne oversikten registrerer ingen nye utførere.

Støttestatus gjelder datasettet og grensesnittet, ikke hele myndigheten. Eksterne
metadata kan ikke velge programkode eller gjøre et datasett kjørbart.

## Tilgjengelig i Samfunnsdata

| Myndighet og maskintilgang | Støttet utvalg og grensesnitt | Begrensning |
|---|---|---|
| SSB — [PxWebApi v2](https://www.ssb.no/api/pxwebapiv2), JSON-stat/CSV | SUPPORTED: kommunebefolkning, tabell 07459, Python/CLI/GUI. DISCOVERED: øvrige importerte katalogmetadata. | CC BY 4.0; kommunegrenser, tidsserier og måltall må tolkes per tabell. Katalogsøk gir ikke generell analyseadgang. |
| Norges Bank — [datatorgets API](https://www.norges-bank.no/en/topics/Statistics/open-data/guide-data-warehouse/), SDMX/CSV | SUPPORTED: styringsrente og EUR/USD/GBP/SEK/DKK mot NOK, Python/CLI/GUI. | Bare de eksplisitte seriene. [Kontrakt og noteringsgrunnlag](norges-bank.md); ingen bekreftet standardlisens i kvitteringen. |
| NAV — [åpne data og CSV](https://www.nav.no/no/nav-og-samfunn/statistikk/flere-statistikkomrader/relatert-informasjon/apne-data-fra-nav) | SUPPORTED: registrerte helt ledige etter kommune, Python/GUI. | Implementert historisk CSV-utvalg 1995–2025; registrert ledighet er ikke AKU. Flere NAV-data er kandidater. |
| Valgdirektoratet — [offisielle resultatgrensesnitt](https://www.valg.no/om-valgdirektoratet/om-valgdirektoratet/pressesider/API-med-valgresultater/), JSON | SUPPORTED: implementerte stortings- og kommunevalgår, partiresultater og sammenligninger, Python/GUI. | Årgang, geografi og opptellingsstatus betyr noe. Ulike publiseringskanaler har ulike tilgangskrav; ikke generell tilgang til EVA. |
| FHI — [Statistikk Open API](https://statistikk-data.fhi.no/swagger/index.html), dokumentert [av FHI](https://www.fhi.no/ta/statistikkalender_og_statistikk/apen-api-og-statistikk/) | SUPPORTED: avgrenset legemiddeladapter, Python/API. | Ingen FHI-spørsmål i GUI. Skjulte tall, ATC-grupper og ulike måltall kan ikke summeres ukritisk. Andre tabeller er kandidater. |

## Kandidater med dokumentert maskintilgang

Alle radene her har status **PLANNED / kandidat**, ikke SUPPORTED eller automatisk
DISCOVERED i programmet. Der standardlisens ikke er bekreftet nedenfor, må vilkår
avklares for det konkrete datasettet før integrasjon.

| Myndighet / område | Offisielt tilgangspunkt og format | Nyttige første utvalg og viktige begrensninger |
|---|---|---|
| SSB / KOSTRA — kommunale tjenester og økonomi | [KOSTRA](https://www.ssb.no/offentlig-sektor/kostra/statistikk/kostra-kommune-stat-rapportering) via [PxWebApi v2](https://www.ssb.no/api/pxwebapi), JSON-stat/CSV | Driftsutgifter, tjenestedekning, bolig og kommunegjeld. CC BY 4.0; foreløpige/reviderte tall, konsern kontra kommune og grenseendringer må skilles. |
| Kartverket / Geonorge — geografi | [Nedlastings-API](https://nedlasting.geonorge.no/help/documentation) og [API-oversikt](https://www.geonorge.no/verktoy/APIer-og-grensesnitt/); metadata, filnedlasting, WFS/WCS | Administrative grenser og kartgrunnlag. Format, koordinatsystem, lisens og eventuell innlogging følger hvert datasett; eiendomsdata er ikke nødvendigvis åpne. |
| Meteorologisk institutt — vær og klima | [Frost](https://frost.met.no/api.html), REST/JSON-LD; [autentisering](https://frost.met.no/authentication.html) | Temperatur, nedbør og stasjonsserier. Krever klient-ID; måleintervall, kvalitetsflagg og stasjonsflytting må bevares. |
| Statens vegvesen / NVDB — vegnett | [NVDB API Les v4](https://nvdbapiles.atlas.vegvesen.no/), REST/OpenAPI | Vegobjekter, veglenker og vegreferanser. NLOD; API-versjon, eventuell autentisering og objektenes gyldighet må håndteres. |
| Statens vegvesen / Trafikkdata — transport | [Offisielt API-datasett](https://dataut.vegvesen.no/dataset/trafikkdata/resource/968a10a7-f704-4cd7-9795-de69e8cad2bc), JSON; [API-veiledning](https://trafikkdata.atlas.vegvesen.no/#/om-api) | Trafikkvolum per målested, retning og tidsintervall. NLOD; aggregerte data, ikke individuelle kjøretøy. Kvalitetsmål og ufullstendig dekning må følge tallene. |
| NVE — vann og energi | [HydAPI](https://api.nve.no/doc/hydrologiske-data/), REST/JSON | Vannføring, vannstand, snø og grunnvann. Registrering/API-nøkkel kreves; foreløpige målinger og kvalitetsangivelser må skilles. Hydrologi er ikke det samme som kraftproduksjon. |
| Brønnøysundregistrene — virksomheter | [Enhetsregisteret](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/index.html), REST/JSON og bulkfiler | Enheter, næringskoder og geografisk fordeling. NLOD; dagens register er ikke en ferdig historisk statistikk. Autoriserte personopplysninger faller utenfor åpent utvalg. |
| Sokkeldirektoratet — petroleum og gassinfrastruktur | [Faktakartets datatjenester](https://factmaps.sodir.no/api/rest/services), ArcGIS REST; [dataserviceoversikt](https://www.sodir.no/4adca7/globalassets/1-sodir/om-oss/informasjonstjenester/karttjenester/factpages_dataservice.pdf) | Felt, brønner, innretninger og rørledninger. Kontroller lag, koordinater, produksjonsenheter og oppdateringsdato; kartobjekter må ikke behandles som produksjonstall. |
| Enova — energi og bygninger | [Data- og API-portal](https://data.enova.no/products), dokumentert [av Enova](https://www.enova.no/om-enova/drift/deling-av-data-fra-enova/) | Energimerker for bygg. API-abonnement/nøkkel og virksomhetstilgang kan kreves; verifiser produktvilkår og personvern før utvalg. |
| Husbanken — bolig og boligsosiale virkemidler | [Åpne datasett](https://statistikk.husbanken.no/datasett/datasett), CSV | Lån, tilskudd og bostøtte. Saksopplysninger kan endres mellom uttrekk; rådata og publiserte rapporttall kan avvike. Kontroll av skjerming og vilkår per fil. |
| Utdanningsdirektoratet — grunnopplæring | [API-konsoll](https://apikonsoll.statistikkbanken.udir.no/), eksport-API og CSV; [vilkår](https://www.udir.no/om-udir/data) | Elevundersøkelsens indikatorer, mobbing og deltakelse. NLOD; små grupper, skjerming, svarandel og endrede spørsmål begrenser sammenligning. |
| HK-dir / DBH — høyere utdanning | [API-dokumentasjon](https://dbh.hkdir.no/static/files/dokumenter/api/api_dokumentasjon.pdf), HTTPS/JSON/CSV; [tabellkatalog](https://dbh.hkdir.no/api/Tabeller/) | Studenter, kandidater og institusjonsstatistikk. Åpne aggregater uten innlogging; små tall skjermes, institusjonsspesifikke data kan kreve tilgang. NLOD og DBHs kilde-/presentasjonsvilkår gjelder. |
| Miljødirektoratet — miljø | [Luftmålingenes offentlige API](https://api-luftmalinger.miljodirektoratet.no/), OpenAPI | Luftkvalitet og målestasjoner. Stoff, måleenhet, tidsmiddel og valideringsstatus må beholdes; avklar tjenestens gjenbruksvilkår. |
| Fiskeridirektoratet — fiskeri og akvakultur | [API-katalog](https://www.fiskeridir.no/statistikk-tall-og-analyse/api-katalog), samt [GIS-tjenester](https://gis.fiskeridir.no/server/rest/services) | Dokumenterte fiskeri-/akvakulturutvalg og geografiske lokaliteter. NLOD; tilgang og eventuell skjerming er datasettspesifikk. Fangst, landing og produksjon er ulike mål. |
| DFØ — offentlige finanser | [Statsregnskapets råfiler](https://statsregnskapet.dfo.no/last-ned), CSV | Utgifter og inntekter etter kapittel/post fra 2014. Månedstall, hittil-i-år og årsregnskap må skilles; desember bekreftes senere. Vilkår avklares ved integrasjon. |
| Norges Bank — statsgjeld | [Datatorgets dokumenterte seriekategorier](https://www.norges-bank.no/en/topics/Statistics/open-data/guide-data-warehouse/), SDMX/CSV | Statsgjeld er tilgjengelig som egen kategori, men ingen gjeldsserie er implementert. Utestående beholdning, transaksjon, rente og markedsverdi trenger ulike kontrakter. |

## Kriminalitet, rettsvesen og forsvar

Disse områdene har realistiske innganger gjennom offisiell aggregert statistikk:

- **Kriminalitet/politi:** SSBs [anmeldte lovbrudd og ofre](https://www.ssb.no/sosiale-forhold-og-kriminalitet/kriminalitet-og-rettsvesen/statistikk/anmeldte-lovbrudd-og-ofre)
  har Statistikkbank-tabeller som kan hentes med PxWebApi. Anmeldelser må ikke
  framstilles som alle faktisk begåtte lovbrudd; endringer i registrering påvirker seriene.
- **Rettsvesen:** SSBs [straffereaksjoner](https://www.ssb.no/sosiale-forhold-og-kriminalitet/kriminalitet-og-rettsvesen/statistikk/straffereaksjoner)
  er en maskintilgjengelig kandidat via samme API. Det er ikke en kilde til alle domstolers
  saksbehandlingstider. Domstolenes egen statistikk er undersøkt, men et stabilt strukturert
  uttrekk er ikke bekreftet her og oppføres derfor ikke som verifisert API-kandidat.
- **Forsvar:** SSBs [offentlige utgifter etter formål](https://www.ssb.no/341745/offentlig-forvaltnings-utgifter-etter-formal.millioner-kroner)
  tilbyr CSV/Excel, blant annet forsvarsformålet. DFØs råfiler gir en annen inngang til
  forsvarsutgifter. Dette dekker økonomi, ikke operativ kapasitet eller personellberedskap.
  Ingen generell åpen statistikk-API fra Forsvaret er bekreftet i denne gjennomgangen.

Alle disse utvalgene er kandidater. Videre arbeid prioriterer avgrensede serier
med tydelige enheter, stabile utvalg og håndterbar tilgang. Statistisk sammenligning
på tvers av kilder krever egne definisjoner og tester før den kan tilbys.
