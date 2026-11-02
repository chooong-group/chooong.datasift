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
    #[serde(flatten)]
    pub rules: crate::rules::Rules,
    pub source: Option<TableSource>,
    pub sources: Option<Vec<TableSource>>,
    #[serde(default)]
    pub csv: CsvConfig,
    #[serde(default)]
    pub file_errors: FileErrors,
    #[serde(default)]
    pub schema_policy: SchemaPolicy,
    #[serde(skip)]
    pub required_columns: HashSet<String>,
    #[serde(skip)]
    pub header_labels: HashSet<String>,
}

#[derive(Debug, Deserialize, Default, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum SchemaPolicy {
    #[default]
    PerTable,
    Strict,
}

#[derive(Debug, Deserialize, Default, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum FileErrors {
    #[default]
    Fail,
    Continue,
}

#[derive(Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct CsvConfig {
    pub encoding: String,
    pub delimiter: String,
    pub quote: String,
    pub header: bool,
}
impl Default for CsvConfig {
    fn default() -> Self {
        Self {
            encoding: "utf-8".into(),
            delimiter: ",".into(),
            quote: "\"".into(),
            header: true,
        }
    }
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
    #[serde(default)]
    columns: Vec<ColumnBinding>,
    pub header_start_row: Option<u32>,
    pub first_column: Option<String>,
    pub last_column: Option<String>,
    pub data_start_row: u32,
    pub data_end_row: Option<u32>,
    #[serde(default)]
    pub skip_rows: HashSet<u32>,
    pub name: Option<String>,
    pub sheet: Option<String>,
    pub rules: Option<crate::rules::Rules>,
}

impl TableSource {
    pub fn explicit(&self) -> bool {
        !self.columns.is_empty()
    }
    pub fn header_rows(&self, fallback_rows: usize) -> std::ops::Range<u32> {
        let start = self.header_start_row.unwrap_or(0);
        start
            ..start
                + self
                    .rules
                    .as_ref()
                    .map(|r| r.header.rows as u32)
                    .unwrap_or(fallback_rows as u32)
    }
    pub fn column_bounds(&self) -> Result<(usize, usize), String> {
        let first = self
            .first_column
            .as_deref()
            .map(column_index)
            .transpose()?
            .unwrap_or(0);
        let last = self
            .last_column
            .as_deref()
            .map(column_index)
            .transpose()?
            .unwrap_or(16383);
        if first > last {
            return Err("first_column is after last_column".into());
        }
        Ok((first, last))
    }

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
                    return Err("Output names in source.columns must be nonempty and unique".into());
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
            || (self.columns.is_empty() && self.header_start_row.is_none())
            || (!self.columns.is_empty() && self.header_start_row.is_some())
            || (self.header_start_row.is_some() && self.header_rows(1).end > self.data_start_row)
            || self.columns.len() > 16_384
            || self
                .skip_rows
                .iter()
                .any(|row| *row < self.data_start_row || *row > end)
        {
            return Err("Invalid data range in source".into());
        }
        self.column_bounds()?;
        if self.explicit() {
            self.headers()?;
        }
        Ok(())
    }
}

pub fn column_index(column: &str) -> Result<usize, String> {
    if column.is_empty() || column.len() > 3 || !column.bytes().all(|b| b.is_ascii_uppercase()) {
        return Err("Excel column must be between A and XFD".into());
    }
    let mut number = 0_usize;
    for letter in column.bytes() {
        number = number * 26 + usize::from(letter - b'A' + 1);
    }
    if number > 16_384 {
        return Err("Excel column must be between A and XFD".into());
    }
    Ok(number - 1)
}

impl Config {
    pub fn parse(input: &str) -> Result<Self, String> {
        let mut spec: Config = serde_json::from_str(input).map_err(|e| format!("JSON: {e}"))?;
        if spec
            .sheet
            .as_ref()
            .is_some_and(|sheet| sheet.trim().is_empty())
        {
            return Err("'sheet' must not be empty".into());
        }
        if let Some(source) = &spec.source {
            source.validate()?;
        }
        spec.rules.validate()?;
        for source in spec.source.iter().chain(spec.sources.iter().flatten()) {
            if let Some(rules) = &source.rules {
                rules.validate()?;
            }
            if source.header_start_row.is_some()
                && source.header_rows(spec.rules.header.rows).end > source.data_start_row
            {
                return Err("Header extends into the data range".into());
            }
        }
        if spec.source.is_some() && spec.sources.is_some() {
            return Err("source and sources are mutually exclusive".into());
        }
        if let Some(sources) = &spec.sources {
            if sources.is_empty() {
                return Err("sources must not be empty".into());
            }
            let mut names = HashSet::new();
            for source in sources {
                source.validate()?;
                if source.name.as_ref().is_some_and(|n| !names.insert(n)) {
                    return Err("Source names must be unique".into());
                }
                if let Some(rules) = &source.rules {
                    rules.validate()?;
                }
            }
        }
        if spec.csv.delimiter.len() != 1
            || spec.csv.quote.len() != 1
            || spec.csv.delimiter == spec.csv.quote
        {
            return Err("CSV delimiter/quote must be different ASCII characters".into());
        }
        if encoding_rs::Encoding::for_label(spec.csv.encoding.as_bytes()).is_none() {
            return Err("Unknown CSV encoding".into());
        }
        spec.required_columns = if spec.rules.header.anchors.is_empty() {
            spec.rules
                .predicate
                .as_ref()
                .map(referenced_columns)
                .unwrap_or_default()
        } else {
            spec.rules.header.anchors.iter().cloned().collect()
        };
        spec.header_labels = spec.required_columns.clone();
        for name in &spec.required_columns {
            if let Some((base, index)) = name.rsplit_once('_') {
                if index.parse::<usize>().is_ok_and(|index| index > 0) {
                    spec.header_labels.insert(base.to_owned());
                }
            }
        }
        Ok(spec)
    }
}

pub fn compile_regex(pattern: &str) -> Result<Regex, String> {
    if pattern.len() > 4096 {
        return Err("Regex must not exceed 4096 bytes".into());
    }
    RegexBuilder::new(pattern)
        .size_limit(8 * 1024 * 1024)
        .build()
        .map_err(|e| format!("Invalid regex: {e}"))
}

pub(crate) fn referenced_columns(predicate: &Json) -> HashSet<String> {
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
    Gt(Json),
    Gte(Json),
    Lt(Json),
    Lte(Json),
    Contains(String),
    StartsWith(String),
    EndsWith(String),
    Regex(Regex),
    IsEmpty,
    NotEmpty,
    IsType(crate::rules::DataType),
    NotType(crate::rules::DataType),
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

fn numeric(json: &Json, op: &str) -> Result<Json, String> {
    if json.is_number() || exact_value(json).is_ok() {
        Ok(json.clone())
    } else {
        Err(format!("'{op}' expects a number or an exact value"))
    }
}

pub(crate) fn exact_value(json: &Json) -> Result<CellValue, String> {
    let obj = json.as_object().ok_or("Expected an exact object")?;
    let tag = obj
        .get("type")
        .and_then(Json::as_str)
        .ok_or("Missing type")?;
    match tag {
        "decimal" if keys_exact(obj, &["type", "value"]) => {
            Ok(CellValue::Decimal(crate::rules::decimal_text(
                obj["value"].as_str().ok_or("value must be a string")?,
                None,
            )?))
        }
        "money" if keys_exact(obj, &["type", "amount", "currency"]) => {
            let currency = obj["currency"]
                .as_str()
                .ok_or("currency must be a string")?;
            if iso_currency::Currency::from_code(currency).is_none() {
                return Err("Unknown ISO-4217 code".into());
            }
            Ok(CellValue::Money {
                amount: crate::rules::decimal_text(
                    obj["amount"].as_str().ok_or("amount must be a string")?,
                    None,
                )?,
                currency: currency.to_owned(),
            })
        }
        "date" | "datetime" if keys_exact(obj, &["type", "value"]) => crate::rules::convert(
            &CellValue::Text(
                obj["value"]
                    .as_str()
                    .ok_or("value must be a string")?
                    .to_owned(),
            ),
            &crate::rules::TypeRule {
                target: if tag == "date" {
                    crate::rules::DataType::Date
                } else {
                    crate::rules::DataType::Datetime
                },
                convert: true,
                currency: None,
                locale: None,
                format: None,
            },
            false,
        ),
        _ => Err("Invalid exact comparison object".into()),
    }
}
fn compare(cell: &CellValue, expected: &Json) -> Option<std::cmp::Ordering> {
    if let CellValue::IsoDate(raw) = cell {
        let tag = if raw.contains('T') {
            "datetime"
        } else {
            "date"
        };
        let cell = exact_value(&serde_json::json!({"type":tag,"value":raw})).ok()?;
        return compare(&cell, expected);
    }
    match (cell, expected) {
        (CellValue::Integer(a), Json::Number(b)) => {
            return if let Some(b) = b.as_i64() {
                Some(a.cmp(&b))
            } else {
                (*a as f64).partial_cmp(&b.as_f64()?)
            }
        }
        (CellValue::Float(a), Json::Number(b)) => return a.partial_cmp(&b.as_f64()?),
        _ => (),
    }

    use rust_decimal::Decimal;
    let target = if expected.is_object() {
        exact_value(expected).ok()?
    } else {
        CellValue::from_json(expected).ok()?
    };
    fn dec(v: &CellValue) -> Option<Decimal> {
        match v {
            CellValue::Integer(n) => Some(Decimal::from(*n)),
            CellValue::Float(n) => crate::rules::decimal_text(&n.to_string(), None).ok(),
            CellValue::Decimal(n) => Some(*n),
            CellValue::StyledNumber { raw: s, .. } | CellValue::NumberText(s) => {
                crate::rules::decimal_text(s, None).ok()
            }
            _ => None,
        }
    }
    match (cell, &target) {
        (
            CellValue::Money {
                amount: a,
                currency: c,
            },
            CellValue::Money {
                amount: b,
                currency: d,
            },
        ) if c == d => Some(a.cmp(b)),
        (CellValue::Date(a), CellValue::Date(b)) => Some(a.cmp(b)),
        (CellValue::DateTime(a), CellValue::DateTime(b)) => Some(a.cmp(b)),
        (CellValue::ZonedDateTime(a), CellValue::ZonedDateTime(b)) => Some(a.cmp(b)),
        _ => Some(dec(cell)?.cmp(&dec(&target)?)),
    }
}

fn text(json: &Json, op: &str) -> Result<String, String> {
    json.as_str()
        .map(String::from)
        .ok_or_else(|| format!("'{op}' expects a JSON string"))
}

fn scalar(value: &Json) -> bool {
    value.is_null()
        || value.is_boolean()
        || value.is_number()
        || value.is_string()
        || exact_value(value).is_ok()
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
            return Err("JSON filter is nested too deeply (maximum 64 levels)".into());
        }
        let obj = json.as_object().ok_or("A rule must be a JSON object")?;
        for key in ["all", "any"] {
            if let Some(value) = obj.get(key) {
                if !keys_exact(obj, &[key]) {
                    return Err(format!("'{key}' must not have additional fields"));
                }
                let items = value
                    .as_array()
                    .filter(|items| !items.is_empty())
                    .ok_or_else(|| format!("'{key}' expects a nonempty list"))?;
                if items.len() > 10_000 {
                    return Err(format!("'{key}' must not contain more than 10000 rules"));
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
                return Err("'not' must not have additional fields".into());
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
            .ok_or("A comparison requires 'column' as a string")?;
        let column = *headers
            .get(column_name)
            .ok_or_else(|| format!("Unknown column: {column_name:?}"))?;
        let operation = obj
            .get("op")
            .and_then(Json::as_str)
            .ok_or("A comparison requires 'op' as a string")?;
        let no_value = matches!(operation, "is_empty" | "not_empty");
        let expect_keys: &[&str] = if no_value {
            &["column", "op"]
        } else {
            &["column", "op", "value"]
        };
        if !keys_exact(obj, expect_keys) {
            return Err(format!(
                "'{operation}' expects exactly the fields {expect_keys:?}"
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
                "eq" | "ne" => return Err(format!("'{operation}' expects a scalar")),
                "in" => {
                    let values = value.as_array().ok_or("'in' expects a list")?;
                    if values.is_empty() || values.iter().any(|v| !scalar(v)) {
                        return Err("'in' expects a nonempty list of scalars".into());
                    }
                    Op::In(values.clone())
                }
                "is_type" | "not_type" => {
                    let target =
                        serde_json::from_value(value.clone()).map_err(|_| "Unknown data type")?;
                    if operation == "is_type" {
                        Op::IsType(target)
                    } else {
                        Op::NotType(target)
                    }
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
                        return Err("Regex must not exceed 4096 bytes".into());
                    }
                    let re = RegexBuilder::new(&pattern)
                        .size_limit(8 * 1024 * 1024)
                        .build()
                        .map_err(|e| format!("Invalid regex: {e}"))?;
                    Op::Regex(re)
                }
                _ => return Err(format!("Unknown operator: {operation:?}")),
            }
        };
        Ok(Self::Test { column, op })
    }

    pub fn invalid_currencies(&self, row: &[CellValue]) -> Vec<crate::value::Reason> {
        use crate::value::{Reason, ReasonCode};
        match self {
            Self::All(items) | Self::Any(items) => items
                .iter()
                .flat_map(|c| c.invalid_currencies(row))
                .collect(),
            Self::Not(child) => child.invalid_currencies(row),
            Self::Test { column, op } => {
                let Some(CellValue::Money { currency, .. }) = row.get(*column) else {
                    return vec![];
                };
                let values: Vec<&Json> = match op {
                    Op::Eq(v) | Op::Ne(v) | Op::Gt(v) | Op::Gte(v) | Op::Lt(v) | Op::Lte(v) => {
                        vec![v]
                    }
                    Op::In(v) => v.iter().collect(),
                    _ => vec![],
                };
                if values.iter().any(|v| {
                    v.get("type").and_then(Json::as_str) == Some("money")
                        && v.get("currency").and_then(Json::as_str) != Some(currency)
                }) {
                    vec![Reason {
                        code: ReasonCode::TypeMismatch,
                        column: None,
                    }]
                } else {
                    vec![]
                }
            }
        }
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
                    Op::Gt(value) => compare(cell, value).is_some_and(|v| v.is_gt()),
                    Op::Gte(value) => compare(cell, value).is_some_and(|v| v.is_ge()),
                    Op::Lt(value) => compare(cell, value).is_some_and(|v| v.is_lt()),
                    Op::Lte(value) => compare(cell, value).is_some_and(|v| v.is_le()),
                    Op::Contains(substr) => string_cell(cell).is_some_and(|v| v.contains(substr)),
                    Op::StartsWith(prefix) => {
                        string_cell(cell).is_some_and(|v| v.starts_with(prefix))
                    }
                    Op::EndsWith(suffix) => string_cell(cell).is_some_and(|v| v.ends_with(suffix)),
                    Op::Regex(re) => string_cell(cell).is_some_and(|v| re.is_match(v)),
                    Op::IsEmpty => is_empty(cell),
                    Op::NotEmpty => !is_empty(cell),
                    Op::IsType(target) => crate::rules::is_type(cell, *target),
                    Op::NotType(target) => !crate::rules::is_type(cell, *target),
                }
            }
        }
    }
}

pub type HeaderLookup = (Vec<(String, usize)>, HashMap<String, usize>);

pub fn headers_from_row(
    row: &[CellValue],
    required: &HashSet<String>,
) -> Result<HeaderLookup, String> {
    let mut list = Vec::new();
    let mut lookup = HashMap::new();
    let mut counts = HashMap::new();
    for (position, value) in row.iter().enumerate() {
        let name = match value {
            CellValue::Text(name) if !name.trim().is_empty() => name,
            _ => continue,
        };
        *counts.entry(name.clone()).or_insert(0_usize) += 1;
        list.push((name.clone(), position));
    }
    let mut occurrences = HashMap::new();
    for (name, position) in &mut list {
        if counts[name.as_str()] > 1 {
            let occurrence = occurrences.entry(name.clone()).or_insert(0_usize);
            *occurrence += 1;
            *name = format!("{name}_{occurrence}");
        }
        if !required.contains(name) {
            continue;
        }
        if lookup.insert(name.clone(), *position).is_some() {
            return Err(
                "Column names are not unique after indexing; use source.columns with unique names"
                    .into(),
            );
        }
    }
    list.retain(|(name, _)| required.contains(name));
    Ok((list, lookup))
}

/// Resolve a row as one schema, or repeated complete unindexed schemas side by side.
pub fn tables_from_row(
    row: &[CellValue],
    required: &HashSet<String>,
) -> Result<Vec<HeaderLookup>, String> {
    let whole = headers_from_row(row, required)?;
    if whole.1.len() == required.len() {
        return Ok(vec![whole]);
    }
    // ponytail: a single repeated name cannot distinguish tables from duplicate
    // columns. Split only two or more complete multi-column schemas; otherwise
    // keep indexed header semantics and require explicit source for ambiguity.
    if required.len() < 2 {
        return Ok(Vec::new());
    }
    let mut groups = Vec::new();
    let mut names = Vec::new();
    let mut lookup = HashMap::new();
    for (position, cell) in row.iter().enumerate() {
        let CellValue::Text(name) = cell else {
            continue;
        };
        if !required.contains(name) {
            continue;
        }
        if lookup.insert(name.clone(), position).is_some() {
            return Ok(Vec::new());
        }
        names.push((name.clone(), position));
        if lookup.len() == required.len() {
            groups.push((std::mem::take(&mut names), std::mem::take(&mut lookup)));
        }
    }
    if groups.len() >= 2 && lookup.is_empty() {
        Ok(groups)
    } else {
        Ok(Vec::new())
    }
}

fn string_cell(value: &CellValue) -> Option<&str> {
    match value {
        CellValue::Text(value) => Some(value),
        _ => None,
    }
}

fn is_empty(value: &CellValue) -> bool {
    value.empty()
}

fn equal(cell: &CellValue, expected: &Json) -> bool {
    match (cell, expected) {
        (CellValue::Empty, Json::Null) => true,
        (CellValue::IsoDate(text) | CellValue::Text(text), Json::String(expected)) => {
            text == expected
        }
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
        (
            CellValue::Decimal(_)
            | CellValue::Money { .. }
            | CellValue::Date(_)
            | CellValue::DateTime(_)
            | CellValue::ZonedDateTime(_)
            | CellValue::IsoDate(_)
            | CellValue::StyledNumber { .. }
            | CellValue::NumberText(_),
            _,
        ) => compare(cell, expected).is_some_and(|o| o.is_eq()),
        (CellValue::Currency(code), Json::String(s)) => code == s,
        _ => false,
    }
}

#[cfg(test)]
#[path = "../tests/unit/filter.rs"]
mod tests;
