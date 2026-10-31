//! Rust/PyO3 bridge: the worker never constructs Python objects for rejected rows.
mod filter;
mod xlsx;

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{sync_channel, Receiver};
use std::sync::Arc;
use std::thread;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use filter::Config;
use xlsx::CellValue;

pub(crate) enum Message {
    Ready(Vec<(String, usize)>),
    Batch(Vec<Vec<CellValue>>),
    Done,
    Failure(String),
}

#[pyclass(module = "rust_xlsx_filter._rust")]
pub struct BatchIterator {
    receiver: Option<Receiver<Message>>,
    cancelled: Arc<AtomicBool>,
    headers: Vec<(String, usize)>,
    finished: bool,
}

#[pymethods]
impl BatchIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Vec<Py<PyDict>>>> {
        if self.finished { return Ok(None); }
        let receiver = self.receiver.take().ok_or_else(|| PyRuntimeError::new_err("Iterator geschlossen"))?;
        // Receiver is Send (but not Sync); move ownership into/out of the GIL-free closure.
        let (receiver, message) = py.detach(move || {
            let message = receiver.recv();
            (receiver, message)
        });
        self.receiver = Some(receiver);

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
                        match row.get(*index).unwrap_or(&CellValue::Empty) {
                            CellValue::Empty => object.set_item(name.as_str(), py.None())?,
                            CellValue::Text(value) => object.set_item(name.as_str(), value.as_str())?,
                            CellValue::Integer(value) => object.set_item(name.as_str(), *value)?,
                            CellValue::Float(value) => object.set_item(name.as_str(), *value)?,
                            CellValue::Bool(value) => object.set_item(name.as_str(), *value)?,
                        }
                    }
                    output.push(object.unbind());
                }
                Ok(Some(output))
            }
            Message::Done => {
                self.finished = true;
                self.receiver.take();
                Ok(None)
            }
            Message::Failure(message) => {
                self.finished = true;
                self.receiver.take();
                Err(PyRuntimeError::new_err(message))
            }
            Message::Ready(_) => Err(PyRuntimeError::new_err("Ungültiger Worker-Status")),
        }
    }

    fn close(&mut self) {
        self.cancelled.store(true, Ordering::Relaxed);
        self.receiver.take();
        self.finished = true;
    }
}

impl Drop for BatchIterator {
    fn drop(&mut self) {
        self.cancelled.store(true, Ordering::Relaxed);
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
        return Err(PyValueError::new_err("batch_size muss zwischen 1 und 65536 liegen"));
    }
    // Validate structural JSON immediately, before creating a worker.
    let config = Config::parse(&filter_json).map_err(PyValueError::new_err)?;
    let cancelled = Arc::new(AtomicBool::new(false));
    let worker_cancelled = Arc::clone(&cancelled);
    // One ready/batch in flight plus two buffered batches: memory bound by consumer speed.
    let (sender, receiver) = sync_channel::<Message>(2);
    let path = PathBuf::from(xlsx_path);

    thread::Builder::new()
        .name("xlsx-json-filter".into())
        .spawn(move || {
            let outcome = xlsx::scan(&path, &config, batch_size, &sender, &worker_cancelled);
            if !worker_cancelled.load(Ordering::Relaxed) {
                match outcome {
                    Ok(()) => { let _ = sender.send(Message::Done); }
                    Err(error) => { let _ = sender.send(Message::Failure(error)); }
                }
            }
        })
        .map_err(|e| PyRuntimeError::new_err(format!("Rust-Worker konnte nicht gestartet werden: {e}")))?;

    // Eager readiness barrier: validate sheet, header, unknown columns and regex
    // before the Python API returns an iterator. Release GIL while waiting.
    let (receiver, message) = py.detach(move || {
        let message = receiver.recv();
        (receiver, message)
    });
    match message {
        Ok(Message::Ready(headers)) => Ok(BatchIterator {
            receiver: Some(receiver), cancelled, headers, finished: false,
        }),
        Ok(Message::Failure(error)) => Err(PyValueError::new_err(error)),
        Ok(_) => Err(PyRuntimeError::new_err("Rust-Worker meldete keine Kopfzeile")),
        Err(_) => Err(PyRuntimeError::new_err("Rust-Worker konnte nicht initialisieren")),
    }
}

#[pymodule]
fn _rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<BatchIterator>()?;
    module.add_function(wrap_pyfunction!(iter_batches_native, module)?)?;
    Ok(())
}
