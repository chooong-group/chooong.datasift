//! One row pipeline shared by CSV and OOXML adapters.
use crate::filter::{headers_from_row, tables_from_row, Config, Expr, HeaderLookup, TableSource};
use crate::rules::{convert, is_type, RowClass, Rules, Selection};
use crate::value::{CellValue, Reason, ReasonCode, Record, RecordKind};
use crate::Message;
use serde::Serialize;
use serde_json::{json, Value as Json};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::SyncSender;
use std::sync::Arc;

#[derive(Default, Serialize)]
pub struct Statistics {
    pub rows_read: u64,
    pub matched: u64,
    pub rejected: u64,
    pub defaults: u64,
    pub conversions: u64,
    pub reasons: BTreeMap<ReasonCode, u64>,
    pub tables: Vec<TableExplanation>,
    pub diagnostics: Vec<Json>,
    pub complete: bool,
    pub seconds: f64,
    #[serde(skip)]
    pub schema: Option<Vec<String>>,
    pub row_classes: BTreeMap<RowClass, u64>,
}

#[derive(Serialize)]
pub struct TableExplanation {
    file: String,
    sheet: String,
    table: String,
    header_row: u32,
    bindings: Vec<(String, usize)>,
    raw_headers: Vec<(String, usize)>,
    defaults: Vec<String>,
    types: Vec<String>,
    type_rules: BTreeMap<String, crate::rules::TypeRule>,
    header: crate::rules::HeaderConfig,
    data_start_row: u32,
    data_end_row: Option<u32>,
}

struct Table<'a> {
    names: Vec<(String, usize)>,
    output: Vec<(String, usize)>,
    predicate: Option<Expr>,
    row_rules: Vec<(crate::rules::RowRule, Option<Expr>)>,
    rules: &'a Rules,
    source: Option<&'a TableSource>,
    header_row: u32,
    repeated: bool,
    order: usize,
    first: usize,
    last: usize,
    name: String,
    schema_reasons: Vec<Reason>,
    explanation: usize,
}

pub struct Sink<'a> {
    pub config: &'a Config,
    pub sender: &'a SyncSender<Message>,
    pub cancelled: &'a Arc<AtomicBool>,
    pub batch_size: usize,
    pub events: bool,
    pub rejects: bool,
    pub file: String,
    pub sheet: String,
    pub date1904: bool,
    pub stats: &'a mut Statistics,
    pub styles: Vec<String>,
    pub merges: Vec<crate::value::Merge>,
    merge_values: HashMap<(u32, usize), CellValue>,
    headers: Option<Vec<(String, usize)>>,
    tables: Vec<Table<'a>>,
    buffer: Vec<Vec<CellValue>>,
    records: Vec<Record>,
    header_buffer: Vec<Vec<CellValue>>,
    pending_sources: Vec<(&'a TableSource, Vec<Vec<CellValue>>)>,
}
impl<'a> Sink<'a> {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        config: &'a Config,
        sender: &'a SyncSender<Message>,
        cancelled: &'a Arc<AtomicBool>,
        batch_size: usize,
        events: bool,
        rejects: bool,
        file: String,
        sheet: String,
        date1904: bool,
        stats: &'a mut Statistics,
    ) -> Self {
        Self {
            styles: Vec::new(),
            merges: Vec::new(),
            merge_values: HashMap::new(),
            config,
            sender,
            cancelled,
            batch_size,
            events,
            rejects,
            file,
            sheet,
            date1904,
            stats,
            headers: None,
            tables: Vec::new(),
            buffer: Vec::with_capacity(batch_size),
            records: Vec::with_capacity(batch_size),
            header_buffer: Vec::new(),
            pending_sources: Vec::new(),
        }
    }
    pub fn has_headers(&self) -> bool {
        self.headers.is_some()
    }
    pub fn initialize(&mut self) -> Result<(), String> {
        let sources: Vec<_> = self
            .config
            .sources
            .as_ref()
            .map(|s| s.iter().collect())
            .unwrap_or_else(|| self.config.source.iter().collect());
        for (index, source) in sources.into_iter().enumerate() {
            if source.sheet.as_ref().is_none_or(|s| s == &self.sheet) {
                if source.explicit() {
                    self.prepare(source.headers()?, 0, Some(source), index, &[])?;
                } else {
                    self.pending_sources.push((source, Vec::new()));
                }
            }
        }
        Ok(())
    }
    fn prepare(
        &mut self,
        (names, lookup): HeaderLookup,
        number: u32,
        source: Option<&'a TableSource>,
        index: usize,
        raw: &[CellValue],
    ) -> Result<(), String> {
        let rules = source
            .and_then(|s| s.rules.as_ref())
            .unwrap_or(&self.config.rules);
        let mut reasons = Vec::new();
        let mut schema: Vec<_> = lookup.keys().cloned().collect();
        schema.sort();
        if self.config.schema_policy == crate::filter::SchemaPolicy::Strict
            && self.stats.schema.as_ref().is_some_and(|s| s != &schema)
        {
            reasons.push(Reason {
                code: ReasonCode::SchemaMismatch,
                column: None,
            });
        }
        self.stats.schema.get_or_insert(schema);
        let mut missing = HashSet::new();
        for name in rules
            .required
            .iter()
            .chain(rules.defaults.keys())
            .chain(rules.types.keys())
        {
            if !lookup.contains_key(name) && missing.insert(name.clone()) {
                reasons.push(Reason {
                    code: ReasonCode::SchemaMismatch,
                    column: Some(name.clone()),
                });
            }
        }
        let predicate = if let Some(p) = &rules.predicate {
            match Expr::compile(p, &lookup) {
                Ok(p) => Some(p),
                Err(e) if !self.events => return Err(e),
                Err(_) => {
                    reasons.push(Reason {
                        code: ReasonCode::SchemaMismatch,
                        column: None,
                    });
                    None
                }
            }
        } else {
            None
        };
        let mut output = Vec::new();
        if let Some(select) = &rules.select {
            for selection in select {
                let selected: Vec<_> = match selection {
                    Selection::Name(name) if name == "*" => names.clone(),
                    Selection::Name(name) => lookup
                        .get(name)
                        .map(|i| vec![(name.clone(), *i)])
                        .ok_or("select: unbekannte Spalte")?,
                    Selection::Pattern { pattern } => {
                        let re = crate::filter::compile_regex(pattern)?;
                        let found: Vec<_> = names
                            .iter()
                            .filter(|(n, _)| re.is_match(n))
                            .cloned()
                            .collect();
                        if found.is_empty() {
                            return Err("select: Regex ohne Treffer".into());
                        }
                        found
                    }
                };
                for binding in selected {
                    if !output.iter().any(|(n, _)| n == &binding.0) {
                        output.push(binding);
                    }
                }
            }
        } else if let Some(predicate) = &rules.predicate {
            // Compatibility: absent select returns only filter fields.
            let mut columns = HashSet::new();
            fn collect(j: &Json, c: &mut HashSet<String>) {
                match j {
                    Json::Object(o) => {
                        if let Some(n) = o.get("column").and_then(Json::as_str) {
                            c.insert(n.to_owned());
                        }
                        for v in o.values() {
                            collect(v, c);
                        }
                    }
                    Json::Array(a) => {
                        for v in a {
                            collect(v, c);
                        }
                    }
                    _ => (),
                }
            }
            collect(predicate, &mut columns);
            output = names
                .iter()
                .filter(|(n, _)| columns.contains(n))
                .cloned()
                .collect();
        } else {
            output = names.clone();
        }
        let first = names
            .iter()
            .map(|(_, i)| *i)
            .min()
            .ok_or("Leeres Tabellenschema")?;
        let last = names
            .iter()
            .map(|(_, i)| *i)
            .max()
            .ok_or("Leeres Tabellenschema")?;
        let repeated = self.tables.iter().any(|t| t.names == names);
        if source.is_none() {
            self.tables.retain(|t| t.last < first || t.first > last);
        }
        let name = source
            .and_then(|s| s.name.clone())
            .unwrap_or_else(|| format!("table-{}-{}", number, index + 1));
        // Explain metadata is bounded independently of input length.
        if self.stats.tables.len() >= 16384 {
            return Err("Zu viele Tabellen (maximal 16384)".into());
        }
        let explanation = self.stats.tables.len();
        self.stats.tables.push(TableExplanation {
            file: self.file.clone(),
            sheet: self.sheet.clone(),
            table: name.clone(),
            header_row: number,
            bindings: names.clone(),
            raw_headers: names
                .iter()
                .filter_map(|(_, i)| match raw.get(*i) {
                    Some(CellValue::Text(s)) => Some((s.clone(), *i)),
                    _ => None,
                })
                .collect(),
            defaults: rules.defaults.keys().cloned().collect(),
            types: rules.types.keys().cloned().collect(),
            type_rules: rules.types.clone(),
            header: rules.header.clone(),
            data_start_row: source.map(|s| s.data_start_row).unwrap_or(number + 1),
            data_end_row: source.and_then(|s| s.data_end_row),
        });
        if !reasons.is_empty() {
            self.diagnostic("SCHEMA_MISMATCH", Some(name.clone()))?;
        }
        let row_rules = rules
            .row_policy
            .rules
            .iter()
            .map(|rule| {
                Ok((
                    rule.clone(),
                    rule.predicate
                        .as_ref()
                        .map(|p| Expr::compile(p, &lookup))
                        .transpose()?,
                ))
            })
            .collect::<Result<Vec<_>, String>>()?;
        if self.headers.is_none() {
            self.use_headers(
                output
                    .iter()
                    .enumerate()
                    .map(|(i, (n, _))| (n.clone(), i))
                    .collect(),
            )?;
        }
        self.tables.push(Table {
            names,
            output,
            predicate,
            row_rules,
            rules,
            source,
            header_row: number,
            repeated,
            order: source
                .and_then(|s| {
                    self.config.sources.as_ref().and_then(|sources| {
                        sources
                            .iter()
                            .position(|candidate| std::ptr::eq(candidate, s))
                    })
                })
                .unwrap_or(index),
            first,
            last,
            name,
            schema_reasons: reasons,
            explanation,
        });
        if source.is_none() {
            self.tables.sort_by_key(|t| t.first);
        } else {
            self.tables.sort_by_key(|t| t.order);
        }
        Ok(())
    }
    pub fn diagnostic(&mut self, code: &str, table: Option<String>) -> Result<(), String> {
        if self.stats.diagnostics.len() >= 16384 {
            return Err("Zu viele Diagnosen".into());
        }
        self.stats
            .diagnostics
            .push(json!({"code":code,"file":self.file,"sheet":self.sheet,"table":table}));
        Ok(())
    }
    fn use_headers(&mut self, headers: Vec<(String, usize)>) -> Result<(), String> {
        if self.headers.as_ref() != Some(&headers) {
            self.flush()?;
            self.sender
                .send(Message::Ready(headers.clone()))
                .map_err(|_| "Verbraucher geschlossen")?;
            self.headers = Some(headers);
        }
        Ok(())
    }
    pub fn selects_cell(&self, row: u32, col: usize) -> bool {
        if !self.pending_sources.is_empty() {
            return true;
        }
        if self.tables.is_empty() {
            return self.config.source.is_none() && self.config.sources.is_none();
        }
        self.tables.iter().any(|t| {
            t.source.is_none_or(|s| s.contains_row(row)) && t.names.iter().any(|(_, i)| *i == col)
        })
    }
    pub(crate) fn needs_exact_numbers(&self) -> bool {
        !self.config.rules.types.is_empty() || self.tables.iter().any(|t| !t.rules.types.is_empty())
    }
    fn discover(&mut self, number: u32, row: &[CellValue]) -> Result<(), String> {
        let h = &self.config.rules.header;
        if !self.config.required_columns.is_empty() && !self.tables.is_empty() && !row.iter().any(|v|matches!(v,CellValue::Text(s) if self.config.header_labels.contains(s) || ((h.trim||h.lowercase||h.unicode.is_some()||h.collapse_whitespace||!h.aliases.is_empty()) && self.config.header_labels.contains(&h.normalize(s))))){return Ok(());}
        let mut normalized: Vec<_> = row
            .iter()
            .map(|v| match v {
                CellValue::Text(s) => CellValue::Text(h.normalize(s)),
                _ => v.clone(),
            })
            .collect();
        if h.rows > 1 && self.tables.is_empty() {
            self.header_buffer.push(normalized);
            if self.header_buffer.len() < h.rows {
                return Ok(());
            }
            let width = self.header_buffer.iter().map(Vec::len).max().unwrap_or(0);
            normalized = (0..width)
                .map(|i| {
                    CellValue::Text(
                        self.header_buffer
                            .iter()
                            .filter_map(|r| match r.get(i) {
                                Some(CellValue::Text(s)) if !s.is_empty() => Some(s.as_str()),
                                _ => None,
                            })
                            .collect::<Vec<_>>()
                            .join(" "),
                    )
                })
                .collect();
            self.header_buffer.remove(0);
        }
        let required = &self.config.required_columns;
        if h.trim
            || h.lowercase
            || h.unicode.is_some()
            || h.collapse_whitespace
            || !h.aliases.is_empty()
        {
            let mut originals = HashMap::new();
            for cell in row {
                if let CellValue::Text(raw) = cell {
                    let normalized = h.normalize(raw);
                    if (required.contains(&normalized)
                        || (required.is_empty() && self.tables.is_empty()))
                        && originals
                            .insert(normalized, raw)
                            .is_some_and(|previous| previous != raw)
                    {
                        return Err("Header-Normalisierung erzeugt eine Namenskollision".into());
                    }
                }
            }
        }
        let groups = if required.is_empty() {
            if !self.tables.is_empty() {
                // Automatic mode recognizes only exact repeated schemas after first discovery.
                let schemas: Vec<_> = self
                    .tables
                    .iter()
                    .map(|t| {
                        t.names
                            .iter()
                            .map(|(n, _)| n.clone())
                            .collect::<HashSet<_>>()
                    })
                    .collect();
                let mut result = Vec::new();
                for schema in schemas {
                    result.extend(tables_from_row(&normalized, &schema)?);
                }
                result
            } else {
                // Deterministic structural heuristic: contiguous, nonblank text runs.
                let mut result = Vec::new();
                let mut start = 0;
                while start < normalized.len() {
                    if !matches!(&normalized[start],CellValue::Text(s) if !s.trim().is_empty()) {
                        start += 1;
                        continue;
                    }
                    let mut end = start + 1;
                    while end < normalized.len()
                        && matches!(&normalized[end],CellValue::Text(s) if !s.trim().is_empty())
                    {
                        end += 1;
                    }
                    if end - start >= h.min_columns {
                        let all: HashSet<_> = normalized[start..end]
                            .iter()
                            .filter_map(|v| match v {
                                CellValue::Text(s) => Some(s.clone()),
                                _ => None,
                            })
                            .collect();
                        let (indexed, _) = headers_from_row(&normalized[start..end], &all)?;
                        // Re-resolve duplicate names using generated suffixes.
                        let mut counts = HashMap::new();
                        for v in &normalized[start..end] {
                            if let CellValue::Text(s) = v {
                                *counts.entry(s.clone()).or_insert(0_usize) += 1;
                            }
                        }
                        let mut seen = HashMap::new();
                        let mut names = Vec::new();
                        let mut lookup = HashMap::new();
                        let _ = indexed;
                        for (offset, v) in normalized[start..end].iter().enumerate() {
                            if let CellValue::Text(s) = v {
                                let count = seen.entry(s.clone()).or_insert(0_usize);
                                *count += 1;
                                let n = if counts[s] > 1 {
                                    format!("{s}_{count}")
                                } else {
                                    s.clone()
                                };
                                if lookup.insert(n.clone(), start + offset).is_some() {
                                    return Err("Mehrdeutige normalisierte Header".into());
                                }
                                names.push((n, start + offset));
                            }
                        }
                        result.push((names, lookup));
                    }
                    start = end;
                }
                result
            }
        } else {
            tables_from_row(&normalized, required)?
        };
        for (index, (mut names, mut lookup)) in groups.into_iter().enumerate() {
            if h.trim
                || h.lowercase
                || h.unicode.is_some()
                || h.collapse_whitespace
                || !h.aliases.is_empty()
            {
                let mut originals = HashMap::new();
                for (_, position) in &names {
                    if let Some(CellValue::Text(raw)) = row.get(*position) {
                        let normalized = h.normalize(raw);
                        if originals
                            .insert(normalized, raw)
                            .is_some_and(|previous| previous != raw)
                        {
                            return Err("Header-Normalisierung erzeugt eine Namenskollision".into());
                        }
                    }
                }
            }
            // Full projection with an anchored schema includes contiguous neighboring labels.
            if (self.config.rules.select.is_some()
                || !self.config.rules.types.is_empty()
                || !self.config.rules.required.is_empty()
                || !self.config.rules.defaults.is_empty()
                || !self.config.rules.header.anchors.is_empty())
                && !required.is_empty()
            {
                let mut first = names.iter().map(|(_, i)| *i).min().unwrap_or(0);
                while first > 0
                    && matches!(&normalized[first-1],CellValue::Text(s) if !s.trim().is_empty() && !required.contains(s))
                {
                    first -= 1;
                }
                let mut end = names.iter().map(|(_, i)| *i).max().unwrap_or(first) + 1;
                while end < normalized.len()
                    && matches!(&normalized[end],CellValue::Text(s) if !s.trim().is_empty() && !required.contains(s))
                {
                    end += 1;
                }
                let all = all_headers(&normalized[first..end])?;
                names = all.0.into_iter().map(|(n, i)| (n, i + first)).collect();
                lookup = names.iter().cloned().collect();
            }
            self.prepare((names, lookup), number, None, index, row)?;
        }
        Ok(())
    }
    pub fn on_row(&mut self, number: u32, row: Vec<CellValue>) -> Result<(), String> {
        if self.cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        self.stats.rows_read += 1;
        let mut header_row = std::borrow::Cow::Borrowed(&row);
        if (self.tables.is_empty() || !self.pending_sources.is_empty()) && !self.merges.is_empty() {
            for merge in &self.merges {
                if merge.first_row == number {
                    if let Some(value) = header_row.get(merge.first_col) {
                        self.merge_values
                            .insert((merge.first_row, merge.first_col), value.clone());
                    }
                }
                if merge.first_row <= number && number <= merge.last_row {
                    if let Some(value) = self.merge_values.get(&(merge.first_row, merge.first_col))
                    {
                        let row = header_row.to_mut();
                        row.resize(row.len().max(merge.last_col + 1), CellValue::Empty);
                        for cell in &mut row[merge.first_col..=merge.last_col] {
                            if cell.empty() {
                                *cell = value.clone();
                            }
                        }
                    }
                }
            }
        }
        let mut prepared = Vec::new();
        for (index, (source, buffer)) in self.pending_sources.iter_mut().enumerate() {
            if source
                .header_rows(self.config.rules.header.rows)
                .contains(&number)
            {
                buffer.push(header_row.to_vec());
            }
            if source.header_rows(self.config.rules.header.rows).end == number + 1 {
                let header = &source.rules.as_ref().unwrap_or(&self.config.rules).header;
                let (first, last) = source.column_bounds()?;
                let width = buffer.iter().map(Vec::len).max().unwrap_or(0).min(last + 1);
                let mut joined = vec![CellValue::Empty; first.min(width)];
                let mut original = joined.clone();
                let mut normalized_labels = HashMap::new();
                for col in first..width {
                    let label = buffer
                        .iter()
                        .filter_map(|r| match r.get(col) {
                            Some(CellValue::Text(s)) if !s.is_empty() => Some(s.as_str()),
                            _ => None,
                        })
                        .collect::<Vec<_>>()
                        .join(" ");
                    let normalized = header.normalize(&label);
                    if !normalized.is_empty()
                        && normalized_labels
                            .insert(normalized.clone(), label.clone())
                            .is_some_and(|previous| previous != label)
                    {
                        return Err("Header-Normalisierung erzeugt eine Namenskollision".into());
                    }
                    original.push(CellValue::Text(label));
                    joined.push(CellValue::Text(normalized));
                }
                let lookup = all_headers(&joined)?;
                prepared.push((index, *source, lookup, original));
            }
        }
        for (index, _, _, _) in prepared.iter().rev() {
            self.pending_sources.remove(*index);
        }
        for (index, source, lookup, original) in prepared {
            self.prepare(lookup, number, Some(source), index, &original)?;
        }
        if self.config.source.is_none() && self.config.sources.is_none() {
            self.discover(number, &header_row)?;
        }
        for index in 0..self.tables.len() {
            let table = &self.tables[index];
            if table.source.is_some_and(|s| !s.contains_row(number)) {
                continue;
            }
            self.stats.tables[table.explanation].data_end_row = Some(number);
            let mut class = if table.header_row == number {
                if table.repeated {
                    RowClass::RepeatedHeader
                } else {
                    RowClass::Header
                }
            } else if table.source.is_none()
                && table
                    .names
                    .iter()
                    .all(|(_, i)| row.get(*i).is_none_or(CellValue::empty))
            {
                RowClass::Empty
            } else {
                RowClass::Data
            };
            for (rule, predicate) in &table.row_rules {
                if (rule.rows.is_empty() || rule.rows.contains(&number))
                    && predicate.as_ref().is_none_or(|p| p.matches(&row))
                {
                    class = rule.classification;
                    break;
                }
            }
            *self.stats.row_classes.entry(class).or_default() += 1;
            if !table.rules.row_policy.include.contains(&class)
                || table.rules.row_policy.exclude.contains(&class)
            {
                continue;
            }
            let mut transformed = (!table.rules.defaults.is_empty()
                || !table.rules.types.is_empty())
            .then(|| row.clone());
            let mut reasons = table.schema_reasons.clone();
            if let Some(effective) = &mut transformed {
                for (name, pos) in &table.names {
                    if effective.len() <= *pos {
                        effective.resize(*pos + 1, CellValue::Empty);
                    }
                    let cell = &mut effective[*pos];
                    if cell.empty() {
                        if let Some(default) = table.rules.defaults.get(name) {
                            *cell = CellValue::from_json(default)?;
                            self.stats.defaults += 1;
                        }
                    }
                    if let Some(rule) = table.rules.types.get(name) {
                        match convert(cell, rule, self.date1904) {
                            Ok(converted) => {
                                if &converted != cell {
                                    self.stats.conversions += 1;
                                }
                                *cell = converted;
                            }
                            Err(_) => reasons.push(Reason {
                                code: if rule.convert {
                                    ReasonCode::ConversionFailed
                                } else {
                                    ReasonCode::TypeMismatch
                                },
                                column: Some(name.clone()),
                            }),
                        }
                        if !cell.empty()
                            && !is_type(cell, rule.target)
                            && !reasons.iter().any(|r| r.column.as_ref() == Some(name))
                        {
                            reasons.push(Reason {
                                code: ReasonCode::TypeMismatch,
                                column: Some(name.clone()),
                            });
                        }
                    } else if let CellValue::NumberText(raw) | CellValue::StyledNumber { raw, .. } =
                        cell
                    {
                        *cell = CellValue::number(raw)?;
                    }
                    if cell.empty() && table.rules.required.contains(name) {
                        reasons.push(Reason {
                            code: ReasonCode::RequiredMissing,
                            column: Some(name.clone()),
                        });
                    }
                }
            }
            let effective = transformed.as_ref().unwrap_or(&row);
            if transformed.is_none() {
                for (name, pos) in &table.names {
                    if row.get(*pos).is_none_or(CellValue::empty)
                        && table.rules.required.contains(name)
                    {
                        reasons.push(Reason {
                            code: ReasonCode::RequiredMissing,
                            column: Some(name.clone()),
                        });
                    }
                }
            }
            if let Some(predicate) = &table.predicate {
                reasons.extend(predicate.invalid_currencies(effective));
            }
            if table
                .predicate
                .as_ref()
                .is_some_and(|p| !p.matches(effective))
            {
                reasons.push(Reason {
                    code: ReasonCode::FilterNotMatched,
                    column: None,
                });
            }
            let matched = reasons.is_empty();
            if matched {
                self.stats.matched += 1;
            } else {
                self.stats.rejected += 1;
                for reason in &reasons {
                    *self.stats.reasons.entry(reason.code).or_default() += 1;
                }
            }
            if self.events {
                if matched || self.rejects {
                    let bindings = if matched { &table.output } else { &table.names };
                    let values = if matched { effective } else { &row };
                    self.records.push(Record {
                        kind: if matched {
                            RecordKind::Matched
                        } else {
                            RecordKind::Rejected
                        },
                        file: self.file.clone(),
                        sheet: self.sheet.clone(),
                        table: table.name.clone(),
                        row: number,
                        values: bindings
                            .iter()
                            .map(|(n, i)| {
                                (
                                    n.clone(),
                                    values.get(*i).unwrap_or(&CellValue::Empty).json(),
                                )
                            })
                            .collect(),
                        source_types: table
                            .names
                            .iter()
                            .map(|(name, i)| {
                                (
                                    name.clone(),
                                    row.get(*i)
                                        .unwrap_or(&CellValue::Empty)
                                        .source_type()
                                        .to_owned(),
                                )
                            })
                            .collect(),
                        reasons,
                    });
                    if self.records.len() >= self.batch_size {
                        self.flush()?;
                    }
                }
            } else if matched {
                let headers = table
                    .output
                    .iter()
                    .enumerate()
                    .map(|(i, (n, _))| (n.clone(), i))
                    .collect();
                let values = table
                    .output
                    .iter()
                    .map(|(_, i)| effective.get(*i).cloned().unwrap_or(CellValue::Empty))
                    .collect();
                self.use_headers(headers)?;
                self.buffer.push(values);
                if self.buffer.len() >= self.batch_size {
                    self.flush()?;
                }
            }
        }
        Ok(())
    }
    pub fn flush(&mut self) -> Result<(), String> {
        if !self.buffer.is_empty() {
            self.sender
                .send(Message::Batch(std::mem::take(&mut self.buffer)))
                .map_err(|_| "Verbraucher geschlossen")?;
        }
        if !self.records.is_empty() {
            self.sender
                .send(Message::Records(std::mem::take(&mut self.records)))
                .map_err(|_| "Verbraucher geschlossen")?;
        }
        Ok(())
    }
}

fn all_headers(row: &[CellValue]) -> Result<HeaderLookup, String> {
    let mut counts = HashMap::new();
    for cell in row {
        if let CellValue::Text(s) = cell {
            if !s.trim().is_empty() {
                *counts.entry(s.clone()).or_insert(0_usize) += 1;
            }
        }
    }
    let mut occurrences = HashMap::new();
    let mut names = Vec::new();
    let mut lookup = HashMap::new();
    for (i, cell) in row.iter().enumerate() {
        if let CellValue::Text(s) = cell {
            if s.trim().is_empty() {
                continue;
            }
            let occurrence = occurrences.entry(s.clone()).or_insert(0_usize);
            *occurrence += 1;
            let name = if counts[s] > 1 {
                format!("{s}_{occurrence}")
            } else {
                s.clone()
            };
            if lookup.insert(name.clone(), i).is_some() {
                return Err("Header nach Indizierung nicht eindeutig".into());
            }
            names.push((name, i));
        }
    }
    Ok((names, lookup))
}
