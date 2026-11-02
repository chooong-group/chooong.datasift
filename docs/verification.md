# Prüfprotokoll

Aktueller Nachtrag: [Explizite Tabellenquellen](table-sources-verification.md).
Der [Zusatzspalten-Nachtrag](unnamed-columns-verification.md) ist historisch und
wurde nach der Präzisierung des Extraktionsziels durch die Quellauswahl ersetzt.
Die folgenden Abschnitte dokumentieren den initialen Package-Prüfstand. Der
damalige Push-Blocker D08 wurde durch Nutzerfreigabe und den bestehenden PR #1
aufgehoben; aktuelle offene Abnahmen stehen im Nachtrag.

Stand: 31.10.2026, Repository `chooong-group/chooong.datasift`, Branch
`feat/datasift-package`, Basis `97d4f59614c5294ab50253213a920390da44323d`.
HEAD und PR sind über Git bzw. den PR nachvollziehbar; keine selbstreferenziellen
Commit- oder Artefakt-Hashes in ausgelieferten Dateien.

## Urteil

BLOCKIERT für Push/PR: Die automatische Freigabeprüfung hat `git push` abgelehnt,
weil für die Übertragung des neuen Quellcodes und der Historie an `origin` eine
ausdrückliche Nutzerzustimmung verlangt wird. Der Branch ist ausschließlich lokal;
es wurde kein PR erstellt. Keine Umgehung oder erneuter Push-Versuch.

NICHT ENTSCHEIDBAR für eine Gesamtfreigabe: lokale Implementation und Nachweise
liegen vor; Linux-CI und unabhängiges Re-Review sind UNVERIFIED. Keine Veröffentlichung,
kein Tag, kein Merge, keine Datenbank- oder Dienständerung.

## Analyse und Entscheidungen

Das gesamte vorhandene Repository einschließlich PoC, Tests, Benchmark, Lizenz,
Gitignore, Regeln und beider Workflows wurde gelesen. Zu Arbeitsbeginn lagen
AGENTS.md, Workflows, Pre-Commit und das PoC bereits gestagt vor. Diese gelieferten
Dateien werden als Eingangsstand erhalten; nur Workflows/Pre-Commit werden gezielt
an das neue Package angepasst. Keine offenen PRs laut `gh pr list --state open`.

Das PoC bleibt unverändert als historische Referenz. Seine pyproject.toml enthält
zwei konkurrierende Build-Backends und ist keine gültige Package-Konfiguration.
Die gelieferten Workflows waren Orchestrator-Vorlagen mit nicht vorhandenen
Imports, Tests, Datenbank- und RabbitMQ-Kommandos.

Lösungsleiter: Die vorhandene native Engine deckt den Kern bereits ab. Maturin
übernimmt Packaging, Pydantic übernimmt Maskenvalidierung und Schemaerzeugung,
Dataclasses modellieren unveränderliche Zeilen. Pydantic ist die einzige neue
Python-Laufzeitabhängigkeit und wegen rekursiver strukturierter Filtereingaben
an der Vertrauensgrenze notwendig. Keine zusätzliche Service-Schicht, kein
Framework, kein Datenbankzugriff, kein neues UI. Ruff-Regeln wurden unverändert
aus der gelieferten Konfiguration übernommen; das historische PoC ist nicht Teil
der Root-Prüfpfade. Die Ausgangsversion 0.1.0 bleibt erhalten.

## Befunde

Die Korrekturen sind implementiert und lokal geprüft; die unabhängige Schließung
aller Befunde bleibt dem Re-Review vorbehalten.

| ID | Priorität | Stand | Ursache, Korrektur und Nachweis |
| --- | --- | --- | --- |
| D01 | P1 | Implementation lokal belegt | pyproject.toml:1 — Ungültiges Packaging: Root-pyproject mit genau einem Maturin-Backend, Namespace-Package, nativer abi3-Erweiterung, Stubs und py.typed; Wheel/sdist installieren und testen |
| D02 | P1 | Implementation lokal belegt | src/chooong/datasift/_models.py:93 — Unvalidierte Python-Masken und Any-API: Pydantic-Modelle, Operator-Enum, unveränderliche Row; test_contract.py plus mypy |
| D03 | P1 | Implementation lokal belegt | datasift-core/src/lib.rs:26 — Receiver war nicht Sync: Mutex schützt die native Empfängerverwaltung; Build, Clippy und Threadwechsel-Test |
| D04 | P1 | Implementation lokal belegt | datasift-core/src/xlsx.rs:25 — EOF konnte unvollständiges XML akzeptieren: gemeinsame XML-Tiefenprüfung für alle Parts; Truncation-Tests für Worksheet/Shared Strings |
| D05 | P1 | Implementation lokal belegt | src/chooong/datasift/__main__.py:38 — Ausgabe konnte Filter überschreiben: Eingabe-/Masken-Aliasprüfung, temporäre Ausgabe und Rename; echte CLI-Fehler-/Symlink-Tests |
| D06 | P1 | UNVERIFIED | .github/workflows/ci.yml:15 — Projektfremde CI ersetzt; Ausführung auf Linux-Runner und Release-Broker noch nicht nachgewiesen |
| D07 | P1 | UNVERIFIED | Unabhängiges Contract-/Datenintegritäts-Re-Review ausstehend |
| D08 | P1 | [ ] OFFEN | Push/PR durch automatische Freigabeprüfung blockiert; explizite Zustimmung zur Übertragung an origin erforderlich |

## Abdeckungsprotokoll

Alle Zeilen mit GEPRÜFT bezeichnen vollständige Dateilektüre und lokale Prüfung,
keine Behauptung über noch nicht ausgeführte CI.

| Dateien / Consumer | Abdeckung |
| --- | --- |
| AGENTS.md | GEPRÜFT, gelieferte Regeln unverändert übernommen |
| .gitignore, LICENSE | GEPRÜFT, unverändert; Apache-2.0-Metadaten im neuen Package |
| README.md, CHANGELOG.md | GEPRÜFT, Einstieg und Änderungen aktualisiert |
| docs/contract.md, docs/verification.md | GEPRÜFT, Contract, Grenzen und Evidenz |
| pyproject.toml, uv.lock | GEPRÜFT, Python-Abhängigkeiten und Qualitätsbefehle |
| datasift-core/Cargo.toml, datasift-core/Cargo.lock | GEPRÜFT, PyO3/abi3 und fixierte Rust-Abhängigkeiten |
| datasift-core/src/value.rs | GEPRÜFT, I/O-unabhängige Zellwerte |
| datasift-core/src/filter.rs | GEPRÜFT, alle Operatoren, Headerauflösung und Fehlerpfade |
| datasift-core/src/xlsx.rs | GEPRÜFT, Archiv/XML-Reader und Ressourcen-/Formatgrenzen |
| datasift-core/src/lib.rs | GEPRÜFT, Worker, Channel, GIL-Freigabe und Iterator-Lebenszyklus |
| src/chooong/datasift/__init__.py | GEPRÜFT, dokumentierte öffentliche Exporte |
| src/chooong/datasift/_models.py | GEPRÜFT, Modelle/Enums/Row |
| src/chooong/datasift/_reader.py | GEPRÜFT, direkte Engine-Aufrufer und Dateiadapter |
| src/chooong/datasift/_rust.pyi, py.typed | GEPRÜFT, native Typgrenze und Marker im Wheel |
| src/chooong/datasift/__main__.py | GEPRÜFT, direkter Consumer CLI/NDJSON |
| tests/test_engine.py | GEPRÜFT, übernommene echte OOXML-Fixtures und Kernabläufe |
| tests/test_contract.py | GEPRÜFT, alle Operatoren, Fehlereingaben, Replay und Concurrency |
| tests/test_cli.py | GEPRÜFT, tatsächlicher CLI-Produktionspfad mit Dateien |
| scripts/bench.py, examples/filter.json | GEPRÜFT, direkter Consumer Benchmark und Beispielmaske |
| .pre-commit-config.yaml | GEPRÜFT, bestehende Python-Prüfungen, Archiv ausgeschlossen |
| .github/workflows/ci.yml | GEPRÜFT, Python-3.13/3.14-Matrix, Rust und installierte Artefakte; CI UNVERIFIED |
| .github/workflows/release-gitlab-pypi.yml | GEPRÜFT, vorhandener CI-Artefakt-/Hash-/OIDC-Pfad beibehalten, Package-Tests ersetzt; Veröffentlichung UNVERIFIED |
| rust_xlsx_filter/README.md, pyproject.toml, Cargo.toml | GEPRÜFT, historische unveränderte Entwurfsgrundlage |
| rust_xlsx_filter/src/lib.rs, filter.rs, xlsx.rs | GEPRÜFT, Ausgangsengine; neuer produktiver Code unter datasift-core/ |
| rust_xlsx_filter/python/rust_xlsx_filter/__init__.py, __main__.py | GEPRÜFT, alte API/CLI; kein zugesicherter Consumer-Contract |
| rust_xlsx_filter/filter_excel.py, filter.json | GEPRÜFT, historischer Wrapper und Beispiel |
| rust_xlsx_filter/tests/test_engine.py, benchmarks/bench.py | GEPRÜFT, Grundlage der übernommenen Nachweise |
| Externe Consumer | Im Repository keine nachgewiesen; keine Cross-Repo-Änderungen oder Integrationszusagen |

## Lokale Verifikation

Plattform: macOS ARM64, CPython 3.13.15 und 3.14.6, Rust/Cargo 1.95.0.
Die folgende Tabelle protokolliert die erfolgreichen abschließenden Prüfbefehle;
frühere Entwicklungsfehler wurden korrigiert und die betroffenen Gates wiederholt.
Python-Coverage gilt ausschließlich für Python, nicht für die Rust-Engine.

| Befehl | Ergebnis / Exit-Code |
| --- | --- |
| uv lock --check; uv sync --frozen | Lock gültig, native editable Installation; 0 |
| .venv/bin/ruff check src tests scripts | All checks passed; 0 |
| .venv/bin/ruff format --check src tests scripts | 9 Dateien formatiert; 0 |
| .venv/bin/mypy src | 5 Quelldateien ohne Fehler; 0 |
| .venv/bin/pytest --cov --cov-report=term-missing | 60 passed, 99.47 % Python-Coverage; 0 |
| cargo fmt --manifest-path datasift-core/Cargo.toml -- --check | erfolgreich; 0 |
| cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings | erfolgreich; 0 |
| cargo test --manifest-path datasift-core/Cargo.toml --locked | 6 passed; 0 |
| uv build | Wheel und sdist, Wheel aus sdist gebaut; 0 |
| .venv/bin/twine check dist/* | Wheel und sdist PASSED; 0 |
| Isoliertes Wheel, Python 3.13, pytest -o addopts= tests | 60 passed; 0 |
| Isoliertes sdist, Python 3.13, pytest -o addopts= tests | 60 passed; 0 |
| Isoliertes Wheel, Python 3.14, pytest -o addopts= tests | 60 passed; 0 |
| Installiertes chooong-datasift --help, python -m chooong.datasift --help | erfolgreich; 0 |
| .venv/bin/python scripts/bench.py --rows 250000 --batch-size 1024 | 12500 Treffer, ca. 0.225 s; 0; keine allgemeine Performance-Zusage |
| YAML laden und eingebettete Python-Skripte kompilieren | erfolgreich; 0; kein Ersatz für Actionlint/CI |
| git diff --check | erfolgreich; 0 |

Artefaktprüfung erfolgt ohne PYTHONPATH und ohne editable Installation in drei
separaten /tmp-Umgebungen. Paket-Inventar enthält native Erweiterung, Stubs,
py.typed und Lizenz, im sdist außerdem Cargo.lock und uv.lock; kein PoC und keine
Bytecode-Caches. Kein Zugriff auf externe APIs, bestehende Dienste oder Datenbanken.

## Einzeln abnehmbare TODOs

### D06 — Linux-CI

- Basis: 97d4f59614c5294ab50253213a920390da44323d; auf dem finalen PR-HEAD prüfen.
- Soll: vollständige CI auf dem vorhandenen Linux-x64-Runner besteht, ohne
  Orchestrator-, PostgreSQL- oder RabbitMQ-Abhängigkeiten.
- Dateien: beide .github/workflows/*.yml, pyproject.toml, datasift-core/Cargo.toml.
- Schritte: Nutzer prüft den automatisch gestarteten PR-Lauf; Actionlint auf
  beiden Workflows ausführen. Kein manuelles Starten oder Polling durch den Agenten.
- Negativ-/Replay-Belege: bestehende 60 Tests, einschließlich Fehlermasken,
  Truncation, atomarer Fehlerausgabe, Concurrency und unabhängiger Wiederholung.
- Befehle: alle quality/package-Kommandos aus ci.yml; Actionlint, falls verfügbar.
- Kriterium: beide Python-Versionen sowie Wheel-/sdist-Tests grün, keine ausgelassenen Jobs.
- Abhängigkeit: vorhandener Runner mit uv, Rust/Cargo, C-Linker und Netzwerkzugriff.
- Consumer-Auswirkung: Linux-Installierbarkeit; kein Registry-Release beauftragt.

### D07 — Unabhängiges Re-Review

- Basis: 97d4f59614c5294ab50253213a920390da44323d; vollständiger finaler PR-Diff.
- Soll: Contract, Ressourcengrenzen, Lifecycle, Fehlerpfade und Datenintegrität
  anhand Code und Tests unabhängig beurteilt; keine Eigenmeldung als Schließung.
- Dateien: alle im Abdeckungsprotokoll genannten produktiven Dateien und Tests.
- Schritte: Diff vollständig lesen, dynamische Headerauflösung, typbewusste
  Vergleiche, Worker-Abbruch, XML-Fehler und atomare Ausgabe nachvollziehen.
- Negativ-/Replay-Tests: test_contract.py, test_cli.py und Rust-Unit-Tests ausführen.
- Befehle: README-Qualitätsbefehle und isolierte Artefaktprüfungen wiederholen.
- Kriterium: keine offenen P1/P2-Befunde, belegte D01–D05-Schließung durch Reviewer.
- Abhängigkeit: unabhängiger Reviewer; Consumer sind CLI, Benchmark und Python-API.

### D08 — Zustimmung für Push und PR

- Basis: 97d4f59614c5294ab50253213a920390da44323d; finalen lokalen HEAD verwenden.
- Soll: genau diesen Feature-Branch an das konfigurierte Repository
  `chooong-group/chooong.datasift` übertragen und genau einen PR nach main erstellen.
- Dateien: vollständiger geprüfter Branch-Diff; keine zusätzlichen Änderungen.
- Schritte: ausdrückliche Nutzerzustimmung einholen; danach `git push --set-upstream
  origin feat/datasift-package`, dann `gh pr create --base main --head
  feat/datasift-package --body-file <geprüfte PR-Beschreibung>`.
- Negativ-/Replay-Prüfung: ohne Zustimmung kein erneuter Übertragungsversuch;
  nach Zustimmung vorhandene PRs prüfen, keinen doppelten PR erstellen.
- Verifikation: `git status --short`, lokaler HEAD und PR-HEAD stimmen überein;
  Diff gegen Basis unverändert, genau eine PR-URL vorhanden. CI nicht pollen.
- Kriterium: Push und PR erfolgreich; danach stoppen, kein Merge/Tag/Release.
- Abhängigkeit: explizite Freigabe der durch Auto-Review beanstandeten Datenweitergabe.
- Consumer-Auswirkung: Review-Zugriff auf Code; keine Änderung von Laufzeit-Consumern.
