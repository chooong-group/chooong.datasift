//! JSON expressions compiled once against the header positions.
use std::collections::{HashMap, HashSet};

use regex::{Regex, RegexBuilder};
use serde::Deserialize;
use serde_json::Value as Json;

use crate::value::CellValue;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    #[serde(deserialize_with = "Option::<String>::deserialize")]
    pub sheet: Option<String>,
    #[serde(default = "default_header_row")]
    pub header_row: u32,
    #[serde(rename = "where")]
    pub predicate: Json,
    pub source: Option<TableSource>,
    #[serde(skip)]
    pub required_columns: HashSet<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ColumnBinding {
    name: String,
    column: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TableSource {
    columns: Vec<ColumnBinding>,
    pub data_start_row: u32,
    pub data_end_row: Option<u32>,
    #[serde(default)]
    pub skip_rows: HashSet<u32>,
}

impl TableSource {
    pub fn contains_row(&self, row: u32) -> bool {
        row >= self.data_start_row
            && self.data_end_row.is_none_or(|end| row <= end)
            && !self.skip_rows.contains(&row)
    }

    pub fn headers(&self) -> Result<HeaderLookup, String> {
        let mut names = HashSet::new();
        let columns = self
            .columns
            .iter()
            .map(|binding| {
                if binding.name.trim().is_empty() || !names.insert(binding.name.clone()) {
                    return Err(
                        "Ausgabenamen in source.columns müssen nichtleer und eindeutig sein".into(),
                    );
                }
                Ok((binding.name.clone(), column_index(&binding.column)?))
            })
            .collect::<Result<Vec<_>, String>>()?;
        let lookup = columns
            .iter()
            .map(|(name, index)| (name.clone(), *index))
            .collect();
        Ok((columns, lookup))
    }

    fn validate(&self) -> Result<(), String> {
        let end = self.data_end_row.unwrap_or(1_048_576);
        if !(1..=1_048_576).contains(&self.data_start_row)
            || end < self.data_start_row
            || end > 1_048_576
            || self.columns.is_empty()
            || self.columns.len() > 16_384
            || self
                .skip_rows
                .iter()
                .any(|row| *row < self.data_start_row || *row > end)
        {
            return Err("Ungültiger Datenbereich in source".into());
        }
        self.headers()?;
        Ok(())
    }
}

pub fn column_index(column: &str) -> Result<usize, String> {
    if column.is_empty() || column.len() > 3 || !column.bytes().all(|b| b.is_ascii_uppercase()) {
        return Err("Excel-Spalte muss zwischen A und XFD liegen".into());
    }
    let mut number = 0_usize;
    for letter in column.bytes() {
        number = number * 26 + usize::from(letter - b'A' + 1);
    }
    if number > 16_384 {
        return Err("Excel-Spalte muss zwischen A und XFD liegen".into());
    }
    Ok(number - 1)
}

fn default_header_row() -> u32 {
    1
}

impl Config {
    pub fn parse(input: &str) -> Result<Self, String> {
        let mut spec: Config = serde_json::from_str(input).map_err(|e| format!("JSON: {e}"))?;
        if spec
            .sheet
            .as_ref()
            .is_some_and(|sheet| sheet.trim().is_empty())
        {
            return Err("'sheet' darf nicht leer sein".into());
        }
        if !(1..=1_048_576).contains(&spec.header_row) {
            return Err("'header_row' muss zwischen 1 und 1048576 liegen".into());
        }
        if let Some(source) = &spec.source {
            if spec.header_row != 1 {
                return Err("header_row ist nur ohne source zulässig".into());
            }
            source.validate()?;
        }
        if spec.sheet.is_none() {
            spec.required_columns = referenced_columns(&spec.predicate);
            let lookup = if let Some(source) = &spec.source {
                source.headers()?.1
            } else {
                spec.required_columns
                    .iter()
                    .enumerate()
                    .map(|(index, name)| (name.clone(), index))
                    .collect()
            };
            // Reject invalid filters even when every worksheet is empty/incompatible.
            Expr::compile(&spec.predicate, &lookup)?;
        }
        Ok(spec)
    }
}

fn referenced_columns(predicate: &Json) -> HashSet<String> {
    fn collect(value: &Json, columns: &mut HashSet<String>) {
        match value {
            Json::Object(fields) => {
                if let Some(name) = fields.get("column").and_then(Json::as_str) {
                    columns.insert(name.to_owned());
                }
                for child in fields.values() {
                    collect(child, columns);
                }
            }
            Json::Array(items) => {
                for child in items {
                    collect(child, columns);
                }
            }
            _ => (),
        }
    }
    let mut columns = HashSet::new();
    collect(predicate, &mut columns);
    columns
}

#[derive(Debug)]
pub(crate) enum Op {
    Eq(Json),
    Ne(Json),
    In(Vec<Json>),
    Gt(f64),
    Gte(f64),
    Lt(f64),
    Lte(f64),
    Contains(String),
    StartsWith(String),
    EndsWith(String),
    Regex(Regex),
    IsEmpty,
    NotEmpty,
}

#[derive(Debug)]
pub(crate) enum Expr {
    All(Vec<Self>),
    Any(Vec<Self>),
    Not(Box<Self>),
    Test { column: usize, op: Op },
}

fn keys_exact(json: &serde_json::Map<String, Json>, expected: &[&str]) -> bool {
    json.len() == expected.len() && expected.iter().all(|key| json.contains_key(*key))
}

fn numeric(json: &Json, op: &str) -> Result<f64, String> {
    let number = json
        .as_f64()
        .ok_or_else(|| format!("'{op}' erwartet eine JSON-Zahl"))?;
    if !number.is_finite() {
        return Err(format!("'{op}': nicht-endliche Zahl"));
    }
    Ok(number)
}

fn text(json: &Json, op: &str) -> Result<String, String> {
    json.as_str()
        .map(String::from)
        .ok_or_else(|| format!("'{op}' erwartet einen JSON-String"))
}

fn scalar(value: &Json) -> bool {
    value.is_null() || value.is_boolean() || value.is_number() || value.is_string()
}

impl Expr {
    pub fn compile(json: &Json, headers: &HashMap<String, usize>) -> Result<Self, String> {
        Self::compile_inner(json, headers, 0)
    }

    fn compile_inner(
        json: &Json,
        headers: &HashMap<String, usize>,
        depth: usize,
    ) -> Result<Self, String> {
        if depth >= 64 {
            return Err("JSON-Filter ist zu tief verschachtelt (maximal 64 Ebenen)".into());
        }
        let obj = json
            .as_object()
            .ok_or("Eine Regel muss ein JSON-Objekt sein")?;
        for key in ["all", "any"] {
            if let Some(value) = obj.get(key) {
                if !keys_exact(obj, &[key]) {
                    return Err(format!("'{key}' darf keine weiteren Felder haben"));
                }
                let items = value
                    .as_array()
                    .filter(|items| !items.is_empty())
                    .ok_or_else(|| format!("'{key}' erwartet eine nichtleere Liste"))?;
                if items.len() > 10_000 {
                    return Err(format!("'{key}' darf höchstens 10000 Regeln enthalten"));
                }
                let compiled = items
                    .iter()
                    .map(|item| Self::compile_inner(item, headers, depth + 1))
                    .collect::<Result<Vec<_>, _>>()?;
                return Ok(if key == "all" {
                    Self::All(compiled)
                } else {
                    Self::Any(compiled)
                });
            }
        }
        if let Some(value) = obj.get("not") {
            if !keys_exact(obj, &["not"]) {
                return Err("'not' darf keine weiteren Felder haben".into());
            }
            return Ok(Self::Not(Box::new(Self::compile_inner(
                value,
                headers,
                depth + 1,
            )?)));
        }

        let column_name = obj
            .get("column")
            .and_then(Json::as_str)
            .ok_or("Ein Vergleich benötigt 'column' als String")?;
        let column = *headers
            .get(column_name)
            .ok_or_else(|| format!("Unbekannte Spalte: {column_name:?}"))?;
        let operation = obj
            .get("op")
            .and_then(Json::as_str)
            .ok_or("Ein Vergleich benötigt 'op' als String")?;
        let no_value = matches!(operation, "is_empty" | "not_empty");
        let expect_keys: &[&str] = if no_value {
            &["column", "op"]
        } else {
            &["column", "op", "value"]
        };
        if !keys_exact(obj, expect_keys) {
            return Err(format!(
                "'{operation}' erwartet exakt die Felder {expect_keys:?}"
            ));
        }
        let op = if no_value {
            if operation == "is_empty" {
                Op::IsEmpty
            } else {
                Op::NotEmpty
            }
        } else {
            let value = obj.get("value").expect("keys already checked");
            match operation {
                "eq" | "ne" if scalar(value) => {
                    if operation == "eq" {
                        Op::Eq(value.clone())
                    } else {
                        Op::Ne(value.clone())
                    }
                }
                "eq" | "ne" => return Err(format!("'{operation}' erwartet einen Skalar")),
                "in" => {
                    let values = value.as_array().ok_or("'in' erwartet eine Liste")?;
                    if values.is_empty() || values.iter().any(|v| !scalar(v)) {
                        return Err("'in' erwartet eine nichtleere Liste aus Skalaren".into());
                    }
                    Op::In(values.clone())
                }
                "gt" => Op::Gt(numeric(value, operation)?),
                "gte" => Op::Gte(numeric(value, operation)?),
                "lt" => Op::Lt(numeric(value, operation)?),
                "lte" => Op::Lte(numeric(value, operation)?),
                "contains" => Op::Contains(text(value, operation)?),
                "starts_with" => Op::StartsWith(text(value, operation)?),
                "ends_with" => Op::EndsWith(text(value, operation)?),
                "regex" => {
                    let pattern = text(value, operation)?;
                    if pattern.len() > 4096 {
                        return Err("Regex darf maximal 4096 Bytes lang sein".into());
                    }
                    let re = RegexBuilder::new(&pattern)
                        .size_limit(8 * 1024 * 1024)
                        .build()
                        .map_err(|e| format!("Ungültiger Regex: {e}"))?;
                    Op::Regex(re)
                }
                _ => return Err(format!("Unbekannter Operator: {operation:?}")),
            }
        };
        Ok(Self::Test { column, op })
    }

    pub fn matches(&self, row: &[CellValue]) -> bool {
        match self {
            Self::All(conditions) => conditions.iter().all(|c| c.matches(row)),
            Self::Any(conditions) => conditions.iter().any(|c| c.matches(row)),
            Self::Not(child) => !child.matches(row),
            Self::Test { column, op } => {
                let cell = row.get(*column).unwrap_or(&CellValue::Empty);
                match op {
                    Op::Eq(value) => equal(cell, value),
                    Op::Ne(value) => !equal(cell, value),
                    Op::In(values) => values.iter().any(|value| equal(cell, value)),
                    Op::Gt(value) => numeric_cell(cell).is_some_and(|v| v > *value),
                    Op::Gte(value) => numeric_cell(cell).is_some_and(|v| v >= *value),
                    Op::Lt(value) => numeric_cell(cell).is_some_and(|v| v < *value),
                    Op::Lte(value) => numeric_cell(cell).is_some_and(|v| v <= *value),
                    Op::Contains(substr) => string_cell(cell).is_some_and(|v| v.contains(substr)),
                    Op::StartsWith(prefix) => {
                        string_cell(cell).is_some_and(|v| v.starts_with(prefix))
                    }
                    Op::EndsWith(suffix) => string_cell(cell).is_some_and(|v| v.ends_with(suffix)),
                    Op::Regex(re) => string_cell(cell).is_some_and(|v| re.is_match(v)),
                    Op::IsEmpty => is_empty(cell),
                    Op::NotEmpty => !is_empty(cell),
                }
            }
        }
    }
}

pub type HeaderLookup = (Vec<(String, usize)>, HashMap<String, usize>);

pub fn headers_from_row(row: &[CellValue]) -> Result<HeaderLookup, String> {
    let mut list = Vec::new();
    let mut lookup = HashMap::new();
    let mut counts = HashMap::new();
    for (position, value) in row.iter().enumerate() {
        let name = match value {
            CellValue::Text(name) if !name.trim().is_empty() => name,
            CellValue::Empty | CellValue::Text(_) => continue,
            _ => {
                return Err(format!(
                    "Spaltenname in Excel-Spalte {} ist kein Text",
                    position + 1
                ))
            }
        };
        *counts.entry(name.clone()).or_insert(0_usize) += 1;
        list.push((name.clone(), position));
    }
    if list.is_empty() {
        return Err("Keine benannten Spalten in der Kopfzeile".into());
    }
    let mut occurrences = HashMap::new();
    for (name, position) in &mut list {
        if counts[name.as_str()] > 1 {
            let occurrence = occurrences.entry(name.clone()).or_insert(0_usize);
            *occurrence += 1;
            *name = format!("{name}_{occurrence}");
        }
        if lookup.insert(name.clone(), *position).is_some() {
            return Err(
                "Spaltennamen sind nach Indizierung nicht eindeutig; source.columns mit eindeutigen Namen verwenden".into(),
            );
        }
    }
    Ok((list, lookup))
}

fn numeric_cell(value: &CellValue) -> Option<f64> {
    match value {
        CellValue::Integer(value) => Some(*value as f64),
        CellValue::Float(value) => Some(*value),
        _ => None,
    }
}

fn string_cell(value: &CellValue) -> Option<&str> {
    match value {
        CellValue::Text(value) => Some(value),
        _ => None,
    }
}

fn is_empty(value: &CellValue) -> bool {
    match value {
        CellValue::Empty => true,
        CellValue::Text(s) => s.is_empty(),
        _ => false,
    }
}

fn equal(cell: &CellValue, expected: &Json) -> bool {
    match (cell, expected) {
        (CellValue::Empty, Json::Null) => true,
        (CellValue::Text(text), Json::String(expected)) => text == expected,
        (CellValue::Bool(value), Json::Bool(expected)) => value == expected,
        (CellValue::Integer(value), Json::Number(expected)) => {
            if let Some(integer) = expected.as_i64() {
                *value == integer
            } else {
                // Floating-point conversion is exact only up to 2^53.
                value.unsigned_abs() <= 9_007_199_254_740_992
                    && expected.as_f64().is_some_and(|n| *value as f64 == n)
            }
        }
        (CellValue::Float(value), Json::Number(expected)) => {
            expected.as_f64().is_some_and(|n| *value == n)
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
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
        let (names, lookup) = headers_from_row(&row).unwrap();
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
}
