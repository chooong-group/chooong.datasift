//! Deterministic file expansion and native streaming CSV adapter.
use crate::{
    engine::{Sink, Statistics},
    filter::{Config, FileErrors},
    value::CellValue,
    Message,
};
use std::{
    collections::BTreeSet,
    fs::File,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::SyncSender,
        Arc,
    },
};

pub fn expand(inputs: &[String]) -> Result<Vec<PathBuf>, String> {
    if inputs.is_empty() {
        return Err("Mindestens eine Eingabe erforderlich".into());
    }
    let mut files = BTreeSet::new();
    for input in inputs {
        if input.contains(['*', '?', '[']) {
            let mut found = false;
            for path in glob::glob(input).map_err(|_| "Ungültiges Glob-Muster")? {
                let path = path.map_err(|_| "Glob kann nicht gelesen werden")?;
                files.insert(path);
                found = true;
            }
            if !found {
                return Err("Glob ohne Treffer".into());
            }
        } else {
            files.insert(PathBuf::from(input));
        }
    }
    Ok(files.into_iter().collect())
}
#[allow(clippy::too_many_arguments)]
pub fn scan(
    inputs: &[String],
    config: &Config,
    batch_size: usize,
    sender: &SyncSender<Message>,
    cancelled: &Arc<AtomicBool>,
    events: bool,
    rejects: bool,
) -> Result<(), String> {
    let files = expand(inputs)?;
    let start = std::time::Instant::now();
    let mut stats = Statistics::default();
    if events
        || files.len() > 1
        || (config.source.is_none()
            && config.sources.is_none()
            && config.required_columns.is_empty())
    {
        sender
            .send(Message::Ready(vec![]))
            .map_err(|_| "Verbraucher geschlossen")?;
    }
    let mut failed = false;
    for path in files {
        if cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        let result = match path
            .extension()
            .and_then(|e| e.to_str())
            .map(str::to_ascii_lowercase)
            .as_deref()
        {
            Some("csv") => csv_scan(
                &path, config, batch_size, sender, cancelled, events, rejects, &mut stats,
            ),
            Some("xlsx" | "xlsm") => crate::xlsx::scan(
                &path, config, batch_size, sender, cancelled, events, rejects, &mut stats,
            ),
            _ => Err("Dateiformat muss CSV, XLSX oder XLSM sein".into()),
        };
        if let Err(error) = result {
            if config.file_errors == FileErrors::Fail {
                return Err(error);
            }
            failed = true;
            if stats.diagnostics.len() >= 16384 {
                return Err("Zu viele Dateifehler".into());
            }
            stats.diagnostics.push(serde_json::json!({"code":"FILE_ERROR","file":path.to_string_lossy(),"complete":false}));
        }
    }
    stats.complete = !failed && !stats.schema_errors;
    stats.seconds = start.elapsed().as_secs_f64();
    sender
        .send(Message::Statistics(
            serde_json::to_string(&stats).map_err(|e| e.to_string())?,
        ))
        .map_err(|_| "Verbraucher geschlossen")?;
    if stats.schema_errors {
        return Err(
            "Schemaabweichungen; unabhängige Tabellen wurden weiterverarbeitet (SCHEMA_MISMATCH)"
                .into(),
        );
    }
    if failed {
        return Err("Mindestens eine Datei unvollständig verarbeitet; siehe Diagnosen".into());
    }
    Ok(())
}
#[allow(clippy::too_many_arguments)]
fn csv_scan(
    path: &Path,
    config: &Config,
    batch_size: usize,
    sender: &SyncSender<Message>,
    cancelled: &Arc<AtomicBool>,
    events: bool,
    rejects: bool,
    stats: &mut Statistics,
) -> Result<(), String> {
    let file = File::open(path).map_err(|_| "CSV nicht lesbar")?;
    let encoding = encoding_rs::Encoding::for_label(config.csv.encoding.as_bytes())
        .ok_or("Unbekanntes CSV-Encoding")?;
    let decoder = crate::encoding::StrictDecoder::new(file, encoding);
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .delimiter(config.csv.delimiter.as_bytes()[0])
        .quote(config.csv.quote.as_bytes()[0])
        .from_reader(decoder);
    let mut sink = Sink::new(
        config,
        sender,
        cancelled,
        batch_size,
        events,
        rejects,
        path.to_string_lossy().into_owned(),
        "csv".into(),
        false,
        stats,
    );
    if !config.csv.header && config.source.is_none() && config.sources.is_none() {
        return Err("CSV ohne Header benötigt explizite source-Bindings".into());
    }
    sink.initialize()?;
    for (index, result) in reader.records().enumerate() {
        if cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        let record = result.map_err(|_| "Beschädigter CSV-Datensatz")?;
        if record.len() > 16384 {
            return Err("CSV überschreitet 16384 Spalten".into());
        }
        if record.iter().any(|s| s.len() > 2 * 1024 * 1024) {
            return Err("CSV-Zelle zu groß oder ungültiges Encoding".into());
        }
        let row = record
            .iter()
            .map(|s| {
                if s.is_empty() {
                    CellValue::Empty
                } else {
                    CellValue::Text(s.to_owned())
                }
            })
            .collect();
        sink.on_row(
            u32::try_from(index + 1).map_err(|_| "Zu viele CSV-Zeilen")?,
            row,
        )?;
    }
    sink.finish()?;
    if !sink.has_headers() {
        sink.diagnostic("NO_SCHEMA", None)?;
    }
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/input.rs"]
mod tests;
