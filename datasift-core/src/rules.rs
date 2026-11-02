//! Validated native rule contract and lossless conversions.
use crate::value::CellValue;
use chrono::{Datelike, Duration, NaiveDate, NaiveDateTime, NaiveTime};
use rust_decimal::prelude::ToPrimitive;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::Value as Json;
use std::collections::{BTreeMap, HashSet};
use unicode_normalization::UnicodeNormalization;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DataType {
    String,
    Integer,
    Float,
    Number,
    Boolean,
    Null,
    Decimal,
    Date,
    Datetime,
    CurrencyCode,
    Money,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TypeRule {
    #[serde(rename = "type")]
    pub target: DataType,
    #[serde(default)]
    pub convert: bool,
    pub currency: Option<String>,
    pub locale: Option<String>,
    pub format: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(untagged)]
pub enum Selection {
    Name(String),
    Pattern { pattern: String },
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct HeaderConfig {
    pub anchors: Vec<String>,
    pub rows: usize,
    pub trim: bool,
    pub lowercase: bool,
    pub unicode: Option<String>,
    pub collapse_whitespace: bool,
    pub aliases: BTreeMap<String, String>,
    pub min_columns: usize,
    pub merged_fill: bool,
}
impl Default for HeaderConfig {
    fn default() -> Self {
        Self {
            anchors: vec![],
            rows: 1,
            trim: false,
            lowercase: false,
            unicode: None,
            collapse_whitespace: false,
            aliases: BTreeMap::new(),
            min_columns: 2,
            merged_fill: false,
        }
    }
}
impl HeaderConfig {
    pub fn normalize(&self, value: &str) -> String {
        let mut result = match self.unicode.as_deref() {
            Some("NFC") => value.nfc().collect(),
            Some("NFKC") => value.nfkc().collect(),
            _ => value.to_owned(),
        };
        if self.collapse_whitespace {
            result = result.split_whitespace().collect::<Vec<_>>().join(" ");
        }
        if self.trim {
            result = result.trim().to_owned();
        }
        if self.lowercase {
            result = result.to_lowercase();
        }
        self.aliases.get(&result).cloned().unwrap_or(result)
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[serde(rename_all = "snake_case")]
pub enum RowClass {
    Data,
    Header,
    RepeatedHeader,
    Empty,
    Comment,
    Total,
    Separator,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RowRule {
    pub classification: RowClass,
    #[serde(default)]
    pub rows: HashSet<u32>,
    #[serde(rename = "where")]
    pub predicate: Option<Json>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct RowPolicy {
    pub include: HashSet<RowClass>,
    pub exclude: HashSet<RowClass>,
    pub rules: Vec<RowRule>,
}
impl Default for RowPolicy {
    fn default() -> Self {
        Self {
            include: HashSet::from([RowClass::Data]),
            exclude: HashSet::new(),
            rules: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Default)]
#[serde(default)]
pub struct Rules {
    #[serde(rename = "where")]
    pub predicate: Option<Json>,
    pub select: Option<Vec<Selection>>,
    pub required: Vec<String>,
    pub defaults: BTreeMap<String, Json>,
    pub types: BTreeMap<String, TypeRule>,
    pub header: HeaderConfig,
    pub row_policy: RowPolicy,
}
impl Rules {
    pub fn validate(&self) -> Result<(), String> {
        for predicate in self.predicate.iter().chain(
            self.row_policy
                .rules
                .iter()
                .filter_map(|r| r.predicate.as_ref()),
        ) {
            let lookup = crate::filter::referenced_columns(predicate)
                .into_iter()
                .enumerate()
                .map(|(i, n)| (n, i))
                .collect();
            crate::filter::Expr::compile(predicate, &lookup)?;
        }
        if self
            .row_policy
            .rules
            .iter()
            .any(|r| r.rows.is_empty() && r.predicate.is_none())
        {
            return Err("Row rule requires rows or where".into());
        }

        if !(1..=32).contains(&self.header.rows)
            || !(1..=16384).contains(&self.header.min_columns)
            || self
                .header
                .unicode
                .as_deref()
                .is_some_and(|s| !matches!(s, "NFC" | "NFKC"))
        {
            return Err("Invalid header configuration".into());
        }
        if let Some(select) = &self.select {
            if select.is_empty() {
                return Err("select must not be empty".into());
            }
            for item in select {
                if let Selection::Pattern { pattern } = item {
                    crate::filter::compile_regex(pattern)?;
                }
            }
        }
        for value in self.defaults.values() {
            CellValue::from_json(value)?;
        }
        for rule in self.types.values() {
            if rule
                .currency
                .as_deref()
                .is_some_and(|c| iso_currency::Currency::from_code(c).is_none())
            {
                return Err("Unknown ISO-4217 code".into());
            }
            if rule
                .locale
                .as_deref()
                .is_some_and(|l| !matches!(l, "de-DE" | "en-US"))
            {
                return Err("Unsupported locale".into());
            }
            if rule.currency.is_some() && rule.target != DataType::Money {
                return Err("currency requires money".into());
            }
            if rule.format.is_some() && !matches!(rule.target, DataType::Date | DataType::Datetime)
            {
                return Err("format requires date/datetime".into());
            }
        }
        Ok(())
    }
}

pub fn format_type(format: &str) -> Option<DataType> {
    let mut code = String::new();
    let mut quoted = false;
    let mut escaped = false;
    for c in format.chars() {
        if escaped {
            escaped = false;
            continue;
        }
        if c == '\\' {
            escaped = true;
            continue;
        }
        if c == '"' {
            quoted = !quoted;
            continue;
        }
        if !quoted {
            code.push(c.to_ascii_lowercase());
        }
    }
    if code.contains('y') || code.contains('d') {
        Some(if code.contains('h') || code.contains('s') {
            DataType::Datetime
        } else {
            DataType::Date
        })
    } else if code.contains('h') && code.contains('s') {
        Some(DataType::Datetime)
    } else {
        None
    }
}
pub fn is_type(value: &CellValue, target: DataType) -> bool {
    if let CellValue::IsoDate(raw) = value {
        return target
            == if raw.contains('T') {
                DataType::Datetime
            } else {
                DataType::Date
            };
    }
    if let CellValue::StyledNumber { raw, format } = value {
        if let Some(actual) = format_type(format) {
            return actual == target;
        }
        return is_type(&CellValue::NumberText(raw.clone()), target);
    }
    match target {
        DataType::String => matches!(value, CellValue::Text(_)),
        DataType::Integer => {
            matches!(value, CellValue::Integer(_))
                || matches!(value,CellValue::NumberText(s) if s.parse::<i64>().is_ok())
        }
        DataType::Float => {
            matches!(value, CellValue::Float(_))
                || matches!(value,CellValue::NumberText(s) if s.parse::<i64>().is_err() && s.parse::<f64>().is_ok())
        }
        DataType::Number => matches!(
            value,
            CellValue::Integer(_)
                | CellValue::Float(_)
                | CellValue::Decimal(_)
                | CellValue::NumberText(_)
        ),
        DataType::Boolean => matches!(value, CellValue::Bool(_)),
        DataType::Null => matches!(value, CellValue::Empty),
        DataType::Decimal => matches!(value, CellValue::Decimal(_)),
        DataType::Date => matches!(value, CellValue::Date(_)),
        DataType::Datetime => matches!(value, CellValue::DateTime(_) | CellValue::ZonedDateTime(_)),
        DataType::Money => matches!(value, CellValue::Money { .. }),
        DataType::CurrencyCode => {
            matches!(value, CellValue::Currency(_))
                || matches!(value,CellValue::Text(s) if iso_currency::Currency::from_code(s).is_some())
        }
    }
}

pub fn decimal_text(text: &str, locale: Option<&str>) -> Result<Decimal, String> {
    let input = text.trim();
    let normalized;
    let number = if let Some(locale) = locale {
        let (group, point) = if locale == "de-DE" {
            ('.', ',')
        } else {
            (',', '.')
        };
        let pieces: Vec<_> = input.split(point).collect();
        if pieces.len() > 2 || pieces.get(1).is_some_and(|s| s.contains(group)) {
            return Err("Ambiguous number format".into());
        }
        let integer = pieces[0].trim_start_matches(['+', '-']);
        if integer.contains(group) {
            let groups: Vec<_> = integer.split(group).collect();
            if groups[0].is_empty()
                || groups[0].len() > 3
                || groups[1..]
                    .iter()
                    .any(|s| s.len() != 3 || !s.bytes().all(|b| b.is_ascii_digit()))
            {
                return Err("Invalid thousands groups".into());
            }
        }
        normalized = input.replace(group, "").replace(point, ".");
        normalized.as_str()
    } else {
        input
    };
    Decimal::from_str_exact(number)
        .or_else(|_| Decimal::from_scientific(number))
        .map_err(|_| "Decimal value outside the exact range".into())
}

fn numeric_text(value: &CellValue) -> Option<String> {
    match value {
        CellValue::StyledNumber { raw: s, .. } | CellValue::Text(s) | CellValue::NumberText(s) => {
            Some(s.clone())
        }
        CellValue::Integer(n) => Some(n.to_string()),
        CellValue::Float(n) => Some(n.to_string()),
        CellValue::Decimal(n) => Some(n.to_string()),
        _ => None,
    }
}

pub fn convert(value: &CellValue, rule: &TypeRule, date1904: bool) -> Result<CellValue, String> {
    if let CellValue::IsoDate(raw) = value {
        let mut native = rule.clone();
        native.convert = rule.convert || is_type(value, rule.target);
        return convert(&CellValue::Text(raw.clone()), &native, date1904);
    }
    if let CellValue::StyledNumber { raw, format } = value {
        let mut native_rule = rule.clone();
        native_rule.locale = None;
        if format_type(format) == Some(rule.target) {
            native_rule.convert = true;
        }
        if rule.target == DataType::Money {
            let code = format
                .split(|c: char| !c.is_ascii_uppercase())
                .find(|s| iso_currency::Currency::from_code(s).is_some());
            if let Some(code) = code {
                if rule.currency.as_deref().is_some_and(|c| c != code) {
                    return Err("Conflicting currency formatting".into());
                }
                native_rule.currency = Some(code.to_owned());
                native_rule.convert = true;
            } else if format == "currency" && rule.currency.is_some() {
                native_rule.convert = true;
            } else if let Some(currency) = rule
                .currency
                .as_deref()
                .and_then(iso_currency::Currency::from_code)
            {
                if format.contains(&currency.symbol().to_string()) {
                    native_rule.convert = true;
                }
            }
        }
        return convert(&CellValue::NumberText(raw.clone()), &native_rule, date1904);
    }
    if matches!(
        value,
        CellValue::NumberText(_) | CellValue::Integer(_) | CellValue::Float(_)
    ) && rule.locale.is_some()
    {
        let mut native_rule = rule.clone();
        native_rule.locale = None;
        return convert(value, &native_rule, date1904);
    }
    if is_type(value, rule.target) {
        if let CellValue::NumberText(raw) = value {
            return CellValue::number(raw);
        }
        return Ok(value.clone());
    }
    if value.empty() && rule.target != DataType::Null {
        return Ok(CellValue::Empty);
    }
    if !rule.convert {
        return Err("Type mismatch".into());
    }
    let raw = numeric_text(value).ok_or("Value cannot be converted")?;
    let text = raw.trim();
    Ok(match rule.target {
        DataType::String => CellValue::Text(raw),
        DataType::Integer => {
            let d = decimal_text(text, rule.locale.as_deref())?;
            if !d.fract().is_zero() {
                return Err("Lossy integer conversion".into());
            }
            CellValue::Integer(d.to_i64().ok_or("Integer outside i64 range")?)
        }
        DataType::Float | DataType::Number => {
            let d = decimal_text(text, rule.locale.as_deref())?;
            let f = d.to_f64().ok_or("Invalid float")?;
            if Decimal::from_f64_retain(f) != Some(d) {
                return Err("Float conversion is not exact".into());
            }
            CellValue::Float(f)
        }
        DataType::Boolean => match text {
            "true" => CellValue::Bool(true),
            "false" => CellValue::Bool(false),
            _ => return Err("Boolean expects true/false".into()),
        },
        DataType::Decimal => CellValue::Decimal(decimal_text(text, rule.locale.as_deref())?),
        DataType::CurrencyCode => {
            if iso_currency::Currency::from_code(text).is_none() {
                return Err("Unknown ISO-4217 code".into());
            }
            CellValue::Currency(text.to_owned())
        }
        DataType::Money => {
            let mut amount = text.to_owned();
            let mut code = rule.currency.clone();
            let words: Vec<_> = text.split_whitespace().collect();
            for word in &words {
                if iso_currency::Currency::from_code(word).is_some() {
                    if code.as_deref().is_some_and(|c| c != *word) {
                        return Err("Conflicting currency".into());
                    }
                    code = Some((*word).to_owned());
                    amount = amount.replace(word, "");
                }
            }
            let currency =
                code.ok_or("Currency must be configured unambiguously or supplied as an ISO code")?;
            // Symbols never establish currency; a configured code is authoritative.
            if rule.currency.is_some() {
                let symbol = iso_currency::Currency::from_code(&currency)
                    .ok_or("Unknown currency")?
                    .symbol()
                    .to_string();
                amount = amount.replace(&symbol, "");
            }
            CellValue::Money {
                amount: decimal_text(amount.trim(), rule.locale.as_deref())?,
                currency,
            }
        }
        DataType::Date | DataType::Datetime => {
            if rule.target == DataType::Datetime && rule.format.is_none() {
                if let Ok(zoned) = chrono::DateTime::parse_from_rfc3339(text) {
                    if !(1..=9999).contains(&zoned.year()) {
                        return Err("Date outside 0001..9999".into());
                    }
                    return Ok(CellValue::ZonedDateTime(zoned));
                }
            }
            let datetime = if matches!(
                value,
                CellValue::NumberText(_) | CellValue::Integer(_) | CellValue::Float(_)
            ) {
                let serial = decimal_text(text, None)?;
                let days = serial.floor().to_i64().ok_or("Date out of range")?;
                if !date1904 && days == 60 {
                    return Err("Excel 1900-02-29 does not exist".into());
                }
                let base = NaiveDate::from_ymd_opt(
                    if date1904 { 1904 } else { 1899 },
                    if date1904 { 1 } else { 12 },
                    if date1904 { 1 } else { 31 },
                )
                .ok_or("Invalid base date")?;
                let days = if !date1904 && days > 60 {
                    days - 1
                } else {
                    days
                };
                let date = base
                    .checked_add_signed(Duration::try_days(days).ok_or("Date out of range")?)
                    .ok_or("Date out of range")?;
                let nanos = (serial - serial.floor()) * Decimal::from(86_400_000_000_000_i64);
                if !nanos.fract().is_zero() {
                    return Err("Date loses nanosecond precision".into());
                }
                date.and_time(NaiveTime::MIN)
                    .checked_add_signed(Duration::nanoseconds(
                        nanos.to_i64().ok_or("Time out of range")?,
                    ))
                    .ok_or("Time out of range")?
            } else if rule.target == DataType::Date {
                NaiveDate::parse_from_str(text, rule.format.as_deref().unwrap_or("%Y-%m-%d"))
                    .map_err(|_| "Invalid date")?
                    .and_time(NaiveTime::MIN)
            } else {
                NaiveDateTime::parse_from_str(
                    text,
                    rule.format.as_deref().unwrap_or("%Y-%m-%dT%H:%M:%S%.f"),
                )
                .map_err(|_| "Invalid date/time")?
            };
            if !(1..=9999).contains(&datetime.year()) {
                return Err("Date outside 0001..9999".into());
            }
            if rule.target == DataType::Date {
                if datetime.time() != NaiveTime::MIN {
                    return Err("date would lose the time of day".into());
                }
                CellValue::Date(datetime.date())
            } else {
                CellValue::DateTime(datetime)
            }
        }
        DataType::Null => return Err("Nonempty value is not null".into()),
    })
}

#[cfg(test)]
#[path = "../tests/unit/rules.rs"]
mod tests;
