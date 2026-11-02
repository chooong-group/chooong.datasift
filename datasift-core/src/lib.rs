//! Rust/PyO3 bridge: the worker never constructs Python objects for rejected rows.
mod discovery;
mod encoding;
mod engine;
mod filter;
mod input;
mod output;
mod recovery;
mod rules;
mod value;
mod xlsx;

#[cfg(test)]
#[path = "../tests/support/mod.rs"]
mod test_support;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{sync_channel, Receiver};
use std::sync::{Arc, Mutex};
use std::thread;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use filter::Config;
use value::CellValue;

pub(crate) enum Message {
    Ready(Vec<(String, usize)>),
    Batch(Vec<Vec<CellValue>>),
    Records(Vec<value::Record>),
    Statistics(String),
    Done,
    Failure(String),
}

#[pyclass(module = "chooong.datasift.rust")]
pub struct BatchIterator {
    receiver: Mutex<Option<Receiver<Message>>>,
    cancelled: Arc<AtomicBool>,
    headers: Vec<(String, usize)>,
    finished: bool,
    statistics: Option<String>,
}

#[pymethods]
impl BatchIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Vec<Py<PyDict>>>> {
        if self.finished {
            return Ok(None);
        }
        loop {
            let receiver = self
                .receiver
                .get_mut()
                .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))?
                .take()
                .ok_or_else(|| PyRuntimeError::new_err("Iterator geschlossen"))?;
            // Receiver is Send (but not Sync); move ownership into/out of the GIL-free closure.
            let (receiver, message) = py.detach(move || {
                let message = receiver.recv();
                (receiver, message)
            });
            *self
                .receiver
                .get_mut()
                .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))? = Some(receiver);

            let message = message.map_err(|_| {
                self.finished = true;
                PyRuntimeError::new_err("Rust-Worker wurde unerwartet beendet")
            })?;
            match message {
                Message::Batch(rows) => {
                    let mut output = Vec::with_capacity(rows.len());
                    for row in rows {
                        let object = PyDict::new(py);
                        for (name, index) in &self.headers {
                            write_cell(
                                &object,
                                name,
                                row.get(*index).unwrap_or(&CellValue::Empty),
                            )?;
                        }
                        output.push(object.unbind());
                    }
                    return Ok(Some(output));
                }
                Message::Statistics(stats) => self.statistics = Some(stats),
                Message::Records(_) => {
                    return Err(PyRuntimeError::new_err("Unerwarteter Ergebnisstrom"))
                }
                Message::Done => {
                    self.finished = true;
                    self.receiver
                        .get_mut()
                        .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))?
                        .take();
                    return Ok(None);
                }
                Message::Failure(message) => {
                    self.finished = true;
                    self.receiver
                        .get_mut()
                        .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))?
                        .take();
                    return Err(PyRuntimeError::new_err(message));
                }
                Message::Ready(headers) => self.headers = headers,
            }
        }
    }

    fn statistics_json(&self) -> Option<String> {
        self.statistics.clone()
    }

    fn close(&mut self) -> PyResult<()> {
        self.cancelled.store(true, Ordering::Relaxed);
        self.receiver
            .get_mut()
            .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))?
            .take();
        self.finished = true;
        Ok(())
    }
}

impl Drop for BatchIterator {
    fn drop(&mut self) {
        self.cancelled.store(true, Ordering::Relaxed);
    }
}

fn write_cell(object: &Bound<'_, PyDict>, name: &str, value: &CellValue) -> PyResult<()> {
    match value {
        CellValue::Empty => object.set_item(name, object.py().None()),
        CellValue::IsoDate(value) | CellValue::Text(value) => object.set_item(name, value.as_str()),
        CellValue::Integer(value) => object.set_item(name, *value),
        CellValue::Float(value) => object.set_item(name, *value),
        CellValue::Bool(value) => object.set_item(name, *value),
        CellValue::StyledNumber { raw, .. } | CellValue::NumberText(raw) => {
            let value = CellValue::number(raw).map_err(PyRuntimeError::new_err)?;
            write_cell(object, name, &value)
        }
        CellValue::Currency(code) => object.set_item(name, code),
        CellValue::Decimal(value) => object.set_item(
            name,
            object
                .py()
                .import("decimal")?
                .getattr("Decimal")?
                .call1((value.to_string(),))?,
        ),
        CellValue::Money { amount, currency } => object.set_item(
            name,
            object
                .py()
                .import("chooong.datasift.models")?
                .getattr("Money")?
                .call1((
                    object
                        .py()
                        .import("decimal")?
                        .getattr("Decimal")?
                        .call1((amount.to_string(),))?,
                    currency,
                ))?,
        ),
        CellValue::Date(value) => object.set_item(
            name,
            object
                .py()
                .import("datetime")?
                .getattr("date")?
                .call_method1("fromisoformat", (value.to_string(),))?,
        ),
        CellValue::ZonedDateTime(value) => {
            let iso = value.to_rfc3339();
            if value.timestamp_subsec_nanos() % 1000 != 0 {
                object.set_item(
                    name,
                    object
                        .py()
                        .import("chooong.datasift.models")?
                        .getattr("PreciseDateTime")?
                        .call1((iso,))?,
                )
            } else {
                object.set_item(
                    name,
                    object
                        .py()
                        .import("datetime")?
                        .getattr("datetime")?
                        .call_method1("fromisoformat", (iso,))?,
                )
            }
        }
        CellValue::DateTime(value) => {
            let iso = value.format("%Y-%m-%dT%H:%M:%S%.f").to_string();
            if value.and_utc().timestamp_subsec_nanos() % 1000 != 0 {
                object.set_item(
                    name,
                    object
                        .py()
                        .import("chooong.datasift.models")?
                        .getattr("PreciseDateTime")?
                        .call1((iso,))?,
                )
            } else {
                object.set_item(
                    name,
                    object
                        .py()
                        .import("datetime")?
                        .getattr("datetime")?
                        .call_method1("fromisoformat", (iso,))?,
                )
            }
        }
    }
}

#[pyfunction(name = "iter_batches", signature = (xlsx_path, filter_json, batch_size = 1024))]
fn iter_batches_native(
    py: Python<'_>,
    xlsx_path: String,
    filter_json: String,
    batch_size: usize,
) -> PyResult<BatchIterator> {
    if !(1..=65_536).contains(&batch_size) {
        return Err(PyValueError::new_err(
            "batch_size muss zwischen 1 und 65536 liegen",
        ));
    }
    make_iterator(py, vec![xlsx_path], filter_json, batch_size, false, false)
}

fn make_iterator(
    py: Python<'_>,
    paths: Vec<String>,
    filter_json: String,
    batch_size: usize,
    events: bool,
    rejects: bool,
) -> PyResult<BatchIterator> {
    if !(1..=65536).contains(&batch_size) {
        return Err(PyValueError::new_err(
            "batch_size muss zwischen 1 und 65536 liegen",
        ));
    }
    // Validate structural JSON immediately, before creating a worker.
    let config = Config::parse(&filter_json).map_err(PyValueError::new_err)?;
    let cancelled = Arc::new(AtomicBool::new(false));
    let worker_cancelled = Arc::clone(&cancelled);
    // One ready/batch in flight plus two buffered batches: memory bound by consumer speed.
    let (sender, receiver) = sync_channel::<Message>(2);

    thread::Builder::new()
        .name("xlsx-json-filter".into())
        .spawn(move || {
            let outcome = input::scan(
                &paths,
                &config,
                batch_size,
                &sender,
                &worker_cancelled,
                events,
                rejects,
            );
            if !worker_cancelled.load(Ordering::Relaxed) {
                match outcome {
                    Ok(()) => {
                        let _ = sender.send(Message::Done);
                    }
                    Err(error) => {
                        let _ = sender.send(Message::Failure(error));
                    }
                }
            }
        })
        .map_err(|e| {
            PyRuntimeError::new_err(format!("Rust-Worker konnte nicht gestartet werden: {e}"))
        })?;

    // Eager readiness barrier: workbook metadata and filter validation. A named
    // sheet also resolves its headers here; all-sheet scans resolve each schema
    // during iteration. Release GIL while waiting.
    let (receiver, message) = py.detach(move || {
        let message = receiver.recv();
        (receiver, message)
    });
    match message {
        Ok(Message::Ready(headers)) => Ok(BatchIterator {
            receiver: Mutex::new(Some(receiver)),
            cancelled,
            headers,
            finished: false,
            statistics: None,
        }),
        Ok(Message::Failure(error)) => Err(PyValueError::new_err(error)),
        Ok(_) => Err(PyRuntimeError::new_err(
            "Rust-Worker meldete keine Kopfzeile",
        )),
        Err(_) => Err(PyRuntimeError::new_err(
            "Rust-Worker konnte nicht initialisieren",
        )),
    }
}

#[pyclass(module = "chooong.datasift.rust")]
struct EventIterator {
    inner: BatchIterator,
    values_only: bool,
}
#[pymethods]
impl EventIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }
    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Vec<String>>> {
        if self.inner.finished {
            return Ok(None);
        }
        loop {
            let receiver = self
                .inner
                .receiver
                .get_mut()
                .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))?
                .take()
                .ok_or_else(|| PyRuntimeError::new_err("Iterator geschlossen"))?;
            let (receiver, message) = py.detach(move || {
                let result = receiver.recv();
                (receiver, result)
            });
            *self
                .inner
                .receiver
                .get_mut()
                .map_err(|_| PyRuntimeError::new_err("Iterator-Lock beschädigt"))? = Some(receiver);
            match message {
                Ok(Message::Records(records)) => {
                    return records
                        .iter()
                        .map(|r| {
                            (if self.values_only {
                                serde_json::to_string(&r.values)
                            } else {
                                serde_json::to_string(r)
                            })
                            .map_err(|_| PyRuntimeError::new_err("Serialisierung fehlgeschlagen"))
                        })
                        .collect::<PyResult<Vec<_>>>()
                        .map(Some)
                }
                Ok(Message::Statistics(stats)) => self.inner.statistics = Some(stats),
                Ok(Message::Ready(_)) => (),
                Ok(Message::Done) => {
                    self.inner.close()?;
                    return Ok(None);
                }
                Ok(Message::Failure(error)) => {
                    self.inner.close()?;
                    return Err(PyRuntimeError::new_err(error));
                }
                _ => {
                    self.inner.close()?;
                    return Err(PyRuntimeError::new_err("Worker unerwartet beendet"));
                }
            }
        }
    }
    fn close(&mut self) -> PyResult<()> {
        self.inner.close()
    }
    fn statistics_json(&self) -> Option<String> {
        self.inner.statistics.clone()
    }
}
#[pyfunction(signature=(paths,filter_json,batch_size=1024,rejected=true))]
fn iter_events(
    py: Python<'_>,
    paths: Vec<String>,
    filter_json: String,
    batch_size: usize,
    rejected: bool,
) -> PyResult<EventIterator> {
    Ok(EventIterator {
        inner: make_iterator(py, paths, filter_json, batch_size, true, rejected)?,
        values_only: false,
    })
}

#[pyfunction(signature=(paths,filter_json,batch_size=1024))]
fn iter_many(
    py: Python<'_>,
    paths: Vec<String>,
    filter_json: String,
    batch_size: usize,
) -> PyResult<BatchIterator> {
    make_iterator(py, paths, filter_json, batch_size, false, false)
}
#[pyfunction(signature=(paths,filter_json,batch_size=1024))]
fn iter_json(
    py: Python<'_>,
    paths: Vec<String>,
    filter_json: String,
    batch_size: usize,
) -> PyResult<EventIterator> {
    Ok(EventIterator {
        inner: make_iterator(py, paths, filter_json, batch_size, true, false)?,
        values_only: true,
    })
}

#[pyfunction]
fn expand_inputs(paths: Vec<String>) -> PyResult<Vec<String>> {
    input::expand(&paths)
        .map(|paths| {
            paths
                .into_iter()
                .map(|p| p.to_string_lossy().into_owned())
                .collect()
        })
        .map_err(PyValueError::new_err)
}

#[pymodule]
fn rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<BatchIterator>()?;
    module.add_function(wrap_pyfunction!(expand_inputs, module)?)?;
    module.add_class::<EventIterator>()?;
    module.add_function(wrap_pyfunction!(iter_events, module)?)?;
    module.add_function(wrap_pyfunction!(output::export_native, module)?)?;
    module.add_function(wrap_pyfunction!(output::recover_export, module)?)?;
    module.add_function(wrap_pyfunction!(iter_many, module)?)?;
    module.add_function(wrap_pyfunction!(iter_json, module)?)?;
    module.add_function(wrap_pyfunction!(iter_batches_native, module)?)?;
    Ok(())
}
