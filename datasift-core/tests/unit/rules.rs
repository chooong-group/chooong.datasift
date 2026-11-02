use super::*;
fn rule(target: DataType) -> TypeRule {
    TypeRule {
        target,
        convert: true,
        currency: None,
        locale: None,
        format: None,
    }
}
#[test]
fn decimal_precision_and_locale_fail_closed() {
    assert_eq!(
        decimal_text("1.234,560000000000000000000001", Some("de-DE"))
            .unwrap()
            .to_string(),
        "1234.560000000000000000000001"
    );
    assert!(decimal_text("12.34,56", Some("de-DE")).is_err());
    assert!(decimal_text("0.12345678901234567890123456789", None).is_err());
    assert!(convert(
        &CellValue::Text("0.1".into()),
        &rule(DataType::Float),
        false
    )
    .is_err());
    assert_eq!(
        convert(
            &CellValue::Text("0.5".into()),
            &rule(DataType::Float),
            false
        )
        .unwrap(),
        CellValue::Float(0.5)
    );
}
#[test]
fn excel_date_boundaries_and_fractional_precision() {
    assert_eq!(
        convert(&CellValue::Integer(59), &rule(DataType::Date), false).unwrap(),
        CellValue::Date(NaiveDate::from_ymd_opt(1900, 2, 28).unwrap())
    );
    assert!(convert(&CellValue::Integer(60), &rule(DataType::Date), false).is_err());
    assert_eq!(
        convert(&CellValue::Integer(61), &rule(DataType::Date), false).unwrap(),
        CellValue::Date(NaiveDate::from_ymd_opt(1900, 3, 1).unwrap())
    );
    assert_eq!(
        convert(&CellValue::Integer(0), &rule(DataType::Date), true).unwrap(),
        CellValue::Date(NaiveDate::from_ymd_opt(1904, 1, 1).unwrap())
    );
    assert!(convert(
        &CellValue::NumberText("1.5".into()),
        &rule(DataType::Date),
        true
    )
    .is_err());
}
#[test]
fn money_requires_currency_and_never_guesses_symbol() {
    assert!(convert(
        &CellValue::Text("$10.50".into()),
        &rule(DataType::Money),
        false
    )
    .is_err());
    let value = convert(
        &CellValue::Text("EUR 10.50".into()),
        &rule(DataType::Money),
        false,
    )
    .unwrap();
    assert_eq!(
        value,
        CellValue::Money {
            amount: decimal_text("10.50", None).unwrap(),
            currency: "EUR".into()
        }
    );
}

#[test]
fn integer_conversion_rejects_fractional_and_out_of_range_values() {
    let rule = rule(DataType::Integer);
    for (text, expected) in [
        ("-9223372036854775808", i64::MIN),
        ("9223372036854775807", i64::MAX),
        ("42.000", 42),
    ] {
        assert_eq!(
            convert(&CellValue::Text(text.into()), &rule, false).unwrap(),
            CellValue::Integer(expected)
        );
    }
    for text in ["-9223372036854775809", "9223372036854775808", "42.001"] {
        assert!(
            convert(&CellValue::Text(text.into()), &rule, false).is_err(),
            "{text}"
        );
    }
}

#[test]
fn strict_rules_require_native_types_without_text_coercion() {
    for (target, value) in [
        (DataType::Integer, CellValue::Text("42".into())),
        (DataType::Boolean, CellValue::Text("true".into())),
        (DataType::String, CellValue::Integer(42)),
    ] {
        let mut strict = rule(target);
        strict.convert = false;
        assert!(
            convert(&value, &strict, false).is_err(),
            "{target:?}: {value:?}"
        );
    }
}

#[test]
fn header_aliases_apply_after_unicode_and_whitespace_normalization() {
    let header = HeaderConfig {
        trim: true,
        lowercase: true,
        collapse_whitespace: true,
        unicode: Some("NFKC".into()),
        aliases: BTreeMap::from([("total amount".into(), "Amount".into())]),
        ..HeaderConfig::default()
    };
    assert_eq!(header.normalize("  Ｔｏｔａｌ\t AMOUNT\n"), "Amount");
    assert_eq!(header.normalize("  Customer\tID "), "customer id");
}

#[test]
fn money_conversion_rejects_conflicting_explicit_currency() {
    let mut configured = rule(DataType::Money);
    configured.currency = Some("EUR".into());
    assert!(convert(&CellValue::Text("USD 10.50".into()), &configured, false).is_err());
    assert!(convert(
        &CellValue::StyledNumber {
            raw: "10.50".into(),
            format: "USD 0.00".into()
        },
        &configured,
        false
    )
    .is_err());
}
