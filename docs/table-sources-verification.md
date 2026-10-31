# Explizite Tabellenquellen — Prüfprotokoll

## Prüfstand und Urteil

31.10.2026, `chooong.datasift`, Branch `feat/datasift-package`, Basis
`beb1b834628dfc351ba4b7884ccfaf679ef4e5bb`, bestehender PR #1. Der genaue finale
Diff ergibt sich aus dieser Basis gegen den lokalen HEAD bzw. Arbeitsstand.
Benutzerdatei und NDJSON bleiben unversioniert und sind keine Package-Inhalte.

NICHT ENTSCHEIDBAR für eine Gesamtfreigabe: lokale Implementation und Nachweise
liegen vor; unabhängiges Review, Remote-CI und Übertragung dieses Deltas sind
UNVERIFIED. Der bisherige Push-Versuch wurde nicht ausgeführt, weil die automatische
Freigabeprüfung mangels Workspace-Credits nicht abgeschlossen werden konnte.
Keine Änderung an Version, Abhängigkeiten, Ruff-Regeln, Diensten oder anderen Repos.

## Befund T01 — P1, unabhängige Schließung offen

Der frühere Ansatz betrachtete die gesamte Headerzeile als Schema und fügte sogar
unbenannte Zusatzdaten hinzu. Damit wurden benachbarte Tabellen, mehrzeilige Header
und Kommentare nicht korrekt als Extraktionsgrenze modelliert.

Lösungsleiter: Zellbereiche können mit vorhandener Streaming-Engine gelesen werden;
benötigt wird eine explizite Quellauswahl, keine zusätzliche Tabellen-Heuristik oder
zweite Excel-Bibliothek. `TableSource` bindet eindeutige Ausgabe-/Filternamen über
`ColumnBinding` an absolute Spalten. Zeilenbeginn, optionales Ende und `skip_rows`
bestimmen die Datensätze. Headertexte werden in diesem Modus nicht interpretiert.
Die `__column_*`-Funktion wurde entfernt, kein automatisches Mitnehmen fremder Werte.

Invariante: `source` begrenzt die Eingabe und Ausgabe, `where` prüft nur ihre
gebundenen Werte. Andere Tabellen/Kommentarzeilen dürfen keinen Treffer ergänzen
oder Werte überschreiben. Unterschiede in Batchgröße, Wiederholung oder Headertext
verändern das Ergebnis nicht. Fehler innerhalb der Quelle sowie beschädigtes
XML bleiben Fehler; atomare NDJSON-Ausgabe bleibt erhalten.

Kommentare werden nicht geraten: Vor dem Datenbeginn sind sie ausgeschlossen;
innerhalb des Datenbereichs legt die Maske `skip_rows` oder Filterbedingungen fest.
Mehrere Tabellen werden mit getrennten Masken verarbeitet. Automatische Erkennung
oder Rekonstruktion verbundener/mehrzeiliger Header ist nicht implementiert.

## Abdeckung

| Dateien / Consumer | Stand |
| --- | --- |
| src/chooong/datasift/_models.py | GEPRÜFT, kanonische Pydantic-Modelle und Bereichs-/Aliasvalidierung |
| src/chooong/datasift/__init__.py | GEPRÜFT, öffentliche Exporte TableSource/ColumnBinding |
| native/src/filter.rs | GEPRÜFT, Source-Contract, Positionsauflösung, unveränderte Filteroperatoren |
| native/src/xlsx.rs | GEPRÜFT, Streaming-Selektion vor Zellwert-Konvertierung, gesamte XML-Struktur weiterhin validiert |
| native/src/lib.rs | GEPRÜFT, Ausgabe nur gebundener Felder, Lebenszyklus unverändert |
| native/src/value.rs, src/chooong/datasift/_reader.py, __main__.py | GEPRÜFT, direkte Consumer/Zelltypen unverändert |
| tests/test_sources.py | GEPRÜFT, echte OOXML-Tabellenlayouts und Fehlerpfade, keine internen Mocks |
| tests/test_contract.py | GEPRÜFT, Korrektur der früheren Zusatzfeld-Erwartung |
| tests/test_engine.py, test_cli.py | GEPRÜFT, bestehende Filter-, Atomicity- und Lifecycle-Pfade |
| examples/filter.json, examples/layout-filter.json | GEPRÜFT, tatsächliche Benutzerdatei bzw. synthetischer Layout-Test |
| README.md, docs/contract.md, CHANGELOG.md | GEPRÜFT, Quellmodell, Grenzen und Contract-Korrektur dokumentiert |
| docs/verification.md, unnamed-columns-verification.md | GEPRÜFT, alte Prüfstände als historisch markiert |
| pyproject.toml, native/Cargo.toml, Lockfiles, beide Workflows, Pre-Commit | GEPRÜFT, unverändert |
| scripts/bench.py | GEPRÜFT, direkter Consumer des unveränderten einfachen Header-Modus |
| Externe Consumer | Keine Cross-Repo-Änderung oder Integrationszusage |

## Lokale Nachweise

Erfolgreiche abschließende Befehle (Exit 0):

- `.venv/bin/ruff check src tests scripts`, `.venv/bin/ruff format --check src tests scripts`.
- `.venv/bin/mypy src`: 5 Quelldateien ohne Fehler.
- `.venv/bin/pytest --cov --cov-report=term-missing`: 88 bestanden,
  99,55 % Python-Coverage; keine Behauptung einer Rust-Coverage.
- `cargo fmt --manifest-path native/Cargo.toml -- --check`.
- `cargo clippy --manifest-path native/Cargo.toml --locked --offline --all-targets -- -D warnings`.
- `cargo test --manifest-path native/Cargo.toml --locked --offline`: 6 bestanden.
- Deklarierter Maturin-Backend, lokal vorhandene Version 1.16.0:
  `maturin build --release --offline --locked -i .venv/bin/python --out dist`
  und `maturin sdist --out dist`; `.venv/bin/twine check dist/*`.
- Isolierte Wheel-Installation unter Python 3.13 und 3.14: jeweils 88 Tests bestanden.
- Echte lokale CLI mit `daten.xlsx` und `examples/filter.json`: 121 Treffer,
  exakt die vier ausgewählten Felder, ursprünglicher Eingabe-Hash unverändert.
- `git diff --check`.

Der diagnostische direkte Cargo-Extension-Build ohne Maturin scheiterte unter
macOS an fehlenden dynamischen Python-Linker-Flags. Der unterstützte Maturin-Build
setzt diese Flags und besteht. Es wurden keine Build- oder Validierungsregeln
aufgeweicht. Die lokale native Erweiterung wurde aus diesem Wheel aktualisiert.

## TODO T01 — unabhängiges Review und Remote-Nachweis

- Basis: `beb1b834628dfc351ba4b7884ccfaf679ef4e5bb`; vollständiges lokales Delta.
- Soll: Quellauswahl und Projektion ohne Übernahme fremder Tabellen, unveränderte
  Filtersemantik und sichere Fehlerbehandlung unabhängig bestätigen.
- Dateien: geänderte Modelle, drei Rust-Dateien, beide Testdateien und Contract.
- Schritte: Delta vollständig lesen, Quellen-Beispiele und README-Prüfungen wiederholen;
  nach wieder verfügbarer Freigabeprüfung Änderungen in den bestehenden PR übertragen.
- Negativ-/Replay-Tests: Bereichsfehler, Alias-Kollisionen, unbekannte Aliase,
  beschädigte ausgewählte Zellen, beschädigtes XML hinter dem Bereich,
  atomare Ausgabe, Batchgrößen 1/2/1024 und Wiederholung.
- Kriterien: unabhängiger Review ohne offene Datenintegritätsbefunde und grüner
  regulärer CI-Lauf am endgültigen PR-HEAD. CI nicht manuell starten/pollen.
- Abhängigkeiten: Reviewer, Workspace-Freigabeprüfung, bereitgestellte Runner-Toolchain.
- Consumer-Auswirkung: optionale neue `source`-Maske und explizite Ausgabeprojektion;
  keine automatisch erzeugten Zusatzfelder mehr. Kein Versions-/Releaseauftrag.

## Nachtrag H01 — automatische Header-Indizes

Basis `f30f8cd9b60af58145fdaa0123194088e9d350bb`, 31.10.2026. Der Nutzer hat
präzisiert: Wiederholte Excel-Header erhalten ab 1 Suffixe wie `Umsatz_1` und
`Umsatz_2`. Die gemeinsame Headerauflösung setzt dies vor Filterkompilierung und
Iterator-Rückgabe um, in physischer Spaltenreihenfolge und unabhängig vom Batch.
Eindeutige Namen bleiben unverändert. Namen nach Indizierung müssen eindeutig
sein; Kollisionen mit bestehenden Suffix-Namen sind ein kontrollierter Fehler.
`source.columns.name` sind explizite Aliase und bleiben von dieser Automatik getrennt.

GEPRÜFT: native/src/filter.rs (Ursache und Namensbildung), direkter Consumer
native/src/xlsx.rs (Headerauflösung), native/src/lib.rs (Ready-/Ausgabevertrag),
tests/test_contract.py, tests/test_header_indexing.py, README.md, docs/contract.md
und CHANGELOG.md. CLI, Python-Reader, Modelle und Workflows sind unverändert;
bestehende Contract-/Quellen-/Atomicity-Tests bleiben relevant und bestanden.
Keine Version, Abhängigkeit, Migration oder Ruff-Regel geändert.

Abschließende Prüfungen mit Exit-Code 0: Ruff check/format, mypy (5 Dateien),
pytest --cov (99 bestanden, 99,55 % Python-Coverage), cargo fmt, Clippy mit
`-D warnings`, cargo test (7 bestanden), Maturin-Wheel/sdist und Twine. Das isolierte
Wheel besteht je 99 Tests unter Python 3.13 und 3.14. Regressionen prüfen zwei/drei
Wiederholungen, Indizes bis 12, leere Spalten, verschobene Kopfzeilen, typisierte
Werte, verschiedene Batchgrößen, Replay, CLI-Schlüssel, nichttextuelle Header und
Suffix-Kollisionen vor Iterator-Rückgabe. Benutzerdaten bleiben außerhalb von Git
und Package-Artefakten.

TODO H01 (P1, unabhängige Schließung offen): Reviewer prüft das Delta ab obiger
Basis, insbesondere `headers_from_row`, Kollisionsbehandlung und Filter-/Ausgabe-
Zuordnung. `tests/test_header_indexing.py`, Rust-Tests und README-Qualitätsbefehle
wiederholen; auf den finalen regulären PR-CI-Lauf prüfen, ohne ihn manuell zu
starten/pollen. Abnahme: eindeutige Zuordnung ohne Wertverlust/Überschreiben,
unveränderte eindeutige Header, alle Prüfungen erfolgreich. Abhängigkeiten:
unabhängiger Reviewer und bereitgestellte Runner-Toolchain. Consumer-Auswirkung:
vormals abgewiesene doppelte Header werden über ihre indizierten Namen auswählbar.
Gesamtfreigabe bleibt NICHT ENTSCHEIDBAR bis Review und Remote-Nachweis.

## Nachtrag S01 — alle Arbeitsblätter bei `sheet: null`

Prüfstand 31.10.2026, Repository `chooong.datasift`, Branch
`feat/datasift-package`, Basis `bc4d9f4304d1af86571e6c7b8ed3cec1abc4bcbb`,
bestehender PR #1. Exakter Diff nach Commit:
`git diff bc4d9f4...feat/datasift-package`. Elf geänderte bzw. neue Dateien.
Dieser Nachtrag ersetzt für dieses Delta die älteren Prüfstände oben.

S01, P1, unabhängige Schließung offen: `sheet` bleibt erforderlich und akzeptiert
nun JSON-null. Die bestehende Streaming-Engine verarbeitet alle Arbeitsblätter
in Workbook-Reihenfolge, mit separater Header-/Filterauflösung und ohne zusätzliche
Ausgabefelder. Kein zweiter Reader, keine neue Abhängigkeit. Namen wählen weiterhin
ein einzelnes Blatt. Ohne `source` werden fehlende Kopfzeilen und unpassende
Schemas übersprungen; mit `source` gelten die Bindungen auf jedem Blatt.
Strukturelle Fehler bleiben Fehler, auch nach ersten Treffern und in übersprungenen
Blättern. Die CLI ersetzt das Ziel erst nach erfolgreichem Gesamtscan.

GEPRÜFT, vollständig: `_models.py`, `_reader.py`, `native/src/filter.rs`,
`native/src/xlsx.rs`, `native/src/lib.rs`, `tests/test_all_sheets.py`,
`examples/filter.json`, README.md, CHANGELOG.md und docs/contract.md.
Direkte Consumer: Python-Reader und CLI sowie bestehende Contract-, Engine-,
Quellen- und Header-Tests; unveränderte Pfade durch die gesamte Testsuite geprüft.
Build-Konfiguration, Workflows und Lockfiles bleiben unverändert. Keine externen
Consumer geändert. Lokale Benutzerdateien bleiben unversioniert; der sdist wird aus
einer gezielten Quellkopie gebaut, damit unversionierte Beispiele nicht einfließen.

Lokale Nachweise (Exit 0): Ruff check/format, mypy (5 Dateien), cargo fmt,
Clippy `--locked --offline --all-targets -- -D warnings`, cargo test (8 bestanden),
pytest --cov (112 bestanden, 99,55 % Python-Coverage), Maturin-Wheel/sdist,
Twine und `git diff --check`. Isolierte Wheel-Prüfungen: jeweils 112 Tests unter
Python 3.13 und 3.14. Die Tests prüfen Blattreihenfolge trotz anders geordneter
Relationships, ausgeblendete Blätter, Diagrammseiten, unterschiedliche Spalten,
fehlende Kopfzeilen, explizite Quellen, leere Ergebnisse, ungültige Regexes,
Batchgrößen 1/2/1024, Replay und unveränderte Eingabe. Fehler in späteren Blättern,
extern verknüpfte Arbeitsblätter und abgeschnittenes XML werden abgewiesen;
ein bestehendes CLI-Ausgabeziel bleibt bei Fehler unverändert.

Urteil: NICHT ENTSCHEIDBAR für die Gesamtfreigabe; Implementation und lokale
Nachweise liegen vor, unabhängiges Review und Remote-CI bleiben UNVERIFIED.

TODO S01-Review: Basis wie oben. Reviewer liest den vollständigen Diff der
aufgelisteten Dateien und prüft insbesondere Metadatenreihenfolge, Ready-/Batch-
Zuordnung, fehlende Kopfzeilen und atomare Ausgabe bei spätem Fehler.
Verifikation: README-Qualitätsbefehle und `tests/test_all_sheets.py` wiederholen.
Abnahme: keine offenen Datenintegritätsbefunde, gleiche Treffer bei Replay und
allen Batchgrößen, Fehler überschreiben kein Ausgabeziel. Abhängigkeit: unabhängiger
Reviewer. Consumer-Auswirkung: optionale Suche über alle Blätter ohne Schemaänderung
der Ergebniszeilen.

TODO S01-CI: gleicher Basis-/Dateiumfang. Nach dem Push regulären CI-Lauf am
endgültigen PR-HEAD prüfen; keine manuelle Auslösung oder Polling durch den Agenten.
Abnahme: alle konfigurierten Gates erfolgreich, einschließlich bestehender
Negativ-/Replay-Tests. Abhängigkeit: Runner-Toolchain. Consumer-Auswirkung:
plattformübergreifender Build-/Contract-Nachweis bleibt bis dahin UNVERIFIED.

Der erste Commitversuch scheiterte mit Exit 128 (`agent refused operation`).
Nach Rückmeldung des Nutzers wird Commit/Push mit unveränderter SSH-Signierung
erneut ausgeführt; der endgültige Commit wird am PR-HEAD ausgewiesen.

## Nachtrag A01 — automatische Headersuche und Maskenprojektion

Prüfstand 31.10.2026, `chooong.datasift`, Branch `feat/datasift-package`,
Basis `2b9bb9822079687ab09327b86082452772326c0b`, bestehender PR #1.
Exakter Diff nach Commit: `git diff 2b9bb98...feat/datasift-package`.
Dieser Nachtrag ersetzt die Header-/Ausgabeaussagen älterer Prüfstände.

A01 (P1, unabhängige Schließung offen): Die bisherige feste Headerzeile machte
Zeilenpositionen zum Maskenwissen und erklärte fremde Kommentartexte zu Spalten.
Die vorhandene Streaming-Engine löst nun die erste Zeile mit sämtlichen
Maskenspalten als Header auf. Sie projiziert Filtereingabe und Ausgabe auf die
referenzierten Spalten, einschließlich `any`/`not`, auch bei `source`.
Lösungsleiter: vorhandene Headerauflösung und Filterreferenzen wiederverwendet,
kein zweiter Reader, keine Formatierungsheuristik und keine neue Abhängigkeit.

Invarianten: Versetzte Header und Titel davor benötigen keine Zeilenangabe;
Kommentar-/Nachbarspalten gelangen nicht in Ergebnisse. Referenzierte Spalten
bleiben eindeutig und in physischer Reihenfolge (bei `source`: Bindungsreihenfolge).
Nach Schemaerkennung werden Fremdspalten nicht konvertiert. Beschädigte gewählte
Werte und strukturell beschädigtes XML bleiben Fehler; atomare Ausgabe bleibt
auch bei späten Fehlern erhalten. Batchgröße und Replay verändern keine Werte.

Expliziter Breaking Change im Greenfield-Contract: `header_row` ist entfernt;
Masken entfernen das Feld. Unbenutzte Header/Source-Aliase erscheinen nicht mehr
in Ergebnissen. Erkennung ist auf den ersten vollständigen Header pro Blatt
begrenzt. Text mit Zeilenumbruch in einer Zelle bleibt ein exakter Name; über
mehrere physische Zeilen verteilte Header werden nicht geraten. Wiederholte
Headertexte in gewählten Spalten werden übersprungen. Für echte Daten mit exakt
diesen Texten oder abweichende Layouts bleiben explizite `source`-Bindungen.

GEPRÜFT, vollständig und geändert: `_models.py`, `native/src/filter.rs`,
`native/src/xlsx.rs`, `tests/test_auto_headers.py`, `tests/test_all_sheets.py`,
`tests/test_contract.py`, `tests/test_header_indexing.py`, `tests/test_engine.py`,
`tests/test_cli.py`, `tests/test_sources.py`, README.md, CHANGELOG.md, docs/contract.md
und dieses Protokoll. GEPRÜFT, direkte Consumer unverändert: `_reader.py`,
`__main__.py`, `native/src/lib.rs`, `native/src/value.rs`, `scripts/bench.py`.
GEPRÜFT, unverändert: Build-Konfiguration, Lockfiles, Workflows, öffentliche Exporte
und versionierte Beispiele. Keine Cross-Repo-Consumer geändert. Benutzerdateien
bleiben unversioniert und werden nicht als Fixtures oder Artefakte hochgeladen.
Die lokale Maske `examples/filter_schmutzig.json` wurde um `header_row` bereinigt;
die lokale Ausgabe wurde mit dem beauftragten CLI-Pfad neu erstellt.

Lokale Nachweise, abschließende Befehle jeweils Exit 0: Ruff check/format, mypy
(5 Dateien), cargo fmt, Clippy `--locked --offline --all-targets -- -D warnings`,
cargo test (8 bestanden), pytest --cov (120 bestanden, 99,54 % Python-Coverage),
Maturin-Wheel und sdist, Twine, `git diff --check`. Isolierte Wheel-Installation
unter Python 3.13/3.14: jeweils 120 Tests bestanden. Der sdist wird gezielt aus
versionierten Quellen plus neuem synthetischem Test gebaut; keine lokalen
Benutzerdateien enthalten. Regressionen prüfen Header ab Zeile 7, versetzte
Spalten, Zell-Zeilenumbrüche, Titel/Zahlen/Teilheader davor, Kommentare zwischen
Header und Daten, wiederholte Header, unbenutzte Kollisionen und beschädigte
Fremdwerte nach Headererkennung, Batchgrößen 1/2/1024 und Replay.
Realer CLI-Pfad: Exit 0, weiterhin 2 Treffer mit genau 3 Maskenspalten, Werte
identisch zur Projektion der vorherigen Ausgabe; Eingabe-Hash unverändert.

Urteil NICHT ENTSCHEIDBAR für Gesamtfreigabe: lokale Umsetzung nachgewiesen,
unabhängiges Review und Remote-CI UNVERIFIED.

TODO A01-Review: Basis wie oben, vollständigen Diff der aufgelisteten Dateien
unabhängig lesen. Soll: automatische eindeutige Schemaauflösung ohne Ausgabe
fremder Spalten. `tests/test_auto_headers.py`, Header-/Source-/Atomicity-Tests und
README-Prüfbefehle wiederholen; Negativfälle fehlende/mehrdeutige Header,
`header_row`-Ablehnung und beschädigte gewählte Werte prüfen. Abnahme: kein
offener Datenintegritätsbefund, identische Ergebnisse bei Replay/Batchvarianten.
Abhängigkeit: unabhängiger Reviewer. Consumer-Auswirkung: dokumentierter neuer
Header-/Projektionscontract; keine Consumer-Integration zugesagt.

TODO A01-CI: gleicher Basis-/Dateiumfang. Regulären CI-Lauf am endgültigen PR-HEAD
durch Nutzer prüfen; keine manuelle Auslösung oder Polling durch den Agenten.
Abnahme: konfigurierte Lint-/Typ-/Test-/Build-Gates inklusive Negativ-/Replay-Tests
erfolgreich. Abhängigkeit: Runner-Toolchain. Consumer-Auswirkung: unterstützte
Plattformen bleiben bis zum Remote-Nachweis UNVERIFIED.

## Nachtrag L01 — Excel-Zeilenumbrüche

Prüfstand 31.10.2026, Repository `chooong.datasift`, Branch `feat/datasift-package`,
Basis `70f88e332228fe5935ab4a74c8e768914d98ebac`, bestehender PR #1.
Exakter Diff nach Commit: `git diff 70f88e3...feat/datasift-package`.

L01 (P1, unabhängige Schließung offen): Nach dem Speichern in Excel enthielten
Header in sharedStrings.xml literale CRLF statt LF. Der Reader übernahm rohe
Bytes, die Maske verwendete LF; dadurch fand die Headersuche kein vollständiges
Schema. Invariante: XML-konforme Zeilenenden verändern weder Headerzuordnung
noch Textfilterung. Korrektur an beiden XML-Einlesepfaden durch vorhandenes
Quick-XML `xml10_content()`, bevor der gemeinsame Text-Helper Inhalte anhängt.
Lösungsleiter: vorhandene Bibliotheksfunktion, keine eigene Ersetzungsheuristik
oder zusätzliche Abhängigkeit. Explizite Zeichenreferenzen werden separat
aufgelöst und behalten das referenzierte Zeichen. Kein pauschales Trimmen.

GEPRÜFT, vollständig und geändert: native/src/xlsx.rs, tests/test_xml_line_endings.py,
README.md, CHANGELOG.md, docs/contract.md und dieses Protokoll. Direkte Consumer:
Shared Strings sowie Worksheet-Text/CDATA, Headerauflösung in native/src/filter.rs
und Python-/CLI-Ausgabe; bestehende Tests bleiben relevant. Modelle, native/src/lib.rs,
Workflows, Lockfiles und Build-Konfiguration unverändert. Keine externen Consumer
geändert. Die vorhandenen lokalen Löschungen unter rust_xlsx_filter stammen vom
Nutzer und sind kein Bestandteil dieses Commits. Excel, lokale Maske und NDJSON
bleiben unversioniert; Benutzerdateien gelangen nicht in Package-Artefakte.

Lokale Nachweise, abschließende Befehle jeweils Exit 0: Ruff check/format,
mypy (5 Dateien), cargo fmt, Clippy `--locked --offline --all-targets -- -D warnings`,
cargo test (8 bestanden), pytest --cov (130 bestanden, 99,54 % Python-Coverage),
Maturin-Wheel/sdist, Twine und `git diff --check`. Wheel-Tests unter Python 3.13
und 3.14: jeweils 130 bestanden. Regressionen prüfen LF, CRLF und CR in Shared
Strings, Inline Strings und CDATA für Header und Daten; Replay und unveränderte
Eingabe werden geprüft. Negativgegenfall: explizites `&#13;` bleibt CR.
Realer beauftragter CLI-Pfad: Exit 0, vier Treffer mit drei Maskenspalten,
Eingabe-Hash unverändert und Maske unverändert. Zwei passende Blätter enthalten
je zwei Treffer; `sheet: null` dedupliziert diese bewusst nicht.

Urteil NICHT ENTSCHEIDBAR für Gesamtfreigabe: lokal nachgewiesen;
unabhängiges Review und Remote-CI UNVERIFIED.

TODO L01-Review: Basis und Dateien wie oben. Vollständigen Diff unabhängig lesen,
insbesondere Text/CDATA vor Zeichenreferenz-Auflösung; Soll: gleiche Ergebnisse
bei allen drei XML-Zeilenenden ohne Veränderung expliziter Zeichenreferenzen.
Verifikation: tests/test_xml_line_endings.py und README-Qualitätsbefehle inklusive
Negativ-/Replay-Fällen wiederholen. Abnahme: keine offenen Datenkorrektheitsbefunde.
Abhängigkeit: unabhängiger Reviewer. Consumer-Auswirkung: XML-Zeilenenden in
Headern und Textwerten entsprechen LF, Zeichenreferenzen behalten ihren Wert.

TODO L01-CI: gleicher Basis-/Dateiumfang; Nutzer prüft regulären CI-Lauf am finalen
PR-HEAD, keine manuelle Auslösung oder Polling durch den Agenten. Abnahme:
konfigurierte Tests/Typ-/Lint-/Build-Gates erfolgreich, einschließlich
Zeilenenden-/Zeichenreferenz-/Replay-Tests. Abhängigkeit: Runner-Toolchain.
Consumer-Auswirkung: weitere Plattformen bleiben bis Remote-Nachweis UNVERIFIED.

## Nachtrag N01 — Modulnamen und absolute Imports

Prüfstand 31.10.2026, `chooong.datasift`, Branch `feat/datasift-package`,
Basis `d3818a32c3724c56aa5a42c5f6b46158feb030a1`, bestehender PR #1.
Exakter Diff nach Commit: `git diff d3818a3...feat/datasift-package`.

N01 (P2, unabhängige Schließung offen): `_models.py`, `_reader.py` und `_rust.pyi`
heißen nun `models.py`, `reader.py`, `rust.pyi`. Die native Erweiterung heißt
konsistent in Maturin, Cargo und PyO3 `chooong.datasift.rust`. Vorhandene Module
wurden umbenannt, keine Kompatibilitätswrapper oder zusätzliche Abhängigkeiten.
Alle Python-Imports sind absolut. Die vom Nutzer verschärften Ruff-Regeln
(`TID252`, `ban-relative-imports = "all"`) werden unverändert übernommen und
zusammen mit der Änderung gepusht. `__init__.py` und `__main__.py` behalten ihre
Python-Standardnamen für Exporte und `python -m chooong.datasift`.

Invarianten: öffentliche Exporte und CLI bleiben unverändert; keine Änderung an
Filtersemantik, Maskenformat oder Ausgabe. Das Wheel enthält nur die neuen
Implementierungsnamen und den passenden nativen Initialisierer, keinen alten
`_rust`-Stub oder Binärcode. Frühere Implementierungsimporte waren kein
zugesicherter Contract und erhalten keine Weiterleitungen.

GEPRÜFT, vollständig und geändert: `src/chooong/datasift/models.py`, `reader.py`,
`rust.pyi`, `__init__.py`, `__main__.py`, `native/src/lib.rs`, `native/Cargo.toml`,
`pyproject.toml`, README.md, CHANGELOG.md, docs/contract.md und dieses Protokoll.
GEPRÜFT, direkte Consumer: sämtliche bestehenden Python-Tests, `scripts/bench.py`
und CLI-Entry-Point; keine Umstellung außerhalb der Package-Verdrahtung nötig.
GEPRÜFT, unverändert: Lockfiles, Workflows und Pre-Commit-Konfiguration.
Vorhandene Nutzerlöschungen unter `rust_xlsx_filter` bleiben ungestagt; lokale
Excel-Dateien und Masken bleiben unversioniert. Keine Cross-Repo-Änderung.

Lokale Nachweise, abschließende Befehle jeweils Exit 0: Ruff check/format mit den
neuen Nutzerregeln, mypy (5 Dateien), pytest --cov (130 bestanden, 99,54 %
Python-Coverage), cargo fmt, Clippy `--locked --offline --all-targets -- -D warnings`,
cargo test (8 bestanden), Maturin-Wheel und sdist, Twine und `git diff --check`.
Isolierte Wheel-Tests unter Python 3.13/3.14: jeweils 130 bestanden. Artefaktinventar
prüft neue Modul-/Stub-Namen und Abwesenheit alter Namen sowie lokaler Benutzerdaten.
Native Modulzuordnung und CLI-Start werden gegen das installierte Wheel geprüft.
Der sdist wird aus gezielt kopierten versionierten Quellen einschließlich der
umbenannten Module gebaut; keine unversionierten Benutzerbeispiele enthalten.

Urteil NICHT ENTSCHEIDBAR für Gesamtfreigabe: lokal nachgewiesen;
unabhängiges Review und Remote-CI UNVERIFIED.

TODO N01-Review: Basis/Dateien wie oben. Vollständigen Diff einschließlich
Nutzer-Ruff-Regeln, Package-Exporte, Maturin-/Cargo-/PyO3-Namen unabhängig prüfen.
Soll: keine alten Implementierungsdateien im Artefakt, keine relativen Imports,
unveränderte öffentliche Import-/CLI-Pfade. README-Prüfbefehle, installierte
Wheel-Tests mit bestehenden Negativ-/Replay-Fällen und CLI-Start wiederholen.
Abnahme: keine offenen Import-/Build-/Contract-Befunde. Abhängigkeit: unabhängiger
Reviewer. Consumer-Auswirkung: öffentliche Exporte bleiben stabil; direkte
Implementierungsimporte sind unverändert keine zugesicherte API.

TODO N01-CI: gleicher Basis-/Dateiumfang; Nutzer prüft regulären CI-Lauf am finalen
PR-HEAD, keine manuelle Auslösung oder Polling durch den Agenten. Abnahme:
konfigurierte Python-/Rust-/Artefakt-Gates einschließlich strikter Importregel
und bestehender Negativ-/Replay-Tests erfolgreich. Abhängigkeit: Runner-Toolchain.
Consumer-Auswirkung: andere Plattformen bleiben bis Remote-Nachweis UNVERIFIED.

## Nachtrag P01 — restliche Nutzeränderungen

Prüfstand 31.10.2026, `chooong.datasift`, Branch `feat/datasift-package`,
Basis `a847719fa05cab14215bf30217de64075f711339`, bestehender PR #1.
Exakter Diff nach Commit: `git diff a847719...feat/datasift-package`.
Dieser Nachtrag ersetzt ältere Aussagen über einen vorhandenen PoC im Checkout.

P01 (P2, unabhängige Schließung offen): Beauftragte Nutzeränderungen übernommen:
`.data/` wird ignoriert, `examples/filter_schmutzig.json` wird als Beispielmaske
versioniert und der historische Ordner `rust_xlsx_filter/` entfernt. Seine
bisherigen Python-/Rust-Dateien, Manifeste, README, Beispiel und Benchmark sind
keine Consumer des aktuellen Package-Builds. Die Git-Historie bleibt erhalten.
README und Contract beschreiben den aktuellen Stand, der obsolete Pre-Commit-
Ausschluss des entfernten Ordners entfällt. Kein Runtime-Code, Filterformat,
öffentlicher Import oder CLI-Pfad geändert; keine neue Abhängigkeit oder Version.

GEPRÜFT: .gitignore, neue Beispielmaske, alle zwölf gezielt entfernten PoC-Dateien
und ihr Ausschluss aus dem aktuellen Build, .pre-commit-config.yaml, README.md,
CHANGELOG.md, docs/contract.md und dieses Protokoll. Aktuelle Python-/Rust-Quellen,
pyproject.toml, Workflows, Lockfiles und direkte Consumer unverändert. Historische
Prüfprotokolle bleiben als historische Prüfstände erhalten. Keine Excel-/NDJSON-
Dateien und keine lokalen `.data/`-Inhalte werden versioniert oder verpackt.

Lokale Nachweise, abschließende Befehle jeweils Exit 0: Ruff check/format, mypy
(5 Dateien), pytest --cov (130 bestanden, 99,54 % Python-Coverage),
`pre-commit validate-config`, Pydantic-Validierung aller drei Beispielmasken,
Maturin-Wheel/sdist, Twine und `git diff --check`. Artefaktinventar bestätigt:
neue Beispielmaske im sdist, kein PoC und keine lokalen Beispieldaten.

Urteil NICHT ENTSCHEIDBAR für Gesamtfreigabe: lokale Checks liegen vor,
unabhängiges Review und Remote-CI UNVERIFIED.

TODO P01-Review: Basis und Dateien wie oben. Reviewer prüft vollständigen Diff,
insbesondere auf unbeabsichtigte Löschungen außerhalb des historischen PoC,
Beispielmasken-Validität, Ignore-Regel und aktuelle Doku. Soll: aktuelles Package
und öffentliche Pfade bleiben unverändert; keine privaten Beispieldaten im Commit
oder Artefakt. Bestehende Contract-/Negativ-/Replay-Tests sowie README-Prüfbefehle
wiederholen. Abnahme: keine offenen Daten-/Build-/Contract-Befunde. Abhängigkeit:
unabhängiger Reviewer. Consumer-Auswirkung: historischer PoC entfernt, der bereits
vorher keine zugesicherte API war; aktueller Import-/Maskencontract bleibt stabil.

TODO P01-CI: gleicher Basis-/Dateiumfang; Nutzer prüft regulären CI-Lauf am finalen
PR-HEAD. Keine manuelle Auslösung oder Polling durch den Agenten. Abnahme:
konfigurierte Python-/Rust-/Artefakt-Gates einschließlich bestehender
Negativ-/Replay-Tests erfolgreich. Abhängigkeit: Runner-Toolchain.
Consumer-Auswirkung: Remote-Build bleibt bis zu diesem Nachweis UNVERIFIED.

## Nachtrag M01 — mehrere Tabellen pro Arbeitsblatt

Prüfstand 31.10.2026, `chooong.datasift`, Branch `feat/datasift-package`,
Basis `c4d8e2b2c7e6d34daa915446b4b5d3e135c66b46`, bestehender PR #1.
Exakter Diff nach Commit: `git diff c4d8e2b...feat/datasift-package`.
Dieser Nachtrag ersetzt ältere Aussagen über genau einen Header pro Blatt.

M01 (P1, unabhängige Schließung offen): Die vorherige Headersuche übersah Tabellen
neben/unter dem ersten Bereich; gleiche Namen über benachbarte Tabellen wurden
fälschlich global indiziert. Die gemeinsame Headerauflösung erkennt nun mehrere
vollständige Gruppen der wortgleichen Maskenspalten in einer Zeile. Ein einzelnes
Zeilenschema behält die bisherige Index-/Kollisionssemantik. Ein Spaltenbereich
hat einen eigenen vorbereiteten Filter und eigene Bindungen. Neue überlappende
Header ersetzen den alten Bereich; unabhängige Nachbartabellen laufen weiter.
Lösungsleiter: vorhandenen Streaming-Reader und Header-/Filtercompiler erweitern,
kein zweiter Parser, keine zusätzliche Abhängigkeit oder künstliche API.

Invarianten: keine Vermischung von Werten benachbarter Tabellen, kein doppeltes
Auswerten ersetzter Bereiche, Reihenfolge Workbook/Zeile/linke Spalte. Nach außen
nur Maskenspalten und keine Tabellenmetadaten. Vor einem Wechsel der Ausgabespalten-
reihenfolge wird der bestehende Batch geleert; projizierte Werte entsprechen dem
jeweiligen Ready-Schema. Beschädigte gewählte Werte und XML bleiben Fehler;
bei spätem Fehler bleibt das CLI-Ziel unverändert. Explizite `source`-Grenzen,
Batchgrößen und Replay bleiben stabil. Aktive Bereiche überlappen sich nicht.

Die dokumentierte Grenze bleibt bewusst: horizontale Aufteilung nur bei mindestens
zwei vollständigen wortgleichen Maskenschemas mit mindestens zwei unterschiedlichen
Maskenspalten. Einzelne wiederholte Namen, teilweise Schemata und horizontale
Tabellen mit intern indizierten Maskennamen werden nicht geraten; dafür explizite
Quellen. Über physische Zeilen verteilte Header werden nicht rekonstruiert.
Außerhalb aktiver Spalten werden nur gültige Text-Headerkandidaten betrachtet;
ungültige unselektierte Werte werden weiterhin nicht extrahiert. Keine Änderung
am Maskenformat, keine neue Version oder Veröffentlichung.

GEPRÜFT, vollständig und geändert: native/src/filter.rs (Schemaauflösung und aus
der Maske abgeleitete Headerkandidaten), native/src/xlsx.rs (aktive Tabellen,
Zellselektion, Projektion, Batchgrenzen), tests/test_multiple_tables.py, README.md,
CHANGELOG.md, docs/contract.md und dieses Protokoll. GEPRÜFT, direkte Consumer
unverändert: native/src/lib.rs (Ready/Batch), Python-Reader, CLI und Benchmark;
bestehende Contract-/Header-/Quellen-/Zeilenenden-Tests bleiben relevant.
Modelle, Workflows und Lockfiles bleiben unverändert. Die gleichzeitig vom Nutzer
geänderte Kommentarübersetzung in pyproject.toml bleibt ungestagt; keine Ruff-Regel
wurde verändert. Benutzerdateien und `treffer.ndjson` bleiben unversioniert.

Lokale Nachweise, abschließende Befehle jeweils Exit 0: Ruff check/format,
mypy (5 Dateien), cargo fmt, Clippy `--locked --offline --all-targets -- -D warnings`,
cargo test (8 bestanden), pytest --cov (147 bestanden, 99,54 % Python-Coverage),
Maturin-Wheel/sdist, Twine, `git diff --check`. Isolierte Wheel-Prüfungen unter
Python 3.13 und 3.14: jeweils 147 bestanden. Artefakte enthalten keine lokalen
Excel-/NDJSON-Dateien oder `.data/`-Inhalte. Synthetische Regressionen prüfen fünf
Tabellen auf zwei Blättern, identische/anders geordnete Spalten, horizontale,
vertikale und versetzte Header, Header neben Daten, Shared-String-Header außerhalb
bisheriger Bindungen, unabhängige Filterbedingungen, späte beschädigte Werte,
Batchgrößen 1/2/3/1024 und Replay. Bestehende Indizes und Kollisionen bleiben geprüft.
Der bestehende Benchmark liest 250000 Zeilen und liefert korrekt 12500 Treffer;
keine plattformübergreifende Performance-/RAM-Zusage aus diesem lokalen Lauf.

Realer beauftragter CLI-Pfad: Exit 0, zehn Einträge mit genau drei Maskenspalten,
Excel-Hash und Maske unverändert. Die Ergebnisse entsprechen als Multimenge exakt
fünf separaten Scans mit expliziten Spalten-/Zeilengrenzen: vier Tabellen mit je
zwei Treffern auf einem Blatt und eine Tabelle mit zwei Treffern auf einem zweiten
Blatt. Kein pauschaler Sollzähler und keine duplizierten Ergebniseinträge im Code.

Urteil NICHT ENTSCHEIDBAR für Gesamtfreigabe: lokal nachgewiesen;
unabhängiges Review und Remote-CI UNVERIFIED.

TODO M01-Review: Basis/Dateien wie oben. Vollständigen Diff unabhängig prüfen,
insbesondere Aufteilung vollständiger Schemata, Überlappungsregel, kompakte
Projektion und Ready-/Batch-Reihenfolge. README-Prüfbefehle und
`tests/test_multiple_tables.py` einschließlich Negativ-/Replay-/Atomicity-Fällen
wiederholen. Soll: alle zehn synthetischen Treffer ohne Vermischung oder zusätzliche
Treffer, unveränderte explizite Quellen und Indexsemantik. Abnahme: keine offenen
Datenkorrektheits-/Lifecycle-Befunde. Abhängigkeit: unabhängiger Reviewer.
Consumer-Auswirkung: weitere passende Tabellen liefern zusätzliche Datensätze;
Maskenformat und öffentliche Import-/CLI-Pfade bleiben unverändert.

TODO M01-CI: gleicher Basis-/Dateiumfang; Nutzer prüft regulären CI-Lauf am finalen
PR-HEAD. Keine manuelle Auslösung oder Polling durch den Agenten. Abnahme:
konfigurierte Python-/Rust-/Artefakt-Gates einschließlich bestehender und neuer
Negativ-/Replay-Tests erfolgreich. Abhängigkeit: Runner-Toolchain.
Consumer-Auswirkung: andere Plattformen bleiben bis Remote-Nachweis UNVERIFIED.
