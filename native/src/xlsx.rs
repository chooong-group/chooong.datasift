//! Bounded-memory XLSX reader. Worksheet XML is parsed while it is decompressed.
//! Only the shared-string table and workbook metadata are materialized.
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::SyncSender;
use std::sync::Arc;

use quick_xml::events::{BytesStart, Event};
use quick_xml::Reader;
use zip::ZipArchive;

use crate::filter::{headers_from_row, Config, Expr};
use crate::Message;

const MAX_XML_METADATA_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SHARED_STRINGS_BYTES: u64 = 512 * 1024 * 1024;
const MAX_CELL_TEXT_BYTES: usize = 2 * 1024 * 1024;
const MAX_COLS: usize = 16_384;
const MAX_ROWS: u32 = 1_048_576;

use crate::value::CellValue;

/// quick-xml reports EOF even when enclosing tags remain open.
fn validate_depth(event: &Event<'_>, depth: &mut usize) -> Result<(), String> {
    match event {
        Event::Start(_) => {
            *depth += 1;
            if *depth > 128 {
                return Err("XML ist zu tief verschachtelt".into());
            }
        }
        Event::End(_) => *depth = depth.checked_sub(1).ok_or("Unerwartetes XML-Ende")?,
        Event::Eof if *depth != 0 => return Err("XML ist unvollständig".into()),
        _ => (),
    }
    Ok(())
}

fn xml_tag(name: &[u8]) -> &[u8] {
    name.rsplit(|byte| *byte == b':').next().unwrap_or(name)
}

fn attribute(element: &BytesStart<'_>, wanted: &[u8]) -> Result<Option<String>, String> {
    for item in element.attributes() {
        let item = item.map_err(|e| format!("Ungültiges XML-Attribut: {e}"))?;
        if item.key.as_ref() == wanted {
            return Ok(Some(
                item.unescape_value()
                    .map_err(|e| format!("Ungültiger XML-Attributwert: {e}"))?
                    .into_owned(),
            ));
        }
    }
    Ok(None)
}

fn append_text(target: &mut String, fragment: &[u8]) -> Result<(), String> {
    let content = std::str::from_utf8(fragment).map_err(|e| format!("Nicht-UTF-8 XML: {e}"))?;
    if target.len().saturating_add(content.len()) > MAX_CELL_TEXT_BYTES {
        return Err("Eine Excel-Zelle enthält mehr als 2 MiB Text".into());
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
                .map_err(|_| format!("Ungültige XML-Referenz: {name}"))?;
            char::from_u32(value).ok_or_else(|| format!("Ungültiger Codepoint: {name}"))?
        }
        name if name.starts_with('#') => {
            let value = name[1..]
                .parse::<u32>()
                .map_err(|_| format!("Ungültige XML-Referenz: {name}"))?;
            char::from_u32(value).ok_or_else(|| format!("Ungültiger Codepoint: {name}"))?
        }
        _ => return Err(format!("Nicht unterstützte XML-Entity: &{name};")),
    };
    if target.len().saturating_add(replacement.len_utf8()) > MAX_CELL_TEXT_BYTES {
        return Err("Eine Excel-Zelle enthält mehr als 2 MiB Text".into());
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
                "XML-Encoding {:?} wird nicht unterstützt (nur UTF-8)",
                String::from_utf8_lossy(encoding.as_ref())
            ));
        }
    }
    Ok(())
}

fn xml_part(archive: &mut ZipArchive<File>, name: &str, limit: u64) -> Result<Vec<u8>, String> {
    let mut member = archive
        .by_name(name)
        .map_err(|e| format!("Fehlender XLSX-Bestandteil {name:?}: {e}"))?;
    if member.size() > limit {
        return Err(format!(
            "XLSX-Bestandteil {name:?} überschreitet das Größenlimit"
        ));
    }
    let mut bytes = Vec::new();
    member
        .by_ref()
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("Fehler beim Entpacken von {name:?}: {e}"))?;
    if bytes.len() as u64 > limit {
        return Err(format!(
            "XLSX-Bestandteil {name:?} überschreitet das Größenlimit"
        ));
    }
    Ok(bytes)
}

fn safe_target(base: &str, target: &str) -> Result<String, String> {
    if target.contains('\\') || target.contains(':') || target.contains('\0') {
        return Err("Ungültiger oder externer XLSX-Zielpfad".into());
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
                    return Err("XLSX-Pfad darf nicht aus dem Archiv ausbrechen".into());
                }
            }
            value => segments.push(value),
        }
    }
    if segments.is_empty() || segments.contains(&"..") {
        return Err("Ungültiger XLSX-Pfad".into());
    }
    Ok(segments.join("/"))
}

/// Find a worksheet by its *name*, through OOXML relationship IDs (never guess sheet1.xml).
fn workbook_paths(
    archive: &mut ZipArchive<File>,
    sheet: &str,
) -> Result<(String, Option<String>), String> {
    let document = xml_part(archive, "xl/workbook.xml", MAX_XML_METADATA_BYTES)?;
    let mut reader = Reader::from_reader(document.as_slice());
    let mut buf = Vec::new();
    let mut depth = 0_usize;
    let mut relationship_id = None;
    let mut available = Vec::new();

    loop {
        let event = reader
            .read_event_into(&mut buf)
            .map_err(|e| e.to_string())?;
        validate_depth(&event, &mut depth)?;
        match event {
            Event::Start(ref e) | Event::Empty(ref e) if xml_tag(e.name().as_ref()) == b"sheet" => {
                if let Some(name) = attribute(e, b"name")? {
                    if name == sheet {
                        relationship_id = attribute(e, b"r:id")?;
                        if relationship_id.is_none() {
                            return Err(format!("Arbeitsblatt {sheet:?} ohne r:id"));
                        }
                    }
                    available.push(name);
                }
            }
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD ist in XLSX nicht erlaubt".into()),
            Event::Eof => break,
            _ => (),
        }
        buf.clear();
    }
    let relationship_id = relationship_id.ok_or_else(|| {
        format!("Arbeitsblatt {sheet:?} nicht vorhanden. Verfügbar: {available:?}")
    })?;

    let document = xml_part(
        archive,
        "xl/_rels/workbook.xml.rels",
        MAX_XML_METADATA_BYTES,
    )?;
    let mut reader = Reader::from_reader(document.as_slice());
    let mut buf = Vec::new();
    let mut depth = 0_usize;
    let mut worksheet = None;
    let mut shared_strings = None;

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
                    if id == Some(relationship_id.clone()) {
                        return Err("Externes Arbeitsblatt wird nicht unterstützt".into());
                    }
                    continue;
                }
                if id.as_deref() == Some(relationship_id.as_str()) {
                    if !kind.ends_with("/worksheet") {
                        return Err("Die Tabellen-Relation ist kein worksheet".into());
                    }
                    worksheet = Some(safe_target("xl/", &target)?);
                }
                if kind.ends_with("/sharedStrings") {
                    shared_strings = Some(safe_target("xl/", &target)?);
                }
            }
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD ist in XLSX nicht erlaubt".into()),
            Event::Eof => break,
            _ => (),
        }
        buf.clear();
    }
    let worksheet = worksheet.ok_or("Worksheet-Relation nicht gefunden")?;
    Ok((worksheet, shared_strings))
}

fn load_shared_strings(
    archive: &mut ZipArchive<File>,
    path: Option<&str>,
) -> Result<Vec<String>, String> {
    let name = path.unwrap_or("xl/sharedStrings.xml");
    let member = match archive.by_name(name) {
        Ok(member) => member,
        Err(zip::result::ZipError::FileNotFound) if path.is_none() => return Ok(Vec::new()),
        Err(err) => return Err(format!("sharedStrings.xml nicht lesbar: {err}")),
    };
    if member.size() > MAX_SHARED_STRINGS_BYTES {
        return Err("sharedStrings.xml überschreitet 512 MiB (RAM-Schutz)".into());
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
            return Err("sharedStrings XML überschreitet 512 MiB (RAM-Schutz)".into());
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
            Event::Text(ref e) if in_t => append_text(&mut current, e.as_ref())?,
            Event::CData(ref e) if in_t => append_text(&mut current, e.as_ref())?,
            Event::GeneralRef(ref e) if in_t => append_reference(&mut current, e.as_ref())?,
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD ist in XLSX nicht erlaubt".into()),
            Event::Eof => {
                if in_si {
                    return Err("sharedStrings.xml endet innerhalb eines <si>".into());
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
        return Err(format!("Ungültige Zellreferenz: {reference:?}"));
    }
    let mut number: usize = 0;
    for letter in &bytes[..letters] {
        number = number * 26 + (letter.to_ascii_uppercase() - b'A' + 1) as usize;
        if number > MAX_COLS {
            return Err("Zellreferenz liegt außerhalb von XFD".into());
        }
    }
    Ok(number - 1)
}

fn finish_cell(
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
            let idx: usize = raw.parse().map_err(|_| "Ungültiger Shared-String-Index")?;
            strings
                .get(idx)
                .cloned()
                .map(CellValue::Text)
                .ok_or_else(|| format!("Shared-String-Index {idx} ist nicht vorhanden"))
        }
        "str" | "e" | "d" => {
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
            _ => Err(format!("Ungültiger Bool-Wert {raw:?}")),
        },
        "" | "n" => {
            if raw.is_empty() {
                return Ok(CellValue::Empty);
            }
            if let Ok(integer) = raw.parse::<i64>() {
                return Ok(CellValue::Integer(integer));
            }
            let number = raw
                .parse::<f64>()
                .map_err(|_| format!("Ungültiger Excel-Zahlenwert {raw:?}"))?;
            if !number.is_finite() {
                return Err("Nicht-endlicher Excel-Zahlenwert".into());
            }
            Ok(CellValue::Float(number))
        }
        other => Err(format!("Nicht unterstützter Excel-Zelltyp {other:?}")),
    }
}

struct Sink<'a> {
    config: &'a Config,
    sender: &'a SyncSender<Message>,
    cancelled: &'a Arc<AtomicBool>,
    batch_size: usize,
    headers: Option<Vec<(String, usize)>>,
    predicate: Option<Expr>,
    buffer: Vec<Vec<CellValue>>,
}

impl Sink<'_> {
    fn on_row(&mut self, number: u32, row: Vec<CellValue>) -> Result<(), String> {
        if self.cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        if number < self.config.header_row {
            return Ok(());
        }
        if number == self.config.header_row {
            if self.headers.is_some() {
                return Err("Doppelte Kopfzeile".into());
            }
            let (names, lookup) = headers_from_row(&row)?;
            let predicate = Expr::compile(&self.config.predicate, &lookup)?;
            self.sender
                .send(Message::Ready(names.clone()))
                .map_err(|_| "Der Python-Verbraucher wurde geschlossen".to_string())?;
            self.headers = Some(names);
            self.predicate = Some(predicate);
            return Ok(());
        }
        let predicate = self
            .predicate
            .as_ref()
            .ok_or("Die angegebene Kopfzeile fehlt")?;
        if !predicate.matches(&row) {
            return Ok(());
        }
        self.buffer.push(row);
        if self.buffer.len() >= self.batch_size {
            self.flush()?;
        }
        Ok(())
    }

    fn flush(&mut self) -> Result<(), String> {
        if !self.buffer.is_empty() {
            self.sender
                .send(Message::Batch(std::mem::take(&mut self.buffer)))
                .map_err(|_| "Der Python-Verbraucher wurde geschlossen".to_string())?;
        }
        Ok(())
    }
}

/// This entire function runs on a dedicated Rust thread; ZipArchive and borrowed
/// worksheet ZipFile never escape it. Bounded channels prevent unbounded buffering.
pub fn scan(
    path: &Path,
    config: &Config,
    batch_size: usize,
    sender: &SyncSender<Message>,
    cancelled: &Arc<AtomicBool>,
) -> Result<(), String> {
    let input = File::open(path).map_err(|e| format!("Kann XLSX nicht öffnen: {e}"))?;
    let mut archive = ZipArchive::new(input).map_err(|e| format!("Ungültiges XLSX/ZIP: {e}"))?;
    let (worksheet, shared_path) = workbook_paths(&mut archive, &config.sheet)?;
    let shared = load_shared_strings(&mut archive, shared_path.as_deref())?;

    let member = archive
        .by_name(&worksheet)
        .map_err(|e| format!("Arbeitsblatt-XML {worksheet:?} fehlt: {e}"))?;
    let mut reader = Reader::from_reader(BufReader::with_capacity(128 * 1024, member));
    let mut buf = Vec::new();
    let mut depth = 0_usize;
    let mut sink = Sink {
        config,
        sender,
        cancelled,
        batch_size,
        headers: None,
        predicate: None,
        buffer: Vec::with_capacity(batch_size),
    };

    let mut row = Vec::new();
    let mut in_sheet_data = false;
    let mut in_row = false;
    let mut in_cell = false;
    let mut in_inline = false;
    let mut in_phonetic = false;
    let mut field = Field::None;
    let mut cell_kind = String::new();
    let mut raw_value = String::new();
    let mut inline_value = String::new();
    let mut cell_col = 0_usize;
    let mut next_cell_col = 0_usize;
    let mut row_num = 0_u32;
    let mut last_row = 0_u32;

    loop {
        if cancelled.load(Ordering::Relaxed) {
            return Ok(());
        }
        let event = reader.read_event_into(&mut buf).map_err(|e| {
            format!(
                "Ungültiges Tabellen-XML (Byte {}): {e}",
                reader.error_position()
            )
        })?;
        validate_depth(&event, &mut depth)?;
        match event {
            Event::Start(ref e) => match xml_tag(e.name().as_ref()) {
                b"sheetData" => in_sheet_data = true,
                b"row" if in_sheet_data => {
                    if in_row {
                        return Err("Verschachtelte <row>-Elemente".into());
                    }
                    row_num = match attribute(e, b"r")? {
                        Some(value) => value
                            .parse::<u32>()
                            .map_err(|_| "Ungültige Excel-Zeilennummer")?,
                        None => last_row.checked_add(1).ok_or("Zu viele Excel-Zeilen")?,
                    };
                    if row_num <= last_row || row_num > MAX_ROWS {
                        return Err(format!("Ungültige oder unsortierte Excel-Zeile {row_num}"));
                    }
                    in_row = true;
                    row.clear();
                    next_cell_col = 0;
                }
                b"c" if in_row => {
                    if in_cell {
                        return Err("Verschachtelte <c>-Elemente".into());
                    }
                    start_cell(e, row_num, next_cell_col, &mut cell_col, &mut cell_kind)?;
                    if cell_col < next_cell_col {
                        return Err("Doppelte oder unsortierte Zellen in einer Excel-Zeile".into());
                    }
                    next_cell_col = cell_col + 1;
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
                        Some(value) => value.parse().map_err(|_| "Ungültige Excel-Zeilennummer")?,
                        None => last_row.checked_add(1).ok_or("Zu viele Excel-Zeilen")?,
                    };
                    if number <= last_row || number > MAX_ROWS {
                        return Err("Ungültige leere Excel-Zeile".into());
                    }
                    sink.on_row(number, Vec::new())?;
                    last_row = number;
                }
                b"c" if in_row => {
                    start_cell(e, row_num, next_cell_col, &mut cell_col, &mut cell_kind)?;
                    if cell_col < next_cell_col {
                        return Err("Unsortierte Excel-Zelle".into());
                    }
                    next_cell_col = cell_col + 1;
                    put_cell(&mut row, cell_col, CellValue::Empty)?;
                }
                _ => (),
            },
            Event::Text(ref text) => match field {
                Field::Value => append_text(&mut raw_value, text.as_ref())?,
                Field::Inline => append_text(&mut inline_value, text.as_ref())?,
                Field::None => (),
            },
            Event::CData(ref text) => match field {
                Field::Value => append_text(&mut raw_value, text.as_ref())?,
                Field::Inline => append_text(&mut inline_value, text.as_ref())?,
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
                    let value = finish_cell(&cell_kind, &raw_value, &inline_value, &shared)
                        .map_err(|e| {
                            format!("Excel-Zeile {row_num}, Spalte {}: {e}", cell_col + 1)
                        })?;
                    put_cell(&mut row, cell_col, value)?;
                    in_cell = false;
                    field = Field::None;
                }
                b"row" if in_row => {
                    if in_cell {
                        return Err("Nicht geschlossene Excel-Zelle".into());
                    }
                    sink.on_row(row_num, std::mem::take(&mut row))?;
                    last_row = row_num;
                    in_row = false;
                }
                b"sheetData" => in_sheet_data = false,
                _ => (),
            },
            Event::Decl(ref e) => validate_declaration(e)?,
            Event::DocType(_) => return Err("DTD ist in XLSX nicht erlaubt".into()),
            Event::Eof => {
                if in_row || in_cell {
                    return Err("Tabellen-XML ist unvollständig".into());
                }
                if sink.headers.is_none() {
                    return Err(format!(
                        "Excel-Kopfzeile {} ist nicht vorhanden",
                        config.header_row
                    ));
                }
                sink.flush()?;
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
                .map_err(|_| "Ungültige Zell-Zeilennummer")?;
            if cell_row != expected_row {
                return Err(format!(
                    "Zellreferenz {reference:?} liegt nicht in Excel-Zeile {expected_row}"
                ));
            }
            index
        }
        None => next_col,
    };
    if *col >= MAX_COLS {
        return Err("Mehr als 16384 Spalten in einer Excel-Zeile".into());
    }
    *kind = attribute(e, b"t")?.unwrap_or_else(|| "n".into());
    Ok(())
}

fn put_cell(row: &mut Vec<CellValue>, col: usize, value: CellValue) -> Result<(), String> {
    if row.len() <= col {
        row.resize(col + 1, CellValue::Empty);
    }
    if row[col] != CellValue::Empty {
        return Err("Doppelte Excel-Zelle".into());
    }
    row[col] = value;
    Ok(())
}

#[cfg(test)]
mod tests {
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
            CellValue::Text("2026-10-31".into())
        );
    }
}
