use super::{expand, scan};
use crate::filter::Config;
use crate::test_support::TestDir;
use crate::value::Record;
use crate::Message;
use serde_json::{json, Value};
use std::fs;
use std::sync::atomic::AtomicBool;
use std::sync::mpsc::sync_channel;
use std::sync::Arc;

struct ScanResult {
    outcome: Result<(), String>,
    records: Vec<Record>,
    batch_sizes: Vec<usize>,
    statistics: Option<Value>,
}

fn run_scan(paths: &[String], config: &Config, batch_size: usize) -> ScanResult {
    // Drain the real bounded channel concurrently; an undrained channel would
    // hide backpressure bugs by requiring an arbitrary fixture-sized capacity.
    std::thread::scope(|scope| {
        let (sender, receiver) = sync_channel(2);
        let cancelled = Arc::new(AtomicBool::new(false));
        let worker =
            scope.spawn(move || scan(paths, config, batch_size, &sender, &cancelled, true, true));
        let mut records = Vec::new();
        let mut batch_sizes = Vec::new();
        let mut statistics = None;
        for message in receiver {
            match message {
                Message::Ready(_) => (),
                Message::Records(batch) => {
                    batch_sizes.push(batch.len());
                    records.extend(batch);
                }
                Message::Statistics(value) => {
                    assert!(statistics.is_none(), "Statistics must be emitted once");
                    statistics = Some(serde_json::from_str(&value).unwrap());
                }
                _ => panic!("Unexpected message from event scan"),
            }
        }
        ScanResult {
            outcome: worker.join().unwrap(),
            records,
            batch_sizes,
            statistics,
        }
    })
}

#[test]
fn globs_and_explicit_paths_are_sorted_and_deduplicated() {
    let directory = TestDir::new();
    let first = directory.join("a.csv");
    let second = directory.join("b.csv");
    fs::write(&first, b"").unwrap();
    fs::write(&second, b"").unwrap();
    fs::write(directory.join("ignored.txt"), b"").unwrap();
    let inputs = vec![
        second.to_string_lossy().into_owned(),
        directory.join("*.csv").to_string_lossy().into_owned(),
        first.to_string_lossy().into_owned(),
    ];
    assert_eq!(expand(&inputs).unwrap(), vec![first, second]);
}

#[test]
fn empty_inputs_invalid_globs_and_unmatched_globs_are_rejected() {
    let directory = TestDir::new();
    for inputs in [
        vec![],
        vec!["[".into()],
        vec![directory.join("*.csv").to_string_lossy().into_owned()],
    ] {
        assert!(expand(&inputs).is_err(), "{inputs:?}");
    }
}

#[test]
fn csv_quoting_multiline_cells_and_final_batch_preserve_record_order() {
    let directory = TestDir::new();
    let input = directory.join("input.csv");
    fs::write(
        &input,
        "ID,Note\na,\"first, second\"\nb,\"line one\nline two\"\nc,\"say \"\"hello\"\"\"\n",
    )
    .unwrap();
    let config = Config::parse(r#"{"sheet":null,"header":{"anchors":["ID","Note"]}}"#).unwrap();
    let paths = vec![input.to_string_lossy().into_owned()];
    for batch_size in [1, 2, 1024] {
        let result = run_scan(&paths, &config, batch_size);
        result.outcome.unwrap();
        assert!(result
            .batch_sizes
            .iter()
            .all(|size| *size > 0 && *size <= batch_size));
        assert_eq!(
            result.records.iter().map(|r| r.row).collect::<Vec<_>>(),
            [2, 3, 4]
        );
        assert_eq!(
            result
                .records
                .iter()
                .map(|r| r.values["Note"].clone())
                .collect::<Vec<_>>(),
            [
                json!("first, second"),
                json!("line one\nline two"),
                json!("say \"hello\"")
            ]
        );
        let statistics = result.statistics.unwrap();
        assert_eq!(statistics["matched"], 3);
        assert_eq!(statistics["rejected"], 0);
        assert_eq!(statistics["complete"], true);
    }
}

#[test]
fn continue_policy_yields_valid_files_but_reports_incomplete_scan() {
    let directory = TestDir::new();
    let invalid = directory.join("00.unsupported");
    let valid = directory.join("10.csv");
    fs::write(&valid, "ID,Amount\na,1\n").unwrap();
    let paths = vec![
        valid.to_string_lossy().into_owned(),
        invalid.to_string_lossy().into_owned(),
    ];
    let config = Config::parse(
        r#"{"sheet":null,"header":{"anchors":["ID","Amount"]},"file_errors":"continue"}"#,
    )
    .unwrap();
    let result = run_scan(&paths, &config, 1);
    assert!(result.outcome.is_err());
    assert_eq!(result.records.len(), 1);
    assert_eq!(result.records[0].file, valid.to_string_lossy());
    assert_eq!(result.records[0].values["ID"], "a");
    let stats = result.statistics.unwrap();
    assert_eq!(stats["complete"], false);
    assert_eq!(stats["matched"], 1);
    assert_eq!(stats["diagnostics"].as_array().unwrap().len(), 1);
    assert_eq!(stats["diagnostics"][0]["code"], "FILE_ERROR");
    assert_eq!(
        stats["diagnostics"][0]["file"],
        invalid.to_string_lossy().as_ref()
    );
}

#[test]
fn default_failure_policy_stops_before_later_files() {
    let directory = TestDir::new();
    let valid = directory.join("10.csv");
    fs::write(&valid, "ID,Amount\na,1\n").unwrap();
    let paths = vec![
        directory
            .join("00.unsupported")
            .to_string_lossy()
            .into_owned(),
        valid.to_string_lossy().into_owned(),
    ];
    let config = Config::parse(r#"{"sheet":null,"header":{"anchors":["ID","Amount"]}}"#).unwrap();
    let result = run_scan(&paths, &config, 1);
    assert!(result.outcome.is_err());
    assert!(result.records.is_empty());
    assert!(result.statistics.is_none());
}

#[test]
fn cancelled_scan_does_not_open_inputs_or_emit_records() {
    let (sender, receiver) = sync_channel(2);
    let config = Config::parse(r#"{"sheet":null}"#).unwrap();
    scan(
        &["missing.csv".into()],
        &config,
        1,
        &sender,
        &Arc::new(AtomicBool::new(true)),
        true,
        true,
    )
    .unwrap();
    drop(sender);
    let messages = receiver.into_iter().collect::<Vec<_>>();
    assert!(matches!(messages.as_slice(), [Message::Ready(_)]));
}
