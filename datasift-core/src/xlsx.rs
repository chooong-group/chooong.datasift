//! Bounded-memory XLSX reader. Worksheet XML is parsed while it is decompressed.
//! Only the shared-string table and workbook metadata are materialized.
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::SyncSender;
use std::sync::Arc;

use quick_xml::events::{BytesStart, Event};
use quick_xml::Reader;
use zip::ZipArchive;

use crate::engine::{Sink, Statistics};
use crate::filter::{column_index, Config};
use crate::Message;

const MAX_XML_METADATA_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SHARED_STRINGS_BYTES: u64 = 512 * 1024 * 1024;
const MAX_CELL_TEXT_BYTES: usize = 2 * 1024 * 1024;
const MAX_COLS: usize = 16_384;
const MAX_ROWS: u32 = 1_048_576;

use crate::value::{CellValue, Merge};

/// quick-xml reports EOF even when enclosing tags remain open.
fn validate_depth(event: &Event<'_>, depth: &mut usize) -> Result<(), String> {
    match event {
        Event::Start(_) => {
            *depth += 1;
            if *depth > 128 {
                return Err("XML is nested too deeply".into());
            }
        }
        Event::End(_) => *depth = depth.checked_sub(1).ok_or("Unexpected XML end")?,
        Event::Eof if *depth != 0 => return Err("XML is incomplete".into()),
        _ => (),
    }
    Ok(())
}

fn xml_tag(name: &[u8]) -> &[u8] {
    name.rsplit(|byte| *byte == b':').next().unwrap_or(name)
}

fn attribute(element: &BytesStart<'_>, wanted: &[u8]) -> Result<Option<String>, String> {
    for item in element.attributes() {
        let item = item.map_err(|e| format!("Invalid XML attribute: {e}"))?;
        if item.key.as_ref() == wanted {
            return Ok(Some(
                item.unescape_value()
                    .map_err(|e| format!("Invalid XML attribute value: {e}"))?
                    .into_owned(),
            ));
        }
    }
    Ok(None)
}

fn append_text(target: &mut String, content: &str) -> Result<(), String> {
    if target.len().saturating_add(content.len()) > MAX_CELL_TEXT_BYTES {
        return Err("An Excel cell contains more than 2 MiB of text".into());
    }
    target.push_str(content);
    Ok(())
}

fn append_reference(target: &mut String, reference: &[u8]) -> Result<(), String> {
    let name = std::str::from_utf8(reference).map_err(|e| e.to_string())?;
    let replacement = match name {
        "amp" => '&',
        "lt" => '<',
        "gt" => '>',
        "quot" => '"',
        "apos" => '\'',
        name if name.starts_with("#x") || name.starts_with("#X") => {
            let value = u32::from_str_radix(&name[2..], 16)
                .map_err(|_| format!("Invalid XML reference: {name}"))?;
            char::from_u32(value).ok_or_else(|| format!("Invalid code point: {name}"))?
        }
        name if name.starts_with('#') => {
            let value = name[1..]
                .parse::<u32>()
                .map_err(|_| format!("Invalid XML reference: {name}"))?;
            char::from_u32(value).ok_or_else(|| format!("Invalid code point: {name}"))?
        }
        _ => return Err(format!("Unsupported XML entity: &{name};")),
    };
    if target.len().saturating_add(replacement.len_utf8()) > MAX_CELL_TEXT_BYTES {
        return Err("An Excel cell contains more than 2 MiB of text".into());
    }
    target.push(replacement);
    Ok(())
}

fn validate_declaration(event: &quick_xml::events::BytesDecl<'_>) -> Result<(), String> {
    if let Some(encoding) = event.encoding() {
        let encoding = encoding.map_err(|e| e.to_string())?;
        if !encoding.as_ref().eq_ignore_ascii_case(b"utf-8")
            && !encoding.as_ref().eq_ignore_ascii_case(b"utf8")
        {
            return Err(format!(
                "XML encoding {:?} is not supported (UTF-8 only)",
                String::from_utf8_lossy(encoding.as_ref())
            ));
        }
    }
    Ok(())
}

fn xml_part(archive: &mut ZipArchive<File>, name: &str, limit: u64) -> Result<Vec<u8>, String> {
    let mut member = archive
        .by_name(name)
        .map_err(|e| format!("Missing XLSX part {name:?}: {e}"))?;
    if member.size() > limit {
        return Err(format!("XLSX part {name:?} exceeds the size limit"));
    }
    let mut bytes = Vec::new();
    member
        .by_ref()
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("Error decompressing {name:?}: {e}"))?;
    if bytes.len() as u64 > limit {
        return Err(format!("XLSX part {name:?} exceeds the size limit"));
    }
    Ok(bytes)
}

fn safe_target(base: &str, target: &str) -> Result<String, String> {
    if target.contains('\\') || target.contains(':') || target.contains('\0') {
        return Err("Invalid or external XLSX target path".into());
    }
    let unnormalized = if let Some(target) = target.strip_prefix('/') {
        target.to_string()
    } else {
        format!("{base}{target}")
    };
    let mut segments: Vec<&str> = Vec::new();
    for segment in unnormalized.split('/') {
        match segment {
            "" | "." => (),
            ".." => {
                if segments.pop().is_none() {
                    return Err("XLSX path must not escape the archive".into());
                }
            }
            value => segments.push(value),
        }
    }
    if segments.is_empty() || segments.contains(&"..") {
        return Err("Invalid XLSX path".into());
    }
    Ok(segments.join("/"))
}

struct WorkbookPaths {
    worksheets: Vec<String>,
    shared_strings: Option<String>,
    date1904: bool,
    names: HashMap<String, String>,
    styles: Option<String>,
}

/// Resolve selected worksheets through OOXML relationships, preserving workbook order.
fn workbook_paths(
    archive: &mut ZipArchive<File>,
    sheet: Option<&str>,
) -> Result<WorkbookPaths, String> {
    let document = xml_part(archive, "xl/workbook.xml", MAX_XML_METADATA_BYTES)?;
    let mut reader = Reader::from_reader(document.as_slice());
    let mut buf = Vec::new();
    let mut depth = 0_usize;
    let mut relationship_ids = Vec::new();
    let mut available = Vec::new();
    let mut date1904 = false;
    let mut sheet_names = HashMap::new();

    loop {
        let event = reader
            .read_event_into(&mut buf)
            .map_err(|e| e.to_string())?;
        validate_depth(&event, &mut depth)?;
        match event {
            Event::Start(ref e) | Event::Empty(ref e) if xml_tag(e.name().as_ref()) == b"sheet" => {
                if let Some(name) = attribute(e, b"name")? {
                    if sheet.is_none_or(|selected| name == selected) {
                        relationship_ids
                            .push(attribute(e, b"r:id")?.ok_or("Worksheet without r:id")?);
                    }
                    if let Some(id) = attribute(e, b"r:id")? {
                        sheet_names.insert(id, name.clone());
                    }
                    available.push(name);
                }
            }
            Event::Start(ref e) | Event::Empty(ref e)
                if xml_tag(e.name().as_ref()) == b"workbookPr" =>
            {
                date1904 =
                    attribute(e, b"date1904")?.is_some_and(|s| matches!(s.as_str(), "1" | "true"));
            }
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD is not allowed in XLSX".into()),
            Event::Eof => break,
            _ => (),
        }
        buf.clear();
    }
    if sheet.is_some() && relationship_ids.is_empty() {
        return Err(format!(
            "Worksheet {sheet:?} does not exist. Available: {available:?}"
        ));
    }
    let selected_ids: HashSet<&str> = relationship_ids.iter().map(String::as_str).collect();

    let document = xml_part(
        archive,
        "xl/_rels/workbook.xml.rels",
        MAX_XML_METADATA_BYTES,
    )?;
    let mut reader = Reader::from_reader(document.as_slice());
    let mut buf = Vec::new();
    let mut depth = 0_usize;
    let mut by_id = HashMap::new();
    let mut shared_strings = None;
    let mut styles = None;

    loop {
        let event = reader
            .read_event_into(&mut buf)
            .map_err(|e| e.to_string())?;
        validate_depth(&event, &mut depth)?;
        match event {
            Event::Start(ref e) | Event::Empty(ref e)
                if xml_tag(e.name().as_ref()) == b"Relationship" =>
            {
                let id = attribute(e, b"Id")?;
                let kind = attribute(e, b"Type")?.unwrap_or_default();
                let target = attribute(e, b"Target")?.unwrap_or_default();
                let target_mode = attribute(e, b"TargetMode")?;
                if target_mode.as_deref() == Some("External") {
                    if id.as_deref().is_some_and(|id| selected_ids.contains(id)) {
                        return Err("External worksheet is not supported".into());
                    }
                    continue;
                }
                if let Some(id) = id.filter(|id| selected_ids.contains(id.as_str())) {
                    let worksheet = if kind.ends_with("/worksheet") {
                        Some(safe_target("xl/", &target)?)
                    } else if sheet.is_some() {
                        return Err("The sheet relationship is not a worksheet".into());
                    } else {
                        None // Chartsheets have no worksheet rows to search.
                    };
                    if by_id.insert(id, worksheet).is_some() {
                        return Err("Duplicate workbook relationship".into());
                    }
                }
                if kind.ends_with("/styles") {
                    styles = Some(safe_target("xl/", &target)?);
                }
                if kind.ends_with("/sharedStrings") {
                    shared_strings = Some(safe_target("xl/", &target)?);
                }
            }
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD is not allowed in XLSX".into()),
            Event::Eof => break,
            _ => (),
        }
        buf.clear();
    }
    let mut worksheets = Vec::new();
    let mut names = HashMap::new();
    for id in &relationship_ids {
        if let Some(path) = by_id.remove(id).ok_or("Worksheet relationship not found")? {
            names.insert(
                path.clone(),
                sheet_names.get(id).cloned().unwrap_or_default(),
            );
            worksheets.push(path);
        }
    }
    Ok(WorkbookPaths {
        worksheets,
        shared_strings,
        date1904,
        names,
        styles,
    })
}

fn load_shared_strings(
    archive: &mut ZipArchive<File>,
    path: Option<&str>,
) -> Result<Vec<String>, String> {
    let name = path.unwrap_or("xl/sharedStrings.xml");
    let member = match archive.by_name(name) {
        Ok(member) => member,
        Err(zip::result::ZipError::FileNotFound) if path.is_none() => return Ok(Vec::new()),
        Err(err) => return Err(format!("Cannot read sharedStrings.xml: {err}")),
    };
    if member.size() > MAX_SHARED_STRINGS_BYTES {
        return Err("sharedStrings.xml exceeds 512 MiB (memory limit)".into());
    }
    let mut reader = Reader::from_reader(BufReader::new(member));
    let mut buf = Vec::new();
    let mut depth = 0_usize;
    let mut strings = Vec::new();
    let mut current = String::new();
    let mut in_si = false;
    let mut in_t = false;
    let mut in_phonetic = false;

    loop {
        if reader.buffer_position() > MAX_SHARED_STRINGS_BYTES {
            return Err("sharedStrings XML exceeds 512 MiB (memory limit)".into());
        }
        let event = reader
            .read_event_into(&mut buf)
            .map_err(|e| format!("sharedStrings XML: {e}"))?;
        validate_depth(&event, &mut depth)?;
        match event {
            Event::Start(ref e) => match xml_tag(e.name().as_ref()) {
                b"si" => {
                    in_si = true;
                    current.clear();
                }
                b"rPh" if in_si => in_phonetic = true,
                b"t" if in_si && !in_phonetic => in_t = true,
                _ => (),
            },
            Event::Empty(ref e) if xml_tag(e.name().as_ref()) == b"si" => {
                strings.push(String::new())
            }
            Event::End(ref e) => match xml_tag(e.name().as_ref()) {
                b"t" => in_t = false,
                b"rPh" => in_phonetic = false,
                b"si" => {
                    strings.push(std::mem::take(&mut current));
                    in_si = false;
                }
                _ => (),
            },
            Event::Text(ref e) if in_t => {
                append_text(&mut current, &e.xml10_content().map_err(|e| e.to_string())?)?
            }
            Event::CData(ref e) if in_t => {
                append_text(&mut current, &e.xml10_content().map_err(|e| e.to_string())?)?
            }
            Event::GeneralRef(ref e) if in_t => append_reference(&mut current, e.as_ref())?,
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD is not allowed in XLSX".into()),
            Event::Eof => {
                if in_si {
                    return Err("sharedStrings.xml ends inside an <si>".into());
                }
                break;
            }
            _ => (),
        }
        buf.clear();
    }
    Ok(strings)
}

fn column_from_cell_reference(reference: &str) -> Result<usize, String> {
    let bytes = reference.as_bytes();
    let letters = bytes
        .iter()
        .take_while(|byte| byte.is_ascii_alphabetic())
        .count();
    if letters == 0 || letters == bytes.len() || !bytes[letters..].iter().all(u8::is_ascii_digit) {
        return Err(format!("Invalid cell reference: {reference:?}"));
    }
    column_index(&reference[..letters].to_ascii_uppercase())
}

pub(crate) struct RawCell<'a> {
    pub kind: &'a str,
    pub value: &'a str,
    pub inline: &'a str,
    pub style: usize,
}

impl Sink<'_> {
    pub fn read_cell(
        &self,
        row: u32,
        col: usize,
        cell: crate::xlsx::RawCell<'_>,
        strings: &[String],
    ) -> Result<Option<CellValue>, String> {
        let crate::xlsx::RawCell {
            kind,
            value,
            inline,
            style,
        } = cell;
        if self.selects_cell(row, col) {
            if matches!(kind, "n" | "")
                && !value.trim().is_empty()
                && (!self.config.rules.types.is_empty()
                    || self.needs_exact_numbers()
                    || self.styles.get(style).is_some_and(|f| !f.is_empty()))
            {
                // Validate syntax, retain the original OOXML decimal lexeme.
                crate::xlsx::finish_cell(kind, value, inline, strings)?;
                let raw = value.trim().to_owned();
                if let Some(format) = self.styles.get(style).filter(|f| !f.is_empty()) {
                    return Ok(Some(CellValue::StyledNumber {
                        raw,
                        format: format.clone(),
                    }));
                }
                return Ok(Some(CellValue::NumberText(raw)));
            }
            return crate::xlsx::finish_cell(kind, value, inline, strings).map(Some);
        }
        if self.config.source.is_some() || self.config.sources.is_some() {
            return Ok(None);
        }
        let label = match kind {
            "inlineStr" => Some(inline),
            "s" => value
                .trim()
                .parse::<usize>()
                .ok()
                .and_then(|i| strings.get(i))
                .map(String::as_str),
            "str" | "e" | "d" => Some(value),
            _ => None,
        };
        let h = &self.config.rules.header;
        Ok(label
            .filter(|l| self.config.header_labels.contains(&h.normalize(l)))
            .map(|l| CellValue::Text(l.to_owned())))
    }
}

pub(crate) fn finish_cell(
    kind: &str,
    value: &str,
    inline: &str,
    strings: &[String],
) -> Result<CellValue, String> {
    let raw = value.trim();
    match kind {
        "inlineStr" => Ok(CellValue::Text(inline.to_string())),
        "s" => {
            if raw.is_empty() {
                return Ok(CellValue::Empty);
            }
            let idx: usize = raw.parse().map_err(|_| "Invalid shared string index")?;
            strings
                .get(idx)
                .cloned()
                .map(CellValue::Text)
                .ok_or_else(|| format!("Shared string index {idx} does not exist"))
        }
        "d" => Ok(if value.is_empty() {
            CellValue::Empty
        } else {
            CellValue::IsoDate(value.to_owned())
        }),
        "str" | "e" => {
            if value.is_empty() {
                Ok(CellValue::Empty)
            } else {
                Ok(CellValue::Text(value.to_string()))
            }
        }
        "b" => match raw {
            "1" | "true" => Ok(CellValue::Bool(true)),
            "0" | "false" => Ok(CellValue::Bool(false)),
            "" => Ok(CellValue::Empty),
            _ => Err(format!("Invalid boolean value {raw:?}")),
        },
        "" | "n" => CellValue::number(raw),
        other => Err(format!("Unsupported Excel cell type {other:?}")),
    }
}

fn load_styles(archive: &mut ZipArchive<File>, path: Option<&str>) -> Result<Vec<String>, String> {
    let name = path.unwrap_or("xl/styles.xml");
    if path.is_none() && archive.by_name(name).is_err() {
        return Ok(vec![]);
    }
    let xml = xml_part(archive, name, MAX_XML_METADATA_BYTES)?;
    let mut reader = Reader::from_reader(xml.as_slice());
    let mut buf = Vec::new();
    let mut depth = 0;
    let mut formats = HashMap::new();
    let mut styles = Vec::new();
    let mut in_xfs = false;
    loop {
        let e = reader
            .read_event_into(&mut buf)
            .map_err(|_| "Invalid styles.xml")?;
        validate_depth(&e, &mut depth)?;
        match e {
            Event::Start(ref e) if xml_tag(e.name().as_ref()) == b"cellXfs" => in_xfs = true,
            Event::End(ref e) if xml_tag(e.name().as_ref()) == b"cellXfs" => in_xfs = false,
            Event::Empty(ref e) | Event::Start(ref e)
                if xml_tag(e.name().as_ref()) == b"numFmt" =>
            {
                if let (Some(id), Some(code)) =
                    (attribute(e, b"numFmtId")?, attribute(e, b"formatCode")?)
                {
                    formats.insert(id, code);
                }
            }
            Event::Empty(ref e) | Event::Start(ref e)
                if in_xfs && xml_tag(e.name().as_ref()) == b"xf" =>
            {
                let id = attribute(e, b"numFmtId")?.unwrap_or_default();
                let builtin = match id.as_str() {
                    "14" | "15" | "16" | "17" => "yyyy-mm-dd",
                    "18" | "19" | "20" | "21" | "22" => "yyyy-mm-dd hh:mm:ss",
                    "45" | "46" | "47" => "hh:mm:ss",
                    "5" | "6" | "7" | "8" | "42" | "44" => "currency",
                    _ => "",
                };
                styles.push(
                    formats
                        .get(&id)
                        .cloned()
                        .unwrap_or_else(|| builtin.to_owned()),
                );
            }
            Event::DocType(_) => return Err("DTD is not allowed".into()),
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::Eof => break,
            _ => (),
        }
        buf.clear();
    }
    Ok(styles)
}
fn load_merges(archive: &mut ZipArchive<File>, worksheet: &str) -> Result<Vec<Merge>, String> {
    let member = archive
        .by_name(worksheet)
        .map_err(|_| "Missing worksheet")?;
    let mut reader = Reader::from_reader(BufReader::new(member));
    let mut buf = Vec::new();
    let mut result = Vec::new();
    let mut depth = 0;
    loop {
        let e = reader
            .read_event_into(&mut buf)
            .map_err(|_| "Invalid worksheet XML")?;
        validate_depth(&e, &mut depth)?;
        match e {
            Event::Empty(ref e) | Event::Start(ref e)
                if xml_tag(e.name().as_ref()) == b"mergeCell" =>
            {
                if result.len() >= 16384 {
                    return Err("Too many merged ranges".into());
                }
                let reference = attribute(e, b"ref")?.ok_or("Merge without ref")?;
                let (first, last) = reference.split_once(':').ok_or("Invalid merge")?;
                fn row(s: &str) -> Result<u32, String> {
                    s.trim_start_matches(|c: char| c.is_ascii_uppercase())
                        .parse()
                        .map_err(|_| "Invalid merge row".into())
                }
                let m = Merge {
                    first_col: column_from_cell_reference(first)?,
                    last_col: column_from_cell_reference(last)?,
                    first_row: row(first)?,
                    last_row: row(last)?,
                };
                if m.first_col > m.last_col || m.first_row > m.last_row || m.last_row > MAX_ROWS {
                    return Err("Invalid merged range".into());
                }
                result.push(m);
            }
            Event::Eof => break,
            Event::DocType(_) => return Err("DTD is not allowed".into()),
            _ => (),
        }
        buf.clear();
    }
    Ok(result)
}

/// This entire function runs on a dedicated Rust thread; ZipArchive and borrowed
/// worksheet ZipFile never escape it. Bounded channels prevent unbounded buffering.
#[allow(clippy::too_many_arguments)]
pub fn scan(
    path: &Path,
    config: &Config,
    batch_size: usize,
    sender: &SyncSender<Message>,
    cancelled: &Arc<AtomicBool>,
    events: bool,
    rejects: bool,
    stats: &mut Statistics,
) -> Result<(), String> {
    let input = File::open(path).map_err(|e| format!("Cannot open XLSX: {e}"))?;
    let mut archive = ZipArchive::new(input).map_err(|e| format!("Invalid XLSX/ZIP: {e}"))?;
    let paths = workbook_paths(&mut archive, config.sheet.as_deref())?;
    let styles = load_styles(&mut archive, paths.styles.as_deref())?;
    let shared = load_shared_strings(&mut archive, paths.shared_strings.as_deref())?;
    if config.sheet.is_none() {
        sender
            .send(Message::Ready(Vec::new()))
            .map_err(|_| "The Python consumer was closed".to_string())?;
    }
    for worksheet in paths.worksheets {
        if cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        let mut sink = Sink::new(
            config,
            sender,
            cancelled,
            batch_size,
            events,
            rejects,
            path.to_string_lossy().into_owned(),
            paths
                .names
                .get(&worksheet)
                .cloned()
                .unwrap_or_else(|| worksheet.clone()),
            paths.date1904,
            stats,
        );
        sink.initialize()?;
        let merges = if config.rules.header.merged_fill
            || config
                .source
                .iter()
                .chain(config.sources.iter().flatten())
                .any(|s| s.rules.as_ref().is_some_and(|r| r.header.merged_fill))
        {
            load_merges(&mut archive, &worksheet)?
        } else {
            Vec::new()
        };
        sink.merges = merges;
        sink.styles = styles.clone();
        scan_worksheet(&mut archive, &worksheet, &shared, &mut sink)?;
        if !sink.has_headers() {
            sink.diagnostic("NO_SCHEMA", None)?;
        }
    }
    Ok(())
}

fn scan_worksheet(
    archive: &mut ZipArchive<File>,
    worksheet: &str,
    shared: &[String],
    sink: &mut Sink<'_>,
) -> Result<(), String> {
    let member = archive
        .by_name(worksheet)
        .map_err(|e| format!("Missing worksheet XML {worksheet:?}: {e}"))?;
    let mut reader = Reader::from_reader(BufReader::with_capacity(128 * 1024, member));
    let mut buf = Vec::new();
    let mut depth = 0_usize;

    let mut row = Vec::new();
    let mut in_sheet_data = false;
    let mut in_row = false;
    let mut in_cell = false;
    let mut in_inline = false;
    let mut in_phonetic = false;
    let mut field = Field::None;
    let mut cell_kind = String::new();
    let mut style = 0_usize;
    let mut raw_value = String::new();
    let mut inline_value = String::new();
    let mut cell_col = 0_usize;
    let mut next_cell_col = 0_usize;
    let mut row_num = 0_u32;
    let mut last_row = 0_u32;

    loop {
        if sink.cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        let event = reader.read_event_into(&mut buf).map_err(|e| {
            format!(
                "Invalid worksheet XML (Byte {}): {e}",
                reader.error_position()
            )
        })?;
        validate_depth(&event, &mut depth)?;
        match event {
            Event::Start(ref e) => match xml_tag(e.name().as_ref()) {
                b"sheetData" => in_sheet_data = true,
                b"row" if in_sheet_data => {
                    if in_row {
                        return Err("Nested <row> elements".into());
                    }
                    row_num = match attribute(e, b"r")? {
                        Some(value) => value
                            .parse::<u32>()
                            .map_err(|_| "Invalid Excel row number")?,
                        None => last_row.checked_add(1).ok_or("Too many Excel rows")?,
                    };
                    if row_num <= last_row || row_num > MAX_ROWS {
                        return Err(format!("Invalid or unsorted Excel row {row_num}"));
                    }
                    in_row = true;
                    row.clear();
                    next_cell_col = 0;
                }
                b"c" if in_row => {
                    if in_cell {
                        return Err("Nested <c> elements".into());
                    }
                    start_cell(e, row_num, next_cell_col, &mut cell_col, &mut cell_kind)?;
                    if cell_col < next_cell_col {
                        return Err("Duplicate or unsorted cells in an Excel row".into());
                    }
                    next_cell_col = cell_col + 1;
                    style = attribute(e, b"s")?
                        .map(|s| s.parse::<usize>().map_err(|_| "Invalid cell style"))
                        .transpose()?
                        .unwrap_or(0);
                    raw_value.clear();
                    inline_value.clear();
                    in_cell = true;
                    in_inline = false;
                    field = Field::None;
                }
                b"is" if in_cell => in_inline = true,
                b"rPh" if in_inline => in_phonetic = true,
                b"v" if in_cell => field = Field::Value,
                b"t" if in_inline && !in_phonetic => field = Field::Inline,
                _ => (),
            },
            Event::Empty(ref e) => match xml_tag(e.name().as_ref()) {
                b"row" if in_sheet_data => {
                    let number: u32 = match attribute(e, b"r")? {
                        Some(value) => value.parse().map_err(|_| "Invalid Excel row number")?,
                        None => last_row.checked_add(1).ok_or("Too many Excel rows")?,
                    };
                    if number <= last_row || number > MAX_ROWS {
                        return Err("Invalid empty Excel row".into());
                    }
                    sink.on_row(number, Vec::new())?;
                    last_row = number;
                }
                b"c" if in_row => {
                    start_cell(e, row_num, next_cell_col, &mut cell_col, &mut cell_kind)?;
                    if cell_col < next_cell_col {
                        return Err("Unsorted Excel cell".into());
                    }
                    next_cell_col = cell_col + 1;
                    if sink.selects_cell(row_num, cell_col) {
                        put_cell(&mut row, cell_col, CellValue::Empty)?;
                    }
                }
                _ => (),
            },
            Event::Text(ref text) => match field {
                Field::Value => append_text(
                    &mut raw_value,
                    &text.xml10_content().map_err(|e| e.to_string())?,
                )?,
                Field::Inline => append_text(
                    &mut inline_value,
                    &text.xml10_content().map_err(|e| e.to_string())?,
                )?,
                Field::None => (),
            },
            Event::CData(ref text) => match field {
                Field::Value => append_text(
                    &mut raw_value,
                    &text.xml10_content().map_err(|e| e.to_string())?,
                )?,
                Field::Inline => append_text(
                    &mut inline_value,
                    &text.xml10_content().map_err(|e| e.to_string())?,
                )?,
                Field::None => (),
            },
            Event::GeneralRef(ref reference) => match field {
                Field::Value => append_reference(&mut raw_value, reference.as_ref())?,
                Field::Inline => append_reference(&mut inline_value, reference.as_ref())?,
                Field::None => (),
            },
            Event::End(ref e) => match xml_tag(e.name().as_ref()) {
                b"v" | b"t" => field = Field::None,
                b"rPh" => in_phonetic = false,
                b"is" => in_inline = false,
                b"c" if in_cell => {
                    if let Some(value) = sink
                        .read_cell(
                            row_num,
                            cell_col,
                            RawCell {
                                kind: &cell_kind,
                                value: &raw_value,
                                inline: &inline_value,
                                style,
                            },
                            shared,
                        )
                        .map_err(|error| {
                            format!("Excel row {row_num}, column {}: {error}", cell_col + 1)
                        })?
                    {
                        put_cell(&mut row, cell_col, value)?;
                    }
                    in_cell = false;
                    field = Field::None;
                }
                b"row" if in_row => {
                    if in_cell {
                        return Err("Unclosed Excel cell".into());
                    }
                    sink.on_row(row_num, std::mem::take(&mut row))?;
                    last_row = row_num;
                    in_row = false;
                }
                b"sheetData" => in_sheet_data = false,
                _ => (),
            },
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD is not allowed in XLSX".into()),
            Event::Eof => {
                if in_row || in_cell {
                    return Err("Worksheet XML is incomplete".into());
                }
                sink.finish()?;
                if !sink.has_headers() && sink.config.sheet.is_some() && !sink.stats.schema_errors {
                    return Err(
                        "No header containing all mask columns found (Unknown column)".into(),
                    );
                }
                return Ok(());
            }
            _ => (),
        }
        buf.clear();
    }
}

#[derive(Clone, Copy)]
enum Field {
    None,
    Value,
    Inline,
}

fn start_cell(
    e: &BytesStart<'_>,
    expected_row: u32,
    next_col: usize,
    col: &mut usize,
    kind: &mut String,
) -> Result<(), String> {
    *col = match attribute(e, b"r")? {
        Some(reference) => {
            let index = column_from_cell_reference(&reference)?;
            let digit_start = reference
                .as_bytes()
                .iter()
                .take_while(|byte| byte.is_ascii_alphabetic())
                .count();
            let cell_row = reference[digit_start..]
                .parse::<u32>()
                .map_err(|_| "Invalid cell row number")?;
            if cell_row != expected_row {
                return Err(format!(
                    "Cell reference {reference:?} is not in Excel row {expected_row}"
                ));
            }
            index
        }
        None => next_col,
    };
    if *col >= MAX_COLS {
        return Err("More than 16384 columns in an Excel row".into());
    }
    *kind = attribute(e, b"t")?.unwrap_or_else(|| "n".into());
    Ok(())
}

fn put_cell(row: &mut Vec<CellValue>, col: usize, value: CellValue) -> Result<(), String> {
    if row.len() <= col {
        row.resize(col + 1, CellValue::Empty);
    }
    if row[col] != CellValue::Empty {
        return Err("Duplicate Excel cell".into());
    }
    row[col] = value;
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/xlsx.rs"]
mod tests;
