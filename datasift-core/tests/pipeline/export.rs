use super::*;
use crate::test_support::TestDir;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

#[test]
fn csv_pipeline_exports_typed_parquet_and_reject_originals() {
    let directory = TestDir::new();
    let root = directory.path();
    let input = root.join("input.csv");
    let matched = root.join("matched.parquet");
    let rejected = root.join("rejected.ndjson");
    fs::write(&input, "ID,Amount\na,10.500000000000000000000001\n,bad\n").unwrap();
    let mask = serde_json::json!({
        "sheet": null,
        "required": ["ID", "Amount"],
        "types": {"Amount": {"type": "money", "convert": true, "currency": "EUR"}}
    })
    .to_string();
    let stats = export(
        vec![input.to_string_lossy().into_owned()],
        mask,
        matched.to_string_lossy().into_owned(),
        Some(rejected.to_string_lossy().into_owned()),
        1,
    )
    .unwrap();
    let stats: Value = serde_json::from_str(&stats).unwrap();
    assert_eq!(stats["matched"], 1);
    assert_eq!(stats["rejected"], 1);
    let mut reader = ParquetRecordBatchReaderBuilder::try_new(File::open(&matched).unwrap())
        .unwrap()
        .build()
        .unwrap();
    let batch = reader.next().unwrap().unwrap();
    assert_eq!(batch.num_rows(), 1);
    let list = batch
        .column(5)
        .as_any()
        .downcast_ref::<ListArray>()
        .unwrap();
    let cells = list
        .values()
        .as_any()
        .downcast_ref::<StructArray>()
        .unwrap();
    let values = cells
        .column(5)
        .as_any()
        .downcast_ref::<Decimal256Array>()
        .unwrap();
    assert_eq!(
        values.value(1),
        decimal("10.500000000000000000000001").unwrap()
    );
    let rejected: Value = serde_json::from_str(&fs::read_to_string(&rejected).unwrap()).unwrap();
    assert_eq!(rejected["values"]["Amount"], "bad");
    assert_eq!(rejected["reasons"].as_array().unwrap().len(), 2);
}
#[test]
fn concurrent_writer_lock_is_exclusive() {
    let directory = TestDir::new();
    let root = directory.path();
    let path = root.join("output.ndjson");
    let guard = Transaction::new(std::slice::from_ref(&path)).unwrap();
    assert!(Transaction::new(std::slice::from_ref(&path)).is_err());
    drop(guard);
    let second = Transaction::new(std::slice::from_ref(&path)).unwrap();
    drop(second);
}

#[test]
fn encoding_failure_preserves_both_previous_outputs_and_removes_stages() {
    let directory = TestDir::new();
    let input = directory.join("input.csv");
    let matched = directory.join("matched.ndjson");
    let rejected = directory.join("rejected.ndjson");
    // Place the malformed byte after a full decoder buffer so rows have already
    // reached both output streams before the scan fails.
    let mut bytes = b"ID,Amount\na,1\n,bad\n".to_vec();
    for _ in 0..2048 {
        bytes.extend_from_slice(b"a,1\n");
    }
    bytes.extend_from_slice(b"broken,\xff\n");
    fs::write(&input, &bytes).unwrap();
    fs::write(&matched, b"previous matched\n").unwrap();
    fs::write(&rejected, b"previous rejected\n").unwrap();
    let mask = serde_json::json!({"sheet":null,"header":{"anchors":["ID","Amount"]},"required":["ID"],"types":{"Amount":{"type":"integer","convert":true}}}).to_string();
    let error = export(
        vec![input.to_string_lossy().into_owned()],
        mask,
        matched.to_string_lossy().into_owned(),
        Some(rejected.to_string_lossy().into_owned()),
        1,
    )
    .unwrap_err();
    assert!(error.contains("CSV"), "{error}");
    assert_eq!(fs::read(&matched).unwrap(), b"previous matched\n");
    assert_eq!(fs::read(&rejected).unwrap(), b"previous rejected\n");
    assert_eq!(fs::read(&input).unwrap(), bytes);
    let mut names = fs::read_dir(directory.path())
        .unwrap()
        .map(|entry| entry.unwrap().file_name().into_string().unwrap())
        .collect::<Vec<_>>();
    names.sort();
    assert_eq!(
        names,
        [
            ".matched.ndjson.datasift.lock",
            ".rejected.ndjson.datasift.lock",
            "input.csv",
            "matched.ndjson",
            "rejected.ndjson"
        ]
    );
}

#[test]
fn export_refuses_input_and_output_aliases_without_changing_bytes() {
    let directory = TestDir::new();
    let input = directory.join("input.csv");
    let output = directory.join("output.ndjson");
    fs::write(&input, b"ID,Amount\na,1\n").unwrap();
    fs::write(&output, b"previous\n").unwrap();
    let input = input.to_string_lossy().into_owned();
    let output = output.to_string_lossy().into_owned();
    for (matched, rejected) in [
        (input.clone(), None),
        (output.clone(), Some(input.clone())),
        (output.clone(), Some(output.clone())),
    ] {
        assert!(export(
            vec![input.clone()],
            r#"{"sheet":null}"#.into(),
            matched,
            rejected,
            1
        )
        .is_err());
        assert_eq!(fs::read(&input).unwrap(), b"ID,Amount\na,1\n");
        assert_eq!(fs::read(&output).unwrap(), b"previous\n");
    }
}

const WORKSHEET: &str = r#"<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="4">
<c r="C4" t="s"><v>0</v></c><c r="D4" t="s"><v>1</v></c>
<c r="G4" t="s"><v>0</v></c><c r="H4" t="s"><v>1</v></c>
</row>
<row r="5">
<c r="C5" t="s"><v>2</v></c><c r="D5"><v>10.500000000000000000000001</v></c>
<c r="G5" t="inlineStr"><is><t>Right</t></is></c><c r="H5"><f>1+1</f><v>12.50</v></c>
</row>
</sheetData></worksheet>"#;

const SHARED_STRINGS: &str = r#"<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<si><t>ID</t></si><si><t>Amount</t></si><si><r><t>A &amp; </t></r><r><t>B</t></r></si>
</sst>"#;

#[test]
fn xlsx_offset_tables_use_relationships_rich_strings_and_exact_cached_numbers() {
    let directory = TestDir::new();
    let input = directory.join("input.xlsx");
    let output = directory.join("matched.ndjson");
    crate::test_support::write_workbook(&input, WORKSHEET, SHARED_STRINGS);
    let mask = serde_json::json!({"sheet":"Data","header":{"anchors":["ID","Amount"]},"types":{"Amount":{"type":"decimal","convert":true}}}).to_string();
    let stats = export(
        vec![input.to_string_lossy().into_owned()],
        mask,
        output.to_string_lossy().into_owned(),
        None,
        1,
    )
    .unwrap();
    let stats: Value = serde_json::from_str(&stats).unwrap();
    assert_eq!(stats["matched"], 2);
    assert_eq!(stats["complete"], true);
    assert_eq!(stats["tables"].as_array().unwrap().len(), 2);
    let records = fs::read_to_string(output)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(
        records,
        [
            serde_json::json!({"ID":"A & B","Amount":{"type":"decimal","value":"10.500000000000000000000001"}}),
            serde_json::json!({"ID":"Right","Amount":{"type":"decimal","value":"12.50"}}),
        ]
    );
}

#[test]
fn truncated_xml_and_dtds_fail_without_replacing_previous_output() {
    for (worksheet, strings, expected_error) in [
        (
            WORKSHEET.trim_end_matches("</worksheet>"),
            SHARED_STRINGS,
            "incomplete",
        ),
        (
            WORKSHEET,
            SHARED_STRINGS.trim_end_matches("</sst>"),
            "incomplete",
        ),
        (
            "<!DOCTYPE worksheet [<!ENTITY x 'value'>]><worksheet/>",
            SHARED_STRINGS,
            "DTD",
        ),
    ] {
        let directory = TestDir::new();
        let input = directory.join("input.xlsx");
        let output = directory.join("matched.ndjson");
        crate::test_support::write_workbook(&input, worksheet, strings);
        fs::write(&output, b"previous\n").unwrap();
        let error = export(
            vec![input.to_string_lossy().into_owned()],
            r#"{"sheet":"Data","header":{"anchors":["ID","Amount"]}}"#.into(),
            output.to_string_lossy().into_owned(),
            None,
            1,
        )
        .unwrap_err();
        assert!(error.contains(expected_error), "{error}");
        assert_eq!(fs::read(&output).unwrap(), b"previous\n");
    }
}
