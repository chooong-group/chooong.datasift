# Changelog

## Unreleased

### Added

- Automatische Suche mehrerer vollständiger Tabellenschemata pro Arbeitsblatt,
  auch nebeneinander und versetzt untereinander; Treffer bleiben je Tabelle getrennt
  und werden in Zeilenreihenfolge zusammengeführt.

- Beispielmaske `examples/filter_schmutzig.json` für mehrzeilige Zellnamen und
  verschachtelte Bedingungen ohne feste Headerposition.

- `sheet: null` durchsucht alle Arbeitsblätter und führt Treffer in Workbook-
  Reihenfolge zusammen; die atomare Ausgabe gilt über alle Blätter hinweg.

- Automatische Indizes für wiederholte Header: `Umsatz_1`, `Umsatz_2`, …;
  eindeutige Namen bleiben unverändert, Namenskollisionen werden abgewiesen.
- Explizite `TableSource`-/`ColumnBinding`-Maske für beliebige Tabellenpositionen,
  doppelte/mehrzeilige Header, Datenbereich und auszuschließende Kommentarzeilen.

- Installierbares `chooong.datasift` mit nativer Rust-XLSX-/XLSM-Streaming-Engine.
- Typisierte Filtermodelle, unveränderliche Ergebniszeilen und schließbare Batches.
- CLI `chooong-datasift` mit atomarer NDJSON-Dateiausgabe.
- Reproduzierbare Python-/Rust-Abhängigkeiten und Package-Prüfungen.

### Changed

- Implementierungsmodule heißen `models`, `reader` und `rust`; Imports sind
  entsprechend der verschärften Ruff-Regeln absolut. Öffentliche Exporte bleiben erhalten.

- **Breaking Change:** Automatische Headersuche anhand aller Maskenspalten;
  `header_row` entfällt. Ausgabe und Zellkonvertierung sind auf in `where`
  referenzierte Spalten beschränkt, auch bei expliziten `source`-Bindungen.

- Greenfield-Übernahme des PoC: Importpfad `chooong.datasift`, Ergebnisse als `Row`.
  `rust_xlsx_filter` und `extract_rows` sind keine unterstützten APIs.
- Metadaten verwenden die Apache-2.0-Lizenz des Repositorys.

### Fixed

- XML-Zeilenenden in Shared-/Inline-Strings und CDATA werden korrekt normalisiert;
  mehrzeilige Header bleiben nach erneutem Speichern in Excel zur Maske passend.

- Contract-Korrektur: Nur ausgewählte Felder passender Zeilen werden extrahiert;
  die lokal eingeführten `__column_*`-Zusatzfelder entfallen.
- Threadsicherheit des nativen Empfängers und Erkennung unvollständiger XML-Dokumente.
- Ungültige doppelte Build-Konfiguration und projektfremde CI-Kommandos ersetzt.
- CLI schützt auch die Filterdatei vor Überschreiben.

### Removed

- Historischen PoC `rust_xlsx_filter/` entfernt; das Package liegt ausschließlich
  unter `src/chooong/datasift` und `native`.
