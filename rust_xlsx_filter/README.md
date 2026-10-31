# Rust XLSX JSON Filter

**Ziel:** riesige `.xlsx`- und `.xlsm`-Dateien **nur lesen**. Ein JSON-Filter wird **einmal in Rust kompiliert** und **auf jede eingelesene Zeile in Rust** angewendet. An Python gehen ausschließlich passende Zeilen, wahlweise in Batches.

## Voraussetzungen und Installation

- Python 3.10+ (z. B. 3.13), `uv` und ein installiertes Rust-Toolchain (`cargo`, `rustc`)
- Installation aus dem entpackten Projektverzeichnis (kein vorheriges Python-Paket notwendig):

```bash
uv venv
uv pip install -e '.[test]'
```

Der `maturin`-Build-Backend kompiliert die PyO3-Erweiterung bei der Installation. Nach der Installation:

```bash
uv run --no-sync pytest -q
uv run --no-sync python benchmarks/bench.py --rows 250000
```

Ohne Rust-Toolchain ist die Erweiterung **nicht installierbar**. Das Bundle enthält Rust-Quellcode und Tests, kein vorkompiliertes Wheel.

## Maske (`filter.json`)

```json
{
  "sheet": "Daten",
  "where": {
    "all": [
      {"column": "Kunde", "op": "starts_with", "value": "ABC"},
      {"column": "Land", "op": "eq", "value": "DE"},
      {"column": "Umsatz", "op": "gte", "value": 1000},
      {"any": [
        {"column": "Status", "op": "eq", "value": "Aktiv"},
        {"column": "Status", "op": "eq", "value": "Offen"}
      ]}
    ]
  }
}
```

Das optionale `header_row` (Standard: `1`) legt die Excel-Zeile mit den Spaltenüberschriften fest. Sämtliche Bedingungen werden per Namen gegen diese Zeile aufgelöst, **bevor** der Python-Iterator zurückgegeben wird.

**Gruppen:** `all` (AND), `any` (OR), `not` (NOT). Gruppen `all`/`any` benötigen mindestens eine Regel.

**Operatoren:** `eq`, `ne`, `in`, `gt`, `gte`, `lt`, `lte`, `contains`, `starts_with`, `ends_with`, `regex`, `is_empty`, `not_empty`.

- `eq`/`ne`/`in` nehmen JSON-Skalare (`null`, Bool, Zahl oder String), `in` eine nichtleere Liste.
- Zahlenvergleiche arbeiten **nur** mit Excel-Zahlen, nicht mit Strings und nicht mit Bool.
- Textoperationen arbeiten **nur** mit Strings, standardmäßig case-sensitive. Für reguläre Ausdrücke ist `(?i)` möglich.
- `regex` nutzt den Rust-Regex-Dialekt (kein Backtracking/Lookaround/Backreferences).
- `is_empty` umfasst nicht belegte Zellen und leere Strings; `eq` mit `null` nur nicht belegte Zellen.
- Fehlende Zellen werden als Python-`None` zurückgegeben. Integer/Floats, Bool und Strings bleiben typisiert.

## Python: nur Treffer an Python übertragen

```python
from rust_xlsx_filter import iter_matching_batches

for batch in iter_matching_batches("riesig.xlsx", "filter.json", batch_size=1024):
    # Rust filtert jede gelesene Zeile; nur Treffer werden als dict konvertiert.
    for row in batch:
        process_row(row)
```

Alternativ zeilenweise konsumieren (Python iteriert dabei nur über Treffer):

```python
from rust_xlsx_filter import iter_matching_rows

for row in iter_matching_rows("riesig.xlsx", "filter.json"):
    print(row)
```

Die Maske kann außerdem als Python-`dict` oder JSON-String übergeben werden. Bei vorzeitigem Abbruch kann `batches.close()` die Rust-Verarbeitung abbrechen. `iter_matching_rows()` schließt den darunterliegenden Iterator auch bei einem Abbruch des Generators, sobald dieser geschlossen wird.

## CLI: NDJSON

```bash
uv run --no-sync rust-xlsx-filter riesig.xlsx filter.json --output treffer.ndjson
# Alternativ ohne Datei: schreibt nach stdout (bei Fehler kann stdout Teilergebnisse enthalten)
uv run --no-sync python -m rust_xlsx_filter riesig.xlsx filter.json
```

`--output` schreibt erst in eine temporäre Datei im gleichen Verzeichnis und benennt sie **nur nach vollständigem Erfolg** atomar um. Der XLSX-Eingang wird niemals verändert. Die Ergebnisdatei ist NDJSON (eine JSON-Zeile pro Treffer), kein Excel.

## Aufbau und Speicherverbrauch

1. Worker-Thread in Rust öffnet das ZIP, liest Workbook-Metadaten und die *Shared-Strings-Tabelle*.
2. Rust ermittelt das Arbeitsblatt über die OOXML-Relationships (`r:id`), liest die Kopfzeile und kompiliert JSON-Bedingungen zu Indizes und vorbereiteten Regexes.
3. `quick-xml` parst das Worksheet beim Dekomprimieren aus dem ZIP zeilenweise. Eine vollständige Worksheet-Tabelle wird **nicht** aufgebaut.
4. Nur Zeilen, für die der Rust-Ausdruck `true` ergibt, gelangen in einen begrenzten `sync_channel` (2 Nachrichten, konfigurierbare Batch-Größe). Die PyO3-Konvertierung nach Python erfolgt erst dann.
5. Beim Warten auf den Worker wird die Python-GIL freigegeben.

Peak-RAM hängt hauptsächlich von **Shared Strings + größter Zeile + 2 gepufferten Batches + Worker-Batch** ab, nicht von allen Zeilen der Excel-Datei. Die Shared-Strings-Tabelle wird vollständig eingelesen; dafür gilt aktuell ein festes Limit von **512 MiB entpacktem XML**. Metadaten sind auf 16 MiB pro Part, ein Textfeld auf 2 MiB begrenzt. `batch_size` muss im Bereich 1..65536 liegen (für großen Durchsatz 512–2048 ausprobieren).

## Bewusste Grenzen

- Unterstützt **XLSX/XLSM (OOXML)** mit UTF-8-XML und Standard-Workbook-Pfad `xl/workbook.xml`. **Kein** `.xls`, `.xlsb`, Passwortschutz oder Streaming von Legacy-Formaten.
- **Formeln werden nicht berechnet.** Zurückgegeben wird ausschließlich ihr in der Datei vorhandener Cache-Wert; ohne Cache ist die Zelle leer.
- **Datumswerte mit Excel-Zahlenformaten** werden als numerische Excel-Seriennummer ausgegeben, da keine Formatinterpretation erfolgt. ISO-Datumszellen `t="d"` erscheinen als Strings. Für Datumsmasken ist eine gezielte Erweiterung nötig.
- Keine Styles, Bilder oder gemergten Zellen. Leere/fehlende Excel-Zeilen werden nicht künstlich erzeugt.
- Wenn eine passende Datenzeile Inhalte in Spalten **ohne** Kopfzeile enthält, bricht der Reader explizit ab, statt diese Werte stillschweigend wegzulassen.
- Der Reader verarbeitet nur vorliegende Zellwerte; Excel-Formeln, externe Links und Makros werden niemals ausgeführt.
- Die Bereitstellung von Treffern ist streamingbasiert: Bei einem Fehler nach bereits gelieferten Batches ist der Python-Iterator unvollständig und löst eine Exception aus. Für atomare Ergebnisdateien `--output` verwenden.
- Spezielle OOXML-Varianten, andere XML-Kodierungen und komplexe Excel-Dateien müssen vor produktivem Einsatz getestet werden.

## Tests und Benchmark

```bash
uv run --no-sync pytest -q
uv run --no-sync python benchmarks/bench.py --rows 250000 --batch-size 1024
```

`tests/test_engine.py` erzeugt echte Excel-ZIP/XML-Dateien, verwendet bewusst keinen Excel-Writer zur Testdatenerzeugung und prüft verschachtelte AND/OR/NOT-Regeln, Regex, leere Zellen, Shared Strings, Rich Text, Formel-Cache, Bool-vs-Zahl, ungültige Masken, Batchgrenzen und Fehler nach Scanbeginn.

`benchmarks/bench.py` generiert große echte XLSX-Dateien mit konstantem Speicherverbrauch und misst nur die Einlese- und Filterphase. Performance-Aussagen sind erst nach Benchmarks auf dem Zielsystem belastbar.

### Status der bereitgestellten Version

Quellcode und Python-Testfixtures wurden erstellt; die Fixture-XLSX wurde mit `openpyxl` als unabhängigen Reader auf korrekte Daten überprüft. In der Erstellungsumgebung war **kein Rust-Compiler vorhanden** und kein Internetzugang für dessen Nachinstallation. Daher konnten `cargo test`, der `maturin`-Build und die eigentlichen Rust/Python-Integrationstests hier **nicht ausgeführt** werden. Vor produktivem Einsatz diese Schritte nachholen und mögliche Build- oder Laufzeitprobleme beheben.
