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

`sheet` ist ein erforderliches Feld: ein nichtleerer Blattname wählt genau dieses
Blatt; JSON-`null` durchsucht alle Arbeitsblätter (auch ausgeblendete) in ihrer
Workbook-Reihenfolge. Diagrammseiten ohne Tabellenzeilen werden nicht durchsucht.
Ein fehlendes Feld, leere Strings und andere Typen sind kein Ersatz für `null`.
Die Treffer werden ohne Deduplizierung und ohne zusätzliche Metadatenfelder
zusammengeführt. Gleiche Datensätze auf zwei Blättern bleiben zwei Treffer.

Im Modus `sheet: null` wird jedes Blatt unabhängig ausgewertet. Ohne `source`
gilt `header_row` auf jedem Blatt: Leere Blätter, fehlende Kopfzeilen oder fehlende
Filterspalten liefern keine Treffer; numerische Kopfzellen sind keine Spaltennamen.
Die übrigen Text-Header werden einschließlich ihrer Indizes pro Blatt aufgelöst.
Ist kein Blattschema passend, ist das Ergebnis leer. Mit `source` gelten dieselben
expliziten Spalten-/Zeilengrenzen auf jedem Blatt; es wird kein Header interpretiert.
Fehlerhafte Filter (einschließlich Rust-Regex) werden auch bei leeren Workbooks vor
Iterator-Rückgabe abgewiesen. ZIP-/XML-Fehler, mehrdeutige Header und ungültige Werte
in ausgewerteten Bereichen bleiben Fehler. Die Schemaauflösung weiterer Blätter
kann erst während der Iteration erfolgen; entsprechende Fehler sind `RuntimeError`.
Batches überschreiten keine Blattgrenzen, und `--output` bleibt über alle Blätter
atomar. Shared Strings werden einmal für das Workbook geladen.

`source` trennt die Quellauswahl von der
Filterbedingung. Beispiel: Eine Tabelle mit ein-/mehrzeiligen Headern oberhalb von
Zeile 7 liegt in C–E; eine zweite Tabelle kann daneben stehen:

```json
{
  "sheet": "Daten",
  "source": {
    "columns": [
      {"name": "Kunde", "column": "C"},
      {"name": "Umsatz", "column": "D"},
      {"name": "UmsatzVorjahr", "column": "E"}
    ],
    "data_start_row": 7,
    "data_end_row": 10,
    "skip_rows": [8]
  },
  "where": {"column": "Umsatz", "op": "gte", "value": 100}
}
```

- `ColumnBinding(name, column)` bindet einen eindeutigen Ausgabe-/Filternamen an
  eine absolute Excel-Spalte A..XFD (Großbuchstaben). Mehrere Namen dürfen bewusst
  dieselbe physische Spalte referenzieren. Ohne Bindung wird kein Feld extrahiert.
- `TableSource.columns` ist eine nichtleere Liste mit höchstens 16384 Bindungen.
  Die Listenreihenfolge bestimmt die Ausgabereihenfolge. Tatsächliche Headertexte
  werden in diesem Modus nicht als Schema interpretiert: gleiche Überschriften,
  mehrere Headerzeilen und verbundene Headerzellen sind deshalb kein Hindernis.
  Automatisches Header-Zusammenfügen oder Tabellen-Erkennen findet nicht statt.
- `data_start_row` ist erforderlich, `data_end_row` optional und inklusive.
  Beide liegen in 1..1048576; das Ende darf nicht vor dem Beginn liegen. Ohne Ende
  gilt der Rest des Arbeitsblatts als gewählter Zeilenbereich.
- `skip_rows` nennt explizite Kommentar-/Zwischenzeilen innerhalb des Datenbereichs.
  Kommentare oberhalb des Datenbeginns sind ohnehin ausgeschlossen. Kommentare
  innerhalb des Bereichs werden nicht heuristisch erkannt; sie müssen über
  `skip_rows`, Grenzen oder passende `where`-Bedingungen ausgeschlossen werden.
- Eine Maske wählt eine Quelle. Für mehrere Tabellen getrennte Masken verwenden;
  die Positionen werden weder geraten noch stillschweigend zusammengeführt.
- Zellwerte außerhalb der expliziten Quelle werden nicht typisiert oder ausgegeben.
  ZIP-/XML-Struktur, Zellkoordinaten und Ressourcenlimits werden weiterhin geprüft,
  auch hinter `data_end_row`. Ein beschädigtes Gesamt-XML bleibt ein Fehler.

Ohne `source` gilt der einfache Header-Modus: `header_row` (Standard 1) bezeichnet
exakt eine Kopfzeile. Benannte Spalten werden ausgegeben, leere Überschriften und
Zusatzdaten ohne Überschrift nicht. Wiederholt sich ein exakter Headername,
erhalten **alle** seine Vorkommen ab 1 einen Index von links nach rechts:
`Umsatz`, `Umsatz` werden `Umsatz_1`, `Umsatz_2`. Bei drei Vorkommen kommt
`Umsatz_3` hinzu. Eindeutige Header bleiben unverändert. Die indizierten Namen
gelten gleichermaßen für Filter und Ausgabe; der mehrdeutige Name `Umsatz`
ist dann kein gültiger Filtername. Leere Spalten verändern die Nummerierung nicht.
Eine Kollision mit einer schon vorhandenen Überschrift (etwa `Umsatz_1` neben
zweimal `Umsatz`) wird vor Treffern des jeweiligen Blatts abgewiesen; für diesen Fall lassen
sich mit `source.columns` explizit eindeutige Namen vergeben. Bei expliziter Blattauswahl bleiben nichttextuelle
Überschriften ein Fehler. Namen werden weder getrimmt noch in ihrer
Groß-/Kleinschreibung geändert. Explizite `source.columns.name` sind bereits
gewählte Aliase und müssen weiterhin eindeutig sein.
`header_row` darf mit `source` nicht auf einen anderen Wert als seinen ungenutzten
Standard 1 gesetzt werden. Unbekannte Aliase bei einem gewählten Blatt bzw. bei
expliziten `source`-Bindungen werden abgewiesen. Die oben beschriebene Suche über
alle Blätter ohne `source` überspringt dagegen unpassende Blattschemas.

**Contract-Korrektur:** Die zuvor lokal eingeführten `__column_*`-Zusatzfelder
entfallen. Die Maske bestimmt den Extraktionsumfang. Bestehende einfache Masken
bleiben gültig; es werden keine zuvor unbenannten Zusatzfelder mehr angehängt.

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
keine Backreferences oder Lookarounds. Sie werden pro Blattschema vorbereitet,
bei der blattübergreifenden Suche zusätzlich vorab validiert; keine Kompilierung
pro Datenzeile.

Python-Modelle: `ScalarCondition`, `MembershipCondition`, `NumericCondition`,
`TextCondition`, `EmptyCondition`, `AllOf(conditions=...)`, `AnyOf(conditions=...)`,
`Not(condition=...)`, `ColumnBinding`, `TableSource`, `FilterMask`. `Operator` ist ein `StrEnum`.

## Ergebnisse und Lebenszyklus

`iter_matching_batches(path, mask, *, batch_size=1024)` liefert einen
`BatchIterator` mit `list[Row]`, `close()` und Kontextmanager-Unterstützung.
Sheet, Filter-Aliase und Regex werden vor Rückgabe geprüft. Im einfachen Modus
mit gewähltem Blatt wird außerdem die Kopfzeile gelesen; bei `source` werden die expliziten Bindungen
geprüft, keine tatsächlichen Headertexte.
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
