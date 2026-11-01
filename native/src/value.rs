//! Exact domain values; adapters retain numeric lexemes before explicit conversion.
use chrono::{NaiveDate, NaiveDateTime};
use rust_decimal::Decimal;
use serde::Serialize;
use serde_json::{json, Value};

#[derive(Clone, Debug, PartialEq)]
pub enum CellValue {
    Empty,
    Text(String),
    Integer(i64),
    Float(f64),
    Bool(bool),
    Decimal(Decimal),
    Money { amount: Decimal, currency: String },
    Date(NaiveDate),
    DateTime(NaiveDateTime),
    ZonedDateTime(chrono::DateTime<chrono::FixedOffset>),
    Currency(String),
    NumberText(String),
    IsoDate(String),
    StyledNumber { raw: String, format: String },
}

impl CellValue {
    pub fn source_type(&self) -> &'static str {
        match self {
            Self::Empty => "null",
            Self::Text(_) => "string",
            Self::IsoDate(s) => {
                if s.contains('T') {
                    "datetime"
                } else {
                    "date"
                }
            }
            Self::Integer(_) => "integer",
            Self::Float(_) => "float",
            Self::Bool(_) => "boolean",
            Self::Decimal(_) => "decimal",
            Self::Money { .. } => "money",
            Self::Date(_) => "date",
            Self::DateTime(_) | Self::ZonedDateTime(_) => "datetime",
            Self::Currency(_) => "currency_code",
            Self::NumberText(s) => {
                if s.parse::<i64>().is_ok() {
                    "integer"
                } else {
                    "float"
                }
            }
            Self::StyledNumber { raw, format } => match crate::rules::format_type(format) {
                Some(crate::rules::DataType::Date) => "date",
                Some(crate::rules::DataType::Datetime) => "datetime",
                _ => {
                    if raw.parse::<i64>().is_ok() {
                        "integer"
                    } else {
                        "float"
                    }
                }
            },
        }
    }
    pub fn empty(&self) -> bool {
        matches!(self, Self::Empty) || matches!(self, Self::Text(s) if s.is_empty())
    }

    pub fn json(&self) -> Value {
        match self {
            Self::Empty => Value::Null,
            Self::IsoDate(s) | Self::Text(s) | Self::Currency(s) => json!(s),
            Self::StyledNumber { raw: s, .. } | Self::NumberText(s) => {
                s.parse::<Value>().unwrap_or_else(|_| json!(s))
            }
            Self::Integer(n) => json!(n),
            Self::Float(n) => json!(n),
            Self::Bool(b) => json!(b),
            Self::Decimal(d) => json!({"type":"decimal", "value":d.to_string()}),
            Self::Money { amount, currency } => {
                json!({"type":"money", "amount":amount.to_string(), "currency":currency})
            }
            Self::Date(d) => json!({"type":"date", "value":d.to_string()}),
            Self::ZonedDateTime(d) => json!({"type":"datetime","value":d.to_rfc3339()}),
            Self::DateTime(d) => {
                json!({"type":"datetime", "value":d.format("%Y-%m-%dT%H:%M:%S%.f").to_string()})
            }
        }
    }

    pub fn from_json(value: &Value) -> Result<Self, String> {
        Ok(match value {
            Value::Null => Self::Empty,
            Value::Bool(b) => Self::Bool(*b),
            Value::String(s) => Self::Text(s.clone()),
            Value::Number(n) => {
                if let Some(n) = n.as_i64() {
                    Self::Integer(n)
                } else {
                    Self::Float(n.as_f64().ok_or("Ungültige Zahl")?)
                }
            }
            Value::Object(_) => crate::filter::exact_value(value)?,
            _ => return Err("Standardwert muss ein Skalar sein".into()),
        })
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct Reason {
    pub code: ReasonCode,
    pub column: Option<String>,
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ReasonCode {
    RequiredMissing,
    TypeMismatch,
    ConversionFailed,
    FilterNotMatched,
    SchemaMismatch,
}

#[derive(Clone, Debug, Serialize)]
pub struct Record {
    pub kind: RecordKind,
    pub file: String,
    pub sheet: String,
    pub table: String,
    pub row: u32,
    pub values: serde_json::Map<String, Value>,
    pub source_types: std::collections::BTreeMap<String, String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub reasons: Vec<Reason>,
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum RecordKind {
    Matched,
    Rejected,
}
