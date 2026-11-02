use super::CellValue;
use chrono::DateTime;
use rust_decimal::Decimal;
use serde_json::json;
use std::str::FromStr;

#[test]
fn exact_values_roundtrip_without_float_or_timezone_loss() {
    let amount = Decimal::from_str("1234.560000000000000000000001").unwrap();
    let timestamp = DateTime::parse_from_rfc3339("2026-11-01T12:00:01.123456789+05:30").unwrap();
    for value in [
        CellValue::Decimal(amount),
        CellValue::Money {
            amount,
            currency: "EUR".into(),
        },
        CellValue::Date(timestamp.date_naive()),
        CellValue::DateTime(timestamp.naive_local()),
        CellValue::ZonedDateTime(timestamp),
    ] {
        let encoded = value.json();
        assert_eq!(CellValue::from_json(&encoded).unwrap(), value);
    }
}

#[test]
fn raw_numeric_json_retains_digits_beyond_float_precision() {
    for raw in ["9007199254740993", "0.1234567890123456789012345678"] {
        assert_eq!(CellValue::NumberText(raw.into()).json().to_string(), raw);
        assert_eq!(
            CellValue::StyledNumber {
                raw: raw.into(),
                format: "0.00".into()
            }
            .json()
            .to_string(),
            raw
        );
    }
}

#[test]
fn defaults_reject_collections_and_unknown_tagged_values() {
    for value in [
        json!([1, 2]),
        json!({"type": "unknown", "value": "1"}),
        json!({"arbitrary": 1}),
    ] {
        assert!(CellValue::from_json(&value).is_err(), "{value}");
    }
}
