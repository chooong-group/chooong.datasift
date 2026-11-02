use super::*;

#[test]
fn cell_column_parser() {
    assert_eq!(column_from_cell_reference("A1").unwrap(), 0);
    assert_eq!(column_from_cell_reference("Z1").unwrap(), 25);
    assert_eq!(column_from_cell_reference("AA20").unwrap(), 26);
    assert_eq!(column_from_cell_reference("XFD1048576").unwrap(), 16_383);
    assert!(column_from_cell_reference("XFE1").is_err());
    assert!(column_from_cell_reference("A").is_err());
}

#[test]
fn references_and_paths() {
    let mut text = String::from("A");
    append_reference(&mut text, b"amp").unwrap();
    append_reference(&mut text, b"#x20AC").unwrap();
    assert_eq!(text, "A&€");
    assert_eq!(
        safe_target("xl/", "worksheets/sheet1.xml").unwrap(),
        "xl/worksheets/sheet1.xml"
    );
    assert_eq!(
        safe_target("xl/", "/xl/worksheets/sheet1.xml").unwrap(),
        "xl/worksheets/sheet1.xml"
    );
    assert!(safe_target("xl/", "../../secret.xml").is_err());
}

#[test]
fn number_and_date_caches() {
    assert_eq!(
        finish_cell("n", "123", "", &[]).unwrap(),
        CellValue::Integer(123)
    );
    assert_eq!(
        finish_cell("n", "1.25", "", &[]).unwrap(),
        CellValue::Float(1.25)
    );
    assert_eq!(
        finish_cell("b", "1", "", &[]).unwrap(),
        CellValue::Bool(true)
    );
    assert_eq!(
        finish_cell("d", "2026-10-31", "", &[]).unwrap(),
        CellValue::IsoDate("2026-10-31".into())
    );
}
