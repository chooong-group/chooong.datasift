# XLSX-Zusatzspalten ohne Überschrift

## Prüfstand und Urteil

31.10.2026, Repository `chooong.datasift`, Branch `feat/datasift-package`,
Bugfix-Basis `456b3694804ce07f31e7c91a958559e65dbb7a8e`, bestehender PR #1.
Der finale HEAD ist über Git nachvollziehbar. Die Benutzerdatei und das erzeugte
NDJSON sind ausschließlich lokale Daten, keine Fixtures oder Package-Inhalte.

NICHT ENTSCHEIDBAR für eine Gesamtfreigabe: Implementation und lokale Integration
sind belegt; Remote-CI und unabhängiges Re-Review dieses Deltas bleiben UNVERIFIED.
Keine Version geändert, keine Abhängigkeit ergänzt, kein Release oder Deployment.

## Befund U01 — P1, unabhängige Schließung OFFEN

Die Benutzerdatei besitzt vier Überschriften und 2000 Datenzeilen mit einzelnen
Zusatzwerten in M, U und V. `Sink::on_row` brach beim ersten passenden Datensatz
mit solchem Zusatzwert ab. Die CLI meldete deshalb nur `RuntimeError`.

Korrektur: Der Worker liefert weiterhin ausschließlich Treffer. Der PyO3-Adapter
überträgt benannte Felder und zusätzliche belegte Zellen unter positionsabhängigen
Schlüsseln wie `__column_M`. `unnamed_column_name` löst Kollisionen durch angehängte
Unterstriche, ohne echte Überschriften zu überschreiben. Keine Tabellen-Vorablesung,
kein Verwerfen von Zusatzwerten. Filter lösen weiterhin nur echte Überschriften auf.
`None` ohne Überschrift erzeugt kein Feld; expliziter Leertext bleibt erhalten.

Invariante: Gleiche Eingabe und Maske liefern unabhängig von Batchgröße und
Wiederholung dieselben typisierten Werte, einschließlich Zusatzdaten. Negativfälle:
Namenskollisionen überschreiben keine Felder, unbekannte Filterspalten bleiben
Fehler, beschädigte Dateien dürfen weiterhin keine Teilausgabe veröffentlichen.

## Abdeckungsprotokoll

| Datei / direkter Consumer | Stand |
| --- | --- |
| native/src/filter.rs | GEPRÜFT, Headerauflösung und neue positionsabhängige Namensbildung |
| native/src/lib.rs | GEPRÜFT, Ready-/Batch-Verarbeitung, typisierte PyO3-Zellkonvertierung |
| native/src/xlsx.rs | GEPRÜFT, Guard entfernt, übrige XML-/Archiv-Validierung erhalten |
| native/src/value.rs | GEPRÜFT, Zelltypen unverändert |
| src/chooong/datasift/_reader.py, __main__.py, _models.py | GEPRÜFT, direkte Consumer und Row-Vertrag unverändert |
| tests/test_contract.py | GEPRÜFT, synthetische OOXML-Regressionen und echter CLI-Pfad |
| tests/test_cli.py, tests/test_engine.py | GEPRÜFT, bestehende Fehler-/Atomicity-/Filtertests unverändert |
| scripts/bench.py, examples/filter.json | GEPRÜFT, direkte Consumer unverändert |
| README.md, docs/contract.md, CHANGELOG.md | GEPRÜFT, Ausgabevertrag und Änderung dokumentiert |
| docs/verification.md | GEPRÜFT, Nachtrag und historischer Prüfstand getrennt |
| pyproject.toml, native/Cargo.toml, beide CI-Workflows, Pre-Commit | GEPRÜFT, unverändert; Ruff-Regeln unverändert |
| Externe Consumer | Keine Cross-Repo-Änderungen; keine externe Integrationszusage |

## Ausgeführte Prüfungen

Erfolgreiche abschließende Befehle mit Exit-Code 0:

- `uv sync --frozen --reinstall-package chooong.datasift`: native lokale Erweiterung neu gebaut.
- `.venv/bin/ruff check src tests scripts`; `.venv/bin/ruff format --check src tests scripts`.
- `.venv/bin/mypy src`: 5 Quelldateien ohne Fehler.
- `.venv/bin/pytest --cov --cov-report=term-missing`: 66 bestanden, 99,47 % Python-Coverage.
- `cargo fmt --manifest-path native/Cargo.toml -- --check`.
- `cargo clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings`.
- `cargo test --manifest-path native/Cargo.toml --locked`: 6 bestanden.
- `.venv/bin/chooong-datasift daten.xlsx examples/filter.json --output treffer.ndjson`:
  121 Treffer, ein Zusatzwert in passenden Zeilen erhalten, vollständiger unabhängiger
  ElementTree-Abgleich gegen die Originaldatei erfolgreich; Eingabe-Hash unverändert.
- `uv build` und `.venv/bin/twine check dist/*`: Wheel und sdist erfolgreich.
- Isolierte Installation des gebauten Wheels: 66 Tests erfolgreich und 121 Treffer
  mit der Benutzerdatei; keine editable Installation, kein PYTHONPATH.
- `git diff --check`.

Die Originaldatei wurde weder verändert noch in Tests/Artefakte aufgenommen.
Die neuen Fixtures enthalten ausschließlich synthetische Werte. Die bestehende
CLI-Fehler-Redaktion bleibt erhalten; Zellwerte werden nicht in Logs geschrieben.

## TODO U01 — unabhängiges Delta-Review

- Basis: `456b3694804ce07f31e7c91a958559e65dbb7a8e`, finalen PR-HEAD prüfen.
- Soll: Unbenannte Zusatzdaten bleiben verlustfrei, Namen eindeutig und Streaming begrenzt.
- Dateien: drei geänderte Rust-Dateien, test_contract.py und docs/contract.md.
- Schritte: vollständiges Delta lesen, Kollisionen/Spaltengrenzen nachvollziehen,
  README-Qualitätsbefehle und isolierte Wheel-Regression wiederholen.
- Negativ-/Replay-Tests: unbekannte Filterspalten, Kollisionen, leere Zusatzfelder,
  beschädigte Daten und atomare Ausgabe; Batchgrößen 1, 3 und 1024, erneuter Scan.
- Kriterien: unabhängiger Reviewer bestätigt Datenintegrität und unveränderte
  Filtersemantik; neuer regulärer CI-Lauf erfolgreich. CI nicht manuell starten/pollen.
- Abhängigkeiten: unabhängiger Reviewer und Runner mit bereitgestellter nativer Toolchain.
- Consumer-Auswirkung: vormals abgewiesene Zeilen erhalten dynamische Zusatzfelder;
  bisher gültige Zeilen und Filter bleiben unverändert.
