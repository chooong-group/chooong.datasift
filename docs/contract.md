# Öffentlicher Vertrag v1

Distribution: `chooong.datasift`, Import: `chooong.datasift`, CLI:
`chooong-datasift` bzw. `python -m chooong.datasift`. Die Initialversion bleibt
0.1.0; keine Veröffentlichung oder Consumer-Migration ist Teil dieses Auftrags.

## JSON-Maske

Format v1 ist implizit, ohne Versionsfeld. `FilterMask` ist das kanonische
Eingabemodell; `FilterMask.model_json_schema(by_alias=True)` erzeugt das Schema.
Unbekannte Felder, Operatoren und falsche Werttypen werden abgewiesen.

```json
{"sheet":"Daten","header_row":1,"where":{"column":"Land","op":"eq","value":"DE"}}
```

`sheet` ist ein nichtleerer Blattname; `header_row` ist eine ganze Zahl von 1 bis
1048576 (Standard 1). Spaltennamen entsprechen exakt der Kopfzeile, ohne Trimmen.
Leere Überschriften werden ausgelassen, doppelte oder nichttextuelle abgewiesen.
Eine passende Zeile mit Inhalten ohne Überschrift führt zum Fehler.

| Ausdruck / Operator | Wert und Bedeutung |
| --- | --- |
| `all`, `any` | Nichtleere Listen von Ausdrücken, AND bzw. OR |
| `not` | Genau ein Ausdruck, Negation |
| `eq`, `ne` | JSON-Skalar: null, bool, Zahl oder String; typbewusst |
| `in` | Nichtleere Liste von Skalaren |
| `gt`, `gte`, `lt`, `lte` | Endliche Zahl; keine String-/Bool-Konvertierung |
| `contains`, `starts_with`, `ends_with` | String, case-sensitive |
| `regex` | Rust-Regex, maximal 4096 UTF-8-Bytes; `(?i)` möglich |
| `is_empty`, `not_empty` | Kein `value`-Feld; null und leerer String sind leer |

Ein Vergleich enthält exakt `column`, `op`, `value`; Leerheitsprüfungen nur
`column`, `op`. Gruppen enthalten nur ihren jeweiligen Gruppenschlüssel.
Maximal 64 Ausdrucksebenen und 10000 Regeln je AND-/OR-Gruppe. Regexes unterstützen
keine Backreferences oder Lookarounds und werden einmal pro Scan kompiliert.

Python-Modelle: `ScalarCondition`, `MembershipCondition`, `NumericCondition`,
`TextCondition`, `EmptyCondition`, `AllOf(conditions=...)`, `AnyOf(conditions=...)`,
`Not(condition=...)`, `FilterMask`. `Operator` ist ein `StrEnum`.

## Ergebnisse und Lebenszyklus

`iter_matching_batches(path, mask, *, batch_size=1024)` liefert einen
`BatchIterator` mit `list[Row]`, `close()` und Kontextmanager-Unterstützung.
Sheet, Kopfzeile, Spalten und Regex werden vor Rückgabe geprüft.
`iter_matching_rows` liefert einen Generator und validiert beim ersten `next()`.
Ein geschlossenes oder erschöpftes Scanobjekt bleibt erschöpft. Parallele Scans
besitzen getrennte Worker; ein einzelner Iterator darf nicht gleichzeitig
von mehreren Threads konsumiert oder geschlossen werden.

`Row` ist ein unveränderliches Mapping; `row["Spalte"]` und `dict(row)` sind
unterstützt. Spaltennamen sind datenabhängig, deshalb kein statisches Spaltenschema.
Zellen enthalten `str | bool | int | float | None`; keine Pandas-Abhängigkeit.
Leere Zellen sind `None`, leere Texte bleiben `""`; `eq null` trifft nur `None`.
Excel-Fehlerzellen bleiben Fehlertext. Zahlen verwenden i64 bzw. IEEE-754 f64;
keine Decimal-/Geldarithmetik oder garantierte Genauigkeit jenseits dieser Grenzen.
Numerische Ordnungsvergleiche verwenden f64, auch für Integer. Für exakte große
IDs String-Zellen und String-Gleichheit verwenden.

Initialisierungsfehler: `ValueError` (einschließlich Pydantic `ValidationError`),
Dateifehler beim Lesen der Maske: `OSError`, ungültige UTF-8-Masken ggf.
`UnicodeError`. Laufzeitfehler nach Scanbeginn: `RuntimeError`. Bereits gelieferte
Batches werden nicht zurückgenommen. CLI: Erfolg 0, Scan-/Dateifehler 1,
Argumentfehler 2. stderr enthält keine Zellwerte. stdout liefert NDJSON.

`--output` schreibt eine separate temporäre Datei im Zielverzeichnis, flusht sie
und ersetzt das Ziel atomar. Fehler lassen das bisherige Ziel unverändert und
entfernen die temporäre Datei. Gleiches Ziel wird bei konkurrierenden erfolgreichen
Aufrufen vom zuletzt umbenennenden Prozess bestimmt. Keine dauerhafte Replay-ID:
Wiederholung liest die Datei neu. Keine Garantie gegen Stromausfall nach Rename;
bei Prozessabbruch kann eine temporäre Datei zurückbleiben. Eingabe und Maske dürfen
nicht das Ausgabeziel sein; Symlinks werden für diese Prüfung aufgelöst.

## Ressourcen und Formatgrenzen

XLSX/XLSM mit UTF-8-XML und `xl/workbook.xml`; Blattpfade werden über Relationships
aufgelöst. Keine XLS-/XLSB-Dateien, Verschlüsselung, Formelberechnung, Style- oder
Datumserkennung. Formelcache wird gelesen, ohne Cache `None`; numerische Datumswerte
bleiben Seriennummern, ISO-Datumszellen Strings. Makros und Links werden nie ausgeführt.
Fehlende Zeilen werden nicht erzeugt, Merge-Bereiche nicht expandiert.

Speicher: Shared-Strings-Tabelle, größte XML-Token/Zeile und begrenzte Batches.
Shared-Strings-XML maximal 512 MiB, Metadaten 16 MiB je Part, Zelltext 2 MiB;
XML-Tiefe maximal 128. XML-Parser puffert einzelne Tokens vor der Textlimit-Prüfung:
die Zellgrenze ist keine absolute RAM-Obergrenze für bösartige Archive.
Nicht vertrauenswürdige Dateien unter einem externen Prozess-/RAM-/Zeitlimit lesen.
`batch_size`: 1..65536, zwei Nachrichten im Kanal plus Worker-/Consumer-Batch.

## Kompatibilität und Consumer

Greenfield-Übernahme des PoC, keine zugesicherte Kompatibilität für
`rust_xlsx_filter` oder `extract_rows`. JSON-Ausdrücke und Filtersemantik bleiben
erhalten; Ergebniszeilen sind jetzt `Row` statt veränderlicher Dicts. Direkte
Consumer im Repository sind CLI, Tests und Benchmark; keine anderen Consumer
sind hier vorhanden. Das PoC ist eine historische Referenz und wird nicht mitgebaut.
