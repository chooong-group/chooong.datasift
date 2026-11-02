//! Streaming native serializers and an explicit recoverable two-file commit protocol.
use crate::recovery::{Entry, Journal, Transaction};
use crate::{
    filter::Config,
    value::{Record, RecordKind},
    Message,
};
use arrow_array::{
    ArrayRef, BooleanArray, Date32Array, Decimal256Array, Float64Array, Int32Array, Int64Array,
    ListArray, RecordBatch, StringArray, StructArray, TimestampMicrosecondArray,
};
use arrow_buffer::{i256, OffsetBuffer, ScalarBuffer};
use arrow_schema::{DataType, Field, Fields, Schema};
use parquet::arrow::ArrowWriter;
use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    prelude::*,
};
use serde_json::Value;
#[cfg(test)]
use std::fs::{self, OpenOptions};

use std::{
    fs::File,
    io::{BufWriter, Write},
    path::{Path, PathBuf},
    sync::{atomic::AtomicBool, mpsc::sync_channel, Arc},
};

fn cell_fields() -> Fields {
    vec![
        Field::new("name", DataType::Utf8, false),
        Field::new("text", DataType::Utf8, true),
        Field::new("integer", DataType::Int64, true),
        Field::new("float", DataType::Float64, true),
        Field::new("boolean", DataType::Boolean, true),
        Field::new("decimal", DataType::Decimal256(76, 28), true),
        Field::new("currency", DataType::Utf8, true),
        Field::new("date", DataType::Date32, true),
        Field::new(
            "datetime",
            DataType::Timestamp(arrow_schema::TimeUnit::Microsecond, None),
            true,
        ),
        Field::new("nanosecond_remainder", DataType::Int32, true),
        Field::new("utc_offset_seconds", DataType::Int32, true),
    ]
    .into()
}
fn schema() -> Arc<Schema> {
    Arc::new(Schema::new(vec![
        Field::new("kind", DataType::Utf8, false),
        Field::new("file", DataType::Utf8, false),
        Field::new("sheet", DataType::Utf8, false),
        Field::new("table", DataType::Utf8, false),
        Field::new("row", DataType::Int64, false),
        Field::new(
            "values",
            DataType::List(Arc::new(Field::new(
                "item",
                DataType::Struct(cell_fields()),
                false,
            ))),
            false,
        ),
        Field::new("reasons", DataType::Utf8, false),
        Field::new("source_types", DataType::Utf8, false),
    ]))
}
fn decimal(value: &str) -> Result<i256, String> {
    let d = crate::rules::decimal_text(value, None)?;
    let mut n = i256::from_i128(d.mantissa());
    for _ in d.scale()..28 {
        n = n
            .checked_mul(i256::from_i128(10))
            .ok_or("Decimal256 out of range")?;
    }
    Ok(n)
}
fn parquet_batch(records: &[Record]) -> Result<RecordBatch, String> {
    let mut names = Vec::new();
    let mut texts = Vec::new();
    let mut ints = Vec::new();
    let mut floats = Vec::new();
    let mut bools = Vec::new();
    let mut decimals = Vec::new();
    let mut currencies = Vec::new();
    let mut dates = Vec::new();
    let mut datetimes = Vec::new();
    let mut nanos = Vec::new();
    let mut utc_offsets = Vec::new();
    let mut offsets = vec![0_i32];
    for record in records {
        for (name, value) in &record.values {
            names.push(name.as_str());
            let mut text = None;
            let mut int = None;
            let mut float = None;
            let mut boolean = None;
            let mut dec = None;
            let mut currency = None;
            let mut date = None;
            let mut datetime = None;
            let mut nano = None;
            let mut utc_offset = None;
            match value {
                Value::String(s) => text = Some(s.as_str()),
                Value::Bool(b) => boolean = Some(*b),
                Value::Number(n) => {
                    if let Some(n) = n.as_i64() {
                        int = Some(n)
                    } else {
                        float = n.as_f64()
                    }
                }
                Value::Object(o) => match o.get("type").and_then(Value::as_str) {
                    Some("decimal") => {
                        dec = Some(decimal(o["value"].as_str().ok_or("Missing decimal")?)?)
                    }
                    Some("money") => {
                        dec = Some(decimal(o["amount"].as_str().ok_or("Missing amount")?)?);
                        currency = o["currency"].as_str();
                    }
                    Some("date") => {
                        let d = chrono::NaiveDate::parse_from_str(
                            o["value"].as_str().ok_or("Missing date")?,
                            "%Y-%m-%d",
                        )
                        .map_err(|_| "Invalid date")?;
                        date = Some(
                            i32::try_from(
                                d.signed_duration_since(
                                    chrono::NaiveDate::from_ymd_opt(1970, 1, 1)
                                        .ok_or("Invalid date")?,
                                )
                                .num_days(),
                            )
                            .map_err(|_| "Date out of range")?,
                        );
                    }
                    Some("datetime") => {
                        let text = o["value"].as_str().ok_or("Missing time")?;
                        let d = if let Ok(zoned) = chrono::DateTime::parse_from_rfc3339(text) {
                            utc_offset = Some(zoned.offset().local_minus_utc());
                            zoned.with_timezone(&chrono::Utc)
                        } else {
                            chrono::NaiveDateTime::parse_from_str(text, "%Y-%m-%dT%H:%M:%S%.f")
                                .map_err(|_| "Invalid time")?
                                .and_utc()
                        };
                        datetime = Some(d.timestamp_micros());
                        nano = Some((d.timestamp_subsec_nanos() % 1000) as i32);
                    }
                    _ => return Err("Unknown output type".into()),
                },
                Value::Null => (),
                _ => return Err("Invalid cell value".into()),
            }
            texts.push(text);
            ints.push(int);
            floats.push(float);
            bools.push(boolean);
            decimals.push(dec);
            currencies.push(currency);
            dates.push(date);
            datetimes.push(datetime);
            nanos.push(nano);
            utc_offsets.push(utc_offset);
        }
        offsets.push(i32::try_from(names.len()).map_err(|_| "Output batch is too large")?);
    }
    let arrays: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from(names)),
        Arc::new(StringArray::from(texts)),
        Arc::new(Int64Array::from(ints)),
        Arc::new(Float64Array::from(floats)),
        Arc::new(BooleanArray::from(bools)),
        Arc::new(
            Decimal256Array::from(decimals)
                .with_precision_and_scale(76, 28)
                .map_err(|e| e.to_string())?,
        ),
        Arc::new(StringArray::from(currencies)),
        Arc::new(Date32Array::from(dates)),
        Arc::new(TimestampMicrosecondArray::from(datetimes)),
        Arc::new(Int32Array::from(nanos)),
        Arc::new(Int32Array::from(utc_offsets)),
    ];
    let cells = StructArray::new(cell_fields(), arrays, None);
    let values = ListArray::new(
        Arc::new(Field::new("item", DataType::Struct(cell_fields()), false)),
        OffsetBuffer::new(ScalarBuffer::from(offsets)),
        Arc::new(cells),
        None,
    );
    let reasons: Vec<_> = records
        .iter()
        .map(|r| serde_json::to_string(&r.reasons))
        .collect::<Result<_, _>>()
        .map_err(|e| e.to_string())?;
    RecordBatch::try_new(
        schema(),
        vec![
            Arc::new(StringArray::from(
                records
                    .iter()
                    .map(|r| {
                        if r.kind == RecordKind::Matched {
                            "matched"
                        } else {
                            "rejected"
                        }
                    })
                    .collect::<Vec<_>>(),
            )),
            Arc::new(StringArray::from(
                records.iter().map(|r| r.file.as_str()).collect::<Vec<_>>(),
            )),
            Arc::new(StringArray::from(
                records.iter().map(|r| r.sheet.as_str()).collect::<Vec<_>>(),
            )),
            Arc::new(StringArray::from(
                records.iter().map(|r| r.table.as_str()).collect::<Vec<_>>(),
            )),
            Arc::new(Int64Array::from(
                records.iter().map(|r| i64::from(r.row)).collect::<Vec<_>>(),
            )),
            Arc::new(values),
            Arc::new(StringArray::from(reasons)),
            Arc::new(StringArray::from(
                records
                    .iter()
                    .map(|r| serde_json::to_string(&r.source_types))
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|e| e.to_string())?,
            )),
        ],
    )
    .map_err(|e| e.to_string())
}

enum Writer {
    Json(BufWriter<File>, bool),
    Parquet(Box<ArrowWriter<File>>),
}
impl Writer {
    #[cfg(test)]
    fn new(path: &Path, parquet: bool, rejected: bool) -> Result<Self, String> {
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|_| "Cannot create temporary output")?;
        Self::from_file(file, parquet, rejected)
    }
    fn from_file(file: File, parquet: bool, rejected: bool) -> Result<Self, String> {
        if parquet {
            Ok(Self::Parquet(Box::new(
                ArrowWriter::try_new(file, schema(), None).map_err(|e| e.to_string())?,
            )))
        } else {
            Ok(Self::Json(BufWriter::new(file), rejected))
        }
    }
    fn write(&mut self, records: &[Record]) -> Result<(), String> {
        match self {
            Self::Json(writer, rejected) => {
                for record in records {
                    if *rejected {
                        serde_json::to_writer(&mut *writer, record)
                    } else {
                        serde_json::to_writer(&mut *writer, &record.values)
                    }
                    .map_err(|_| "NDJSON write failed")?;
                    writer.write_all(b"\n").map_err(|_| "NDJSON write failed")?;
                }
            }
            Self::Parquet(writer) => {
                writer
                    .write(&parquet_batch(records)?)
                    .map_err(|e| e.to_string())?;
                writer.flush().map_err(|e| e.to_string())?;
            }
        }
        Ok(())
    }
    fn finish(self) -> Result<File, String> {
        match self {
            Self::Json(mut writer, _) => {
                writer.flush().map_err(|_| "Flush failed")?;
                let file = writer.into_inner().map_err(|_| "Flush failed")?;
                file.sync_all().map_err(|_| "fsync failed")?;
                Ok(file)
            }
            Self::Parquet(writer) => {
                let file = writer.into_inner().map_err(|e| e.to_string())?;
                file.sync_all().map_err(|_| "fsync failed")?;
                Ok(file)
            }
        }
    }
}
fn journal_path(output: &Path) -> Result<PathBuf, String> {
    let name = output
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("Invalid output name")?;
    Ok(output.with_file_name(format!(".{name}.datasift-commit.json")))
}
fn absolute_output(path: &str) -> Result<PathBuf, String> {
    let path = Path::new(path);
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let parent = parent
        .canonicalize()
        .map_err(|_| "Output directory does not exist")?;
    let result = parent.join(path.file_name().ok_or("Missing output name")?);
    if result.is_symlink() {
        return Err("Output must not be a symlink".into());
    }
    Ok(result)
}
fn same_file(a: &Path, b: &Path) -> bool {
    if a.canonicalize()
        .ok()
        .zip(b.canonicalize().ok())
        .is_some_and(|(a, b)| a == b)
    {
        return true;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if let (Ok(a), Ok(b)) = (a.metadata(), b.metadata()) {
            return a.dev() == b.dev() && a.ino() == b.ino();
        }
    }
    false
}
fn export(
    paths: Vec<String>,
    filter_json: String,
    output: String,
    rejected_output: Option<String>,
    batch_size: usize,
) -> Result<String, String> {
    if !(1..=65536).contains(&batch_size) {
        return Err("Invalid batch size".into());
    }
    let config = Config::parse(&filter_json)?;
    let output = absolute_output(&output)?;
    let rejected = rejected_output
        .as_deref()
        .map(absolute_output)
        .transpose()?;
    let inputs = crate::input::expand(&paths)?;
    let destinations: Vec<_> = std::iter::once(&output)
        .chain(rejected.iter())
        .cloned()
        .collect();
    if destinations.len() == 2 && same_file(&destinations[0], &destinations[1]) {
        return Err("Outputs refer to the same file".into());
    }
    let journal_file = journal_path(&output)?;
    let reserved: Vec<_> = destinations
        .iter()
        .map(|path| {
            path.with_file_name(format!(
                ".{}.datasift.lock",
                path.file_name().and_then(|s| s.to_str()).unwrap_or("")
            ))
        })
        .chain(std::iter::once(journal_file.clone()))
        .collect();
    if destinations.iter().any(|p| reserved.contains(p)) {
        return Err("Outputs conflict with commit/lock metadata".into());
    }
    let transaction = Transaction::new(&destinations)?;
    for destination in std::iter::once(&output).chain(rejected.iter()) {
        for input in &inputs {
            if same_file(input, destination) {
                return Err("Output must not overwrite an input".into());
            }
        }
    }
    if rejected.as_ref() == Some(&output) {
        return Err("Output paths must be different".into());
    }
    if journal_file.exists() {
        return Err("Incomplete commit; run recover_export".into());
    }
    let mut entries = Vec::new();
    let generation = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| "Invalid system time")?
        .as_nanos();
    for (index, destination) in std::iter::once(&output).chain(rejected.iter()).enumerate() {
        let stage = destination.with_file_name(format!(
            ".{}.datasift-{}-{generation}-{index}.tmp",
            destination
                .file_name()
                .and_then(|s| s.to_str())
                .ok_or("Invalid name")?,
            std::process::id()
        ));
        entries.push(Entry {
            destination: destination.clone(),
            stage,
            sha256: String::new(),
        });
    }
    let mut journal = Journal {
        version: 1,
        entries,
    };
    let result = (|| {
        let mut matched = Writer::from_file(
            transaction.create_stage(0, &journal.entries[0].stage)?,
            output.extension().is_some_and(|e| e == "parquet"),
            false,
        )?;
        let mut rejects = if let Some(path) = &rejected {
            Some(Writer::from_file(
                transaction.create_stage(1, &journal.entries[1].stage)?,
                path.extension().is_some_and(|e| e == "parquet"),
                true,
            )?)
        } else {
            None
        };
        let (sender, receiver) = sync_channel(2);
        let cancelled = Arc::new(AtomicBool::new(false));
        let worker_cancelled = Arc::clone(&cancelled);
        let worker = std::thread::spawn(move || {
            let outcome = crate::input::scan(
                &paths,
                &config,
                batch_size,
                &sender,
                &worker_cancelled,
                true,
                rejected.is_some(),
            );
            let _ = sender.send(match outcome {
                Ok(()) => Message::Done,
                Err(e) => Message::Failure(e),
            });
        });
        let mut statistics = None;
        let scan = (|| {
            loop {
                match receiver
                    .recv()
                    .map_err(|_| "Worker terminated unexpectedly")?
                {
                    Message::Ready(_) => (),
                    Message::Statistics(s) => statistics = Some(s),
                    Message::Records(records) => {
                        let (m, r): (Vec<_>, Vec<_>) = records
                            .into_iter()
                            .partition(|r| r.kind == RecordKind::Matched);
                        if !m.is_empty() {
                            matched.write(&m)?;
                        }
                        if let Some(writer) = &mut rejects {
                            if !r.is_empty() {
                                writer.write(&r)?;
                            }
                        }
                    }
                    Message::Done => break,
                    Message::Failure(e) => return Err(e),
                    Message::Batch(_) => return Err("Unexpected result stream".into()),
                }
            }
            Ok(())
        })();
        cancelled.store(true, std::sync::atomic::Ordering::Relaxed);
        drop(receiver);
        worker.join().map_err(|_| "Worker panic")?;
        scan?;
        let mut files = vec![matched.finish()?];
        if let Some(writer) = rejects {
            files.push(writer.finish()?);
        }
        for (entry, file) in journal.entries.iter_mut().zip(&mut files) {
            entry.sha256 = crate::recovery::file_digest(file)?;
        }
        let journal_bytes =
            serde_json::to_vec(&journal).map_err(|_| "Journal serialization failed")?;
        let journal_sha256 = crate::recovery::digest(&journal_bytes);
        transaction.write_journal(&journal_file, &journal_bytes)?;
        transaction
            .commit(&journal, &journal_file, &journal_sha256)
            .map_err(|error| format!("{error}; recovery journal_sha256={journal_sha256}"))?;
        statistics.ok_or("Missing statistics".into())
    })();
    if !transaction.has_journal(&journal_file) {
        transaction.cleanup(&journal);
    }

    result
}
#[pyfunction(name="export",signature=(paths,filter_json,output,rejected_output=None,batch_size=1024))]
pub fn export_native(
    py: Python<'_>,
    paths: Vec<String>,
    filter_json: String,
    output: String,
    rejected_output: Option<String>,
    batch_size: usize,
) -> PyResult<String> {
    py.detach(move || export(paths, filter_json, output, rejected_output, batch_size))
        .map_err(PyRuntimeError::new_err)
}
#[pyfunction(signature=(output,journal_sha256,rejected_output=None))]
pub fn recover_export(
    py: Python<'_>,
    output: String,
    journal_sha256: String,
    rejected_output: Option<String>,
) -> PyResult<()> {
    py.detach(move || {
        let output = absolute_output(&output)?;
        let path = journal_path(&output)?;
        let mut targets = vec![output];
        if let Some(rejected) = rejected_output {
            targets.push(absolute_output(&rejected)?);
        }
        crate::recovery::recover(targets, &path, &journal_sha256)
    })
    .map_err(PyValueError::new_err)
}

#[cfg(test)]
#[path = "../tests/pipeline/export.rs"]
mod integration_tests;
#[cfg(test)]
#[path = "../tests/unit/output.rs"]
mod tests;
