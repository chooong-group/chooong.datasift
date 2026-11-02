use super::*;
use crate::test_support::TestDir;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

#[test]
fn parquet_roundtrip_preserves_exact_and_temporal_values() {
    let directory = TestDir::new();
    let path = directory.join("exact.parquet");
    let record = Record {
        kind: RecordKind::Matched,
        file: "synthetic.csv".into(),
        sheet: "csv".into(),
        table: "one".into(),
        row: 2,
        values: serde_json::from_value(serde_json::json!({
            "amount": {"type": "money", "amount": "1234.560000000000000000000001", "currency": "EUR"},
            "date": {"type": "date", "value": "2026-11-01"},
            "time": {"type": "datetime", "value": "2026-11-01T12:00:01.123456789"}
        })).unwrap(),
        reasons: vec![],
        source_types: Default::default(),
    };
    let mut writer = Writer::new(&path, true, false).unwrap();
    writer.write(&[record]).unwrap();
    writer.finish().unwrap();
    let mut reader = ParquetRecordBatchReaderBuilder::try_new(File::open(&path).unwrap())
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
    let values = list
        .values()
        .as_any()
        .downcast_ref::<StructArray>()
        .unwrap();
    let decimal_values = values
        .column(5)
        .as_any()
        .downcast_ref::<Decimal256Array>()
        .unwrap();
    assert_eq!(
        decimal_values.value(0),
        decimal("1234.560000000000000000000001").unwrap()
    );
    let remainder = values
        .column(9)
        .as_any()
        .downcast_ref::<Int32Array>()
        .unwrap();
    assert_eq!(remainder.value(2), 789);
}
