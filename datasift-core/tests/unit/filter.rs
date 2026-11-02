use super::*;

fn heads() -> HashMap<String, usize> {
    [
        ("Kunde".into(), 0),
        ("Umsatz".into(), 1),
        ("Status".into(), 2),
    ]
    .into_iter()
    .collect()
}

#[test]
fn header_indices_are_one_based_and_ignore_empty_columns() {
    let mut row = vec![CellValue::Empty];
    row.extend((0..12).map(|_| CellValue::Text("Umsatz".into())));
    let (names, lookup) =
        headers_from_row(&row, &(1..=12).map(|i| format!("Umsatz_{i}")).collect()).unwrap();
    assert_eq!(names[0], ("Umsatz_1".into(), 1));
    assert_eq!(names[11], ("Umsatz_12".into(), 12));
    assert_eq!(lookup["Umsatz_10"], 10);
    assert!(!lookup.contains_key("Umsatz"));
}

#[test]
fn sheet_null_is_explicit_and_missing_sheet_is_rejected() {
    assert!(Config::parse(r#"{"where":{"column":"x","op":"eq","value":1}}"#).is_err());
    let config =
        Config::parse(r#"{"sheet":null,"where":{"column":"x","op":"eq","value":1}}"#).unwrap();
    assert!(config.sheet.is_none());
    assert!(config.required_columns.contains("x"));
}

#[test]
fn nested_logic() {
    let json = serde_json::json!({"all": [
        {"column":"Kunde", "op":"starts_with", "value":"ABC"},
        {"column":"Umsatz", "op":"gte", "value":1000},
        {"not": {"column":"Status", "op":"eq", "value":"Inaktiv"}}
    ]});
    let compiled = Expr::compile(&json, &heads()).unwrap();
    assert!(compiled.matches(&[
        CellValue::Text("ABC GmbH".into()),
        CellValue::Integer(1000),
        CellValue::Text("Aktiv".into())
    ]));
    assert!(!compiled.matches(&[
        CellValue::Text("ABC GmbH".into()),
        CellValue::Integer(999),
        CellValue::Text("Aktiv".into())
    ]));
}

#[test]
fn no_implicit_number_conversion() {
    let rule = serde_json::json!({"column":"Umsatz", "op":"eq", "value":1});
    let expr = Expr::compile(&rule, &heads()).unwrap();
    assert!(!expr.matches(&[CellValue::Empty, CellValue::Bool(true)]));
    assert!(!expr.matches(&[CellValue::Empty, CellValue::Text("1".into())]));
    assert!(expr.matches(&[CellValue::Empty, CellValue::Float(1.0)]));
}

#[test]
fn invalid_json_is_rejected() {
    assert!(Expr::compile(&serde_json::json!({"any":[]}), &heads()).is_err());
    assert!(Expr::compile(
        &serde_json::json!({"column":"no", "op":"eq", "value":1}),
        &heads()
    )
    .is_err());
    assert!(Expr::compile(
        &serde_json::json!({"column":"Kunde", "op":"regex", "value":"("}),
        &heads()
    )
    .is_err());
    assert!(Expr::compile(
        &serde_json::json!({"column":"Umsatz", "op":"gte", "value":"1000"}),
        &heads()
    )
    .is_err());
}

#[test]
fn invalid_configuration_is_rejected_before_scanning() {
    for (name, configuration) in [
        (
            "unknown field",
            serde_json::json!({"sheet":null,"typo":true}),
        ),
        ("empty sheet", serde_json::json!({"sheet":"  "})),
        (
            "empty sources",
            serde_json::json!({"sheet":null,"sources":[]}),
        ),
        (
            "invalid encoding",
            serde_json::json!({"sheet":null,"csv":{"encoding":"invalid-encoding"}}),
        ),
        (
            "identical delimiter and quote",
            serde_json::json!({"sheet":null,"csv":{"delimiter":",","quote":","}}),
        ),
        (
            "multibyte delimiter",
            serde_json::json!({"sheet":null,"csv":{"delimiter":"€"}}),
        ),
        (
            "empty selection",
            serde_json::json!({"sheet":null,"select":[]}),
        ),
        (
            "invalid projection regex",
            serde_json::json!({"sheet":null,"select":[{"pattern":"("}]}),
        ),
        (
            "invalid header depth",
            serde_json::json!({"sheet":null,"header":{"rows":33}}),
        ),
        (
            "unknown currency",
            serde_json::json!({"sheet":null,"types":{"Amount":{"type":"money","currency":"ZZZ"}}}),
        ),
        (
            "unsupported locale",
            serde_json::json!({"sheet":null,"types":{"Amount":{"type":"decimal","locale":"xx-XX"}}}),
        ),
        (
            "currency on nonmoney rule",
            serde_json::json!({"sheet":null,"types":{"Amount":{"type":"decimal","currency":"EUR"}}}),
        ),
        (
            "unconditional row rule",
            serde_json::json!({"sheet":null,"row_policy":{"rules":[{"classification":"comment"}]}}),
        ),
    ] {
        assert!(Config::parse(&configuration.to_string()).is_err(), "{name}");
    }
}

#[test]
fn source_bindings_reject_collisions_and_invalid_ranges() {
    for (name, source) in [
        (
            "duplicate name",
            serde_json::json!({"columns":[{"name":"ID","column":"A"},{"name":"ID","column":"B"}],"data_start_row":2}),
        ),
        (
            "reversed range",
            serde_json::json!({"columns":[{"name":"ID","column":"A"}],"data_start_row":4,"data_end_row":3}),
        ),
        (
            "skip outside range",
            serde_json::json!({"columns":[{"name":"ID","column":"A"}],"data_start_row":2,"data_end_row":4,"skip_rows":[5]}),
        ),
        (
            "header overlaps data",
            serde_json::json!({"first_column":"A","last_column":"B","header_start_row":2,"data_start_row":2}),
        ),
    ] {
        let configuration = serde_json::json!({"sheet":null,"source":source});
        assert!(Config::parse(&configuration.to_string()).is_err(), "{name}");
    }
}

#[test]
fn column_bindings_accept_only_the_excel_column_domain() {
    for (column, expected) in [("A", 0), ("Z", 25), ("AA", 26), ("XFD", 16383)] {
        assert_eq!(column_index(column).unwrap(), expected);
    }
    for column in ["", "a", "A1", "XFE", "AAAA", "Ä", " A"] {
        assert!(column_index(column).is_err(), "{column:?}");
    }
}

#[test]
fn explicit_source_can_bind_distinct_output_names_to_one_physical_column() {
    let config = Config::parse(r#"{"sheet":null,"source":{"columns":[{"name":"ID","column":"C"},{"name":"OriginalID","column":"C"}],"data_start_row":2}}"#).unwrap();
    let (headers, lookup) = config.source.unwrap().headers().unwrap();
    assert_eq!(headers, [("ID".into(), 2), ("OriginalID".into(), 2)]);
    assert_eq!(lookup["ID"], 2);
    assert_eq!(lookup["OriginalID"], 2);
}
