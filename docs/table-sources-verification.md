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
