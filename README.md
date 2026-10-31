# chooong.datasift

Filtert große XLSX-/XLSM-Dateien zeilenweise mit einer JSON-Maske. Rust liest und
prüft jede Zeile; Python erhält ausschließlich Treffer. Das Package berechnet
keine Formeln und schreibt keine Excel-Dateien.

Greenfield, Version 0.1.0. Unterstützt CPython 3.13/3.14. Für einen Build aus
Quellcode werden Rust/Cargo und ein C-Linker benötigt; installierte kompatible
Wheels benötigen kein Rust. Keine externen Dienste.

## Installation und Benutzung

Aus diesem Repository (noch keine Registry-Veröffentlichung):

```bash
uv pip install .
```

```python
from chooong.datasift import (
    ColumnBinding, FilterMask, Operator, ScalarCondition, TableSource, iter_matching_batches,
)

mask = FilterMask(
    sheet="Daten",
    source=TableSource(
        columns=(ColumnBinding(name="Land", column="B"),),
        data_start_row=2,
    ),
    where=ScalarCondition(column="Land", op=Operator.EQ, value="DE"),
)
with iter_matching_batches("daten.xlsx", mask, batch_size=1024) as batches:
    for batch in batches:
        for row in batch:
            print(row["Land"])
```

```bash
chooong-datasift daten.xlsx examples/filter.json --output treffer.ndjson
python -m chooong.datasift daten.xlsx examples/filter.json
```

`--output` ersetzt die Zieldatei erst nach vollständigem Erfolg atomar. Ohne
`--output` kann stdout bei Fehlern Teilergebnisse enthalten. Die Eingabedateien
bleiben erhalten. `iter_matching_rows` liefert einzelne Treffer; bei vorzeitigem
Abbruch den Generator schließen oder den Batch-Kontextmanager verwenden.

## Contract und Architektur

Öffentliche API: `chooong.datasift` exportiert Filtermodelle, `Operator`, `Row`,
`BatchIterator`, `iter_matching_batches` und `iter_matching_rows`. Masken können
als `FilterMask`, Mapping, JSON-Text oder Dateipfad übergeben werden. Ergebniszeilen
sind unveränderliche `Row`-Mappings mit dynamischen Excel-Spaltennamen.
`source` ordnet Ausgabenamen tatsächlichen Excel-Spalten zu und begrenzt die
Datenzeilen. Damit lassen sich Tabellen nebeneinander, beliebige Startpositionen,
mehrzeilige oder doppelte Header und Kommentarzeilen explizit behandeln. Nur die
zugeordneten Felder passender Zeilen werden ausgegeben. Beispiel für eine Tabelle
ab C7: [examples/layout-filter.json](examples/layout-filter.json). Ohne `source`
bleibt die einfache Auswahl über eine einzelne `header_row` möglich.
Wiederholte Header heißen dabei von links nach rechts etwa `Umsatz_1` und
`Umsatz_2`; diese Namen werden zum Filtern und in der Ausgabe verwendet.

[Filtervertrag und Grenzen](docs/contract.md) beschreiben Operatoren, Typen,
Fehler und Ressourcenlimits. Es gibt keine Umgebungsvariablen oder Diensteinstellungen.
Pydantic validiert die Eingabe; der Python-Dateiadapter reicht die Maske an die
Rust-Engine weiter. Rust trennt Filterlogik und Zellwerte von XLSX-I/O und PyO3.
Eine zusätzliche Service-/Port-Schicht wäre hier ohne eigenen Use Case redundant.

## Entwicklung

```bash
uv sync --frozen
uv run --frozen ruff check src tests scripts
uv run --frozen ruff format --check src tests scripts
uv run --frozen mypy src
uv run --frozen pytest --cov --cov-report=term-missing
cargo fmt --manifest-path native/Cargo.toml -- --check
cargo clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path native/Cargo.toml --locked
uv build
uv run --frozen twine check dist/*
uv run --frozen python scripts/bench.py --rows 250000
```

`uv.lock` und `native/Cargo.lock` fixieren die Entwicklungsabhängigkeiten. Der
ursprüngliche, unveränderte Entwurf liegt unter `rust_xlsx_filter/`; er gehört
nicht zum Package, Build oder unterstützten API. Die Root-Konfiguration ist verbindlich.

[Changelog](CHANGELOG.md) · [Prüfprotokoll](docs/verification.md) ·
[Apache-2.0-Lizenz](LICENSE)
