use super::{Discovery, Event};
use crate::rules::HeaderConfig;
use crate::value::CellValue;

fn text(value: &str) -> CellValue {
    CellValue::Text(value.into())
}

#[test]
fn adjacent_regions_need_independent_structural_confirmation() {
    let header = HeaderConfig::default();
    let mut discovery = Discovery::default();
    assert!(discovery
        .observe(
            4,
            &[
                text("ID"),
                text("Amount"),
                CellValue::Empty,
                text("Name"),
                text("Country")
            ],
            &header
        )
        .is_empty());
    let events = discovery.observe(
        5,
        &[
            text("a"),
            CellValue::Integer(10),
            CellValue::Empty,
            text("Alice"),
            text("DE"),
        ],
        &header,
    );
    assert_eq!(events.len(), 2);
    assert!(
        matches!(&events[0], Event::Header { number: 4, first: 0, raw, repeated: false } if raw == &[text("ID"), text("Amount")])
    );
    assert!(
        matches!(&events[1], Event::Ambiguous { first: 3, last: 4, start: 4, pending } if pending == &[(4, vec![text("Name"), text("Country")])])
    );
}

#[test]
fn nonfinite_text_is_not_numeric_evidence() {
    for value in ["NaN", "inf", "-inf", "1e999"] {
        let mut discovery = Discovery::default();
        let header = HeaderConfig::default();
        discovery.observe(1, &[text("ID"), text("Amount")], &header);
        let events = discovery.observe(2, &[text("a"), text(value)], &header);
        assert!(
            matches!(events.as_slice(), [Event::Ambiguous { .. }]),
            "{value}"
        );
    }
}

#[test]
fn eof_reports_unconfirmed_headers_once() {
    let mut discovery = Discovery::default();
    discovery.observe(7, &[text("ID"), text("Amount")], &HeaderConfig::default());
    let events = discovery.finish();
    assert!(
        matches!(events.as_slice(), [Event::Ambiguous { first: 0, last: 1, start: 7, pending }] if pending.len() == 1)
    );
    assert!(discovery.finish().is_empty());
}

#[test]
fn repeated_headers_use_configured_normalization() {
    let header = HeaderConfig {
        trim: true,
        lowercase: true,
        ..HeaderConfig::default()
    };
    let mut discovery = Discovery::default();
    discovery.observe(1, &[text(" ID "), text("Amount")], &header);
    let events = discovery.observe(2, &[text("a"), CellValue::Integer(1)], &header);
    assert!(matches!(
        events.as_slice(),
        [Event::Header {
            repeated: false,
            ..
        }]
    ));
    let events = discovery.observe(3, &[text("id"), text(" AMOUNT ")], &header);
    assert!(matches!(
        events.as_slice(),
        [Event::Header {
            number: 3,
            repeated: true,
            ..
        }]
    ));
}

#[test]
fn multiline_headers_are_joined_only_after_all_rows_and_data_evidence() {
    let header = HeaderConfig {
        rows: 2,
        ..HeaderConfig::default()
    };
    let mut discovery = Discovery::default();
    discovery.observe(4, &[text("Customer"), text("Net")], &header);
    assert!(discovery
        .observe(5, &[text("ID"), text("Amount")], &header)
        .is_empty());
    let events = discovery.observe(6, &[text("a"), CellValue::Integer(10)], &header);
    assert!(
        matches!(events.as_slice(), [Event::Header { number: 5, first: 0, raw, repeated: false }] if raw == &[text("Customer ID"), text("Net Amount")])
    );
}

#[test]
fn blank_rows_close_regions_so_later_tables_can_be_discovered() {
    let header = HeaderConfig::default();
    let mut discovery = Discovery::default();
    discovery.observe(1, &[text("ID"), text("Amount")], &header);
    discovery.observe(2, &[text("a"), CellValue::Integer(1)], &header);
    assert!(matches!(
        discovery.observe(3, &[], &header).as_slice(),
        [Event::Close { first: 0, last: 1 }]
    ));
    discovery.observe(4, &[text("Code"), text("Value")], &header);
    assert!(matches!(
        discovery
            .observe(5, &[text("b"), CellValue::Integer(2)], &header)
            .as_slice(),
        [Event::Header {
            number: 4,
            repeated: false,
            ..
        }]
    ));
}
