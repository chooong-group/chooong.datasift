# Öffentlicher Vertrag v1

Distribution: `chooong.datasift`, Import: `chooong.datasift`, CLI:
`chooong-datasift` bzw. `python -m chooong.datasift`. Die Initialversion bleibt
0.1.0; keine Veröffentlichung oder Consumer-Migration ist Teil dieses Auftrags.

Die Implementierung liegt in `models`, `reader` und der nativen Erweiterung
`rust` ohne führenden Unterstrich. Zugesicherte Importpfade bleiben die oben
genannten Exporte aus `chooong.datasift`; direkte Implementierungsimporte sind
kein zusätzlicher öffentlicher Contract. Die Python-Standardmodule `__init__`
und `__main__` behalten ihre Namen.

## JSON-Maske

Format v1 ist implizit, ohne Versionsfeld. `FilterMask` ist das kanonische
Eingabemodell; `FilterMask.model_json_schema(by_alias=True)` erzeugt das Schema.
Unbekannte Felder, Operatoren und falsche Werttypen werden abgewiesen.

```json
{"sheet":"Daten","where":{"column":"Land","op":"eq","value":"DE"}}
```

`sheet` ist ein erforderliches Feld: ein nichtleerer Blattname wählt genau dieses
Blatt; JSON-`null` durchsucht alle Arbeitsblätter (auch ausgeblendete) in ihrer
Workbook-Reihenfolge. Diagrammseiten ohne Tabellenzeilen werden nicht durchsucht.
Ein fehlendes Feld, leere Strings und andere Typen sind kein Ersatz für `null`.
Die Treffer werden ohne Deduplizierung und ohne zusätzliche Metadatenfelder
zusammengeführt. Gleiche Datensätze auf zwei Blättern bleiben zwei Treffer.

Ohne `source` sucht die Engine auf jedem Blatt von oben nach unten vollständige
Tabellenköpfe, die alle in `where` referenzierten Spalten enthalten. Nur Textzellen gelten
als Header; Titel, Zahlen und unvollständige Zeilen davor werden übersprungen.
Literale XML-Zeilenenden CRLF und CR werden beim Einlesen in LF normalisiert,
für Shared Strings, Inline Strings und CDATA, in Headern und Datenwerten.
Explizite Zeichenreferenzen wie `&#13;` bleiben das referenzierte Zeichen;
Leerzeichen und Groß-/Kleinschreibung werden nicht normalisiert.
Zeilenumbrüche innerhalb einer Headerzelle gehören zum exakten Namen. Doppelte
Header erhalten die unten beschriebenen Indizes. Kommentare und Nachbartabellen
werden nicht zu Ausgabespalten. Nach der Erkennung werden ausschließlich die
Maskenspalten konvertiert und ausgegeben, in physischer Spaltenreihenfolge.
Wiederholte vollständige Header beginnen einen neuen Tabellenbereich und sind
für diesen Bereich keine Datenzeile.
Echte Datensätze mit exakt diesen Headertexten sind dabei nicht unterscheidbar;
dafür explizite `source`-Bindungen und Datenzeilen verwenden.

Ein gewähltes Blatt ohne vollständigen Header ist ein `ValueError`; bei `sheet: null`
werden solche Blätter übersprungen. Ein Workbook ohne passendes Schema liefert
in diesem Modus keine Treffer. Alle Filterspalten werden auch bei `any` und `not`
benötigt: fehlende Spalten werden nicht als leere Werte interpretiert.
Mit `source` gelten die expliziten Bindungen auf jedem Blatt; auch hier werden nur
in `where` verwendete Namen ausgegeben, in Bindungsreihenfolge.

Mehrere Tabellen können auf einem Blatt nebeneinander, untereinander oder versetzt
stehen. Eine Zeile mit mindestens zwei vollständigen Gruppen der wortgleichen
Maskennamen wird in unabhängige Schemata von links nach rechts aufgeteilt; jede
Gruppe enthält jeden Maskennamen genau einmal. Dafür sind mindestens zwei
unterschiedliche Maskenspalten nötig. Unvollständige Wiederholungsmuster werden
nicht geraten; ein einzelnes Zeilenschema behält seine indizierten Headernamen.
Insbesondere unterscheidet ein einzelner mehrfach vorkommender Name allein keine
benachbarten Tabellen von doppelten Spalten. Bei mehrdeutigen/teilweisen Gruppen
oder horizontalen Tabellen mit intern indizierten Maskennamen explizite Quellen
verwenden. Die Erkennung verwendet keine Formatierungsheuristik und rekonstruiert
keine über mehrere physische Zeilen verteilten Header.

Jeder Tabellenbereich bindet seine Spalten unabhängig. Ein späterer vollständiger
Header ersetzt aktive Bereiche, deren Spaltenintervall (erste bis letzte gewählte
Spalte) ihn überlappt. Nicht überlappende Nachbartabellen laufen weiter, auch mit
Datensätzen in derselben Zeile wie ein neuer Header. Die Erkennung legt kein Ende
anhand leerer Zeilen oder Kommentare fest; dafür bleiben explizite Quellen.
Treffer folgen Workbook-Reihenfolge, je Blatt der Zeilennummer und innerhalb einer
Zeile der linken gewählten Spalte. Sie werden weder dedupliziert noch mit
Tabellenmetadaten erweitert. Gleiche Schemata können einen gemeinsamen Batch haben;
vor einem Wechsel der Ausgabespaltenreihenfolge wird der bisherige Batch geleert.
Zeilen unterhalb des Headers werden anhand von `where` ausgewertet: Kommentare
mit denselben passenden Werten sind ohne zusätzliche fachliche Regel nicht von
Datensätzen unterscheidbar. Für feste Bereiche/Kommentare bleibt `source` verfügbar.

Fehlerhafte Filter einschließlich Rust-Regex werden vor Iterator-Rückgabe abgewiesen.
ZIP-/XML-Fehler, Mehrdeutigkeiten ausgewählter Header und ungültige ausgewählte
Zellwerte bleiben Fehler. Bei der Suche werden vor Headererkennung alle Zellwerte
benötigt; beschädigte Zellwerte in diesen Zeilen werden nicht kaschiert. Nach
der ersten Erkennung werden außerhalb aktiver Spalten zusätzlich gültige
Text-Headerkandidaten gelesen, um weitere Tabellen zu finden. Ungültige
unselektierte Werte werden dabei nicht zu Kandidaten oder Ausgabedaten.
Die Schemaauflösung weiterer Blätter erfolgt während der Iteration; entsprechende
Fehler sind `RuntimeError`. Batches überschreiten keine Blattgrenzen, und `--output`
bleibt über alle Blätter atomar. Shared Strings werden einmal geladen.

**Breaking Change im Greenfield-Contract v1:** `header_row` ist entfernt und wird
als unbekanntes Feld abgewiesen. Vorhandene Masken entfernen diesen Schlüssel.
Die Ausgabe enthält nur noch die in `where` referenzierten Spalten; wer weitere
Werte benötigt, muss diese in die fachliche Maske aufnehmen. Keine Versionsanhebung
oder Veröffentlichung in diesem Auftrag.

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
  dieselbe physische Spalte referenzieren. Nur in `where` verwendete Bindungen werden extrahiert.
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
- Mit `source` wählt eine Maske genau eine explizite Quelle. Für mehrere explizite
  Bereiche getrennte Masken verwenden; die automatische Mehrtabellensuche gilt
  ausschließlich ohne `source`.
- Zellwerte außerhalb der expliziten Quelle werden nicht typisiert oder ausgegeben.
  ZIP-/XML-Struktur, Zellkoordinaten und Ressourcenlimits werden weiterhin geprüft,
  auch hinter `data_end_row`. Ein beschädigtes Gesamt-XML bleibt ein Fehler.

Ohne `source` gilt die automatische Headersuche. Nur referenzierte Spalten
werden ausgegeben; leere oder unbenutzte Überschriften nicht. Innerhalb eines
einzelnen Zeilenschemas gilt: Wiederholt sich ein exakter Headername,
erhalten **alle** seine Vorkommen ab 1 einen Index von links nach rechts:
`Umsatz`, `Umsatz` werden `Umsatz_1`, `Umsatz_2`. Bei drei Vorkommen kommt
`Umsatz_3` hinzu. Eindeutige Header bleiben unverändert. Die indizierten Namen
gelten gleichermaßen für Filter und Ausgabe; der mehrdeutige Name `Umsatz`
ist dann kein gültiger Filtername. Leere Spalten verändern die Nummerierung nicht.
Eine Kollision eines ausgewählten Namens mit einer schon vorhandenen Überschrift (etwa `Umsatz_1` neben
zweimal `Umsatz`) wird vor Treffern des jeweiligen Blatts abgewiesen; für diesen Fall lassen
sich mit `source.columns` explizit eindeutige Namen vergeben. Nichttextuelle Zellen sind keine Header. Namen werden weder getrimmt noch in ihrer
Groß-/Kleinschreibung geändert. Explizite `source.columns.name` sind bereits
gewählte Aliase und müssen weiterhin eindeutig sein.
Unbekannte Aliase in `source` werden abgewiesen. Bei automatischer Suche muss
eine Kopfzeile mit sämtlichen ausgewählten Namen gefunden werden.

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
keine Backreferences oder Lookarounds. Sie werden vorab validiert und pro
erkanntem Tabellenschema vorbereitet; keine Kompilierung pro Datenzeile.

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

Speicher: Shared-Strings-Tabelle, aktive Tabellenschemata mit kompilierten Filtern,
größte XML-Token/Zeile und begrenzte Batches. Aktive Tabellen haben nicht überlappende
Spaltenintervalle innerhalb der höchstens 16384 Excel-Spalten.
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
sind hier vorhanden. Der ursprüngliche PoC ist entfernt und nur noch in der Git-Historie verfügbar.
