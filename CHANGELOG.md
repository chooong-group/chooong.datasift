# Changelog

## Unreleased

### Added

- Installierbares `chooong.datasift` mit nativer Rust-XLSX-/XLSM-Streaming-Engine.
- Typisierte Filtermodelle, unveränderliche Ergebniszeilen und schließbare Batches.
- CLI `chooong-datasift` mit atomarer NDJSON-Dateiausgabe.
- Reproduzierbare Python-/Rust-Abhängigkeiten und Package-Prüfungen.

### Changed

- Greenfield-Übernahme des PoC: Importpfad `chooong.datasift`, Ergebnisse als `Row`.
  `rust_xlsx_filter` und `extract_rows` sind keine unterstützten APIs.
- Metadaten verwenden die Apache-2.0-Lizenz des Repositorys.

### Fixed

- Threadsicherheit des nativen Empfängers und Erkennung unvollständiger XML-Dokumente.
- Ungültige doppelte Build-Konfiguration und projektfremde CI-Kommandos ersetzt.
- CLI schützt auch die Filterdatei vor Überschreiben.
