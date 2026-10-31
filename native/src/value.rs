//! Domain values, independent of XLSX and Python adapters.
#[derive(Clone, Debug, PartialEq)]
pub enum CellValue {
    Empty,
    Text(String),
    Integer(i64),
    Float(f64),
    Bool(bool),
}
