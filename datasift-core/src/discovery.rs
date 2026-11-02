//! Bounded structural discovery. Unknown text-only layouts are diagnosed, never guessed.
use crate::rules::HeaderConfig;
use crate::value::CellValue;

pub enum Event {
    Header {
        number: u32,
        first: usize,
        raw: Vec<CellValue>,
        repeated: bool,
    },
    Close {
        first: usize,
        last: usize,
    },
    Ambiguous {
        first: usize,
        last: usize,
        start: u32,
        pending: Vec<(u32, Vec<CellValue>)>,
    },
}
struct Region {
    first: usize,
    last: usize,
    start: u32,
    end: u32,
    rows: Vec<Vec<CellValue>>,
    confirmed: bool,
    repeat: usize,
    blocked: bool,
}
#[derive(Default)]
pub struct Discovery {
    regions: Vec<Region>,
}
fn evidence(cell: &CellValue) -> bool {
    match cell {
        CellValue::Empty => false,
        CellValue::Text(text) => {
            text.parse::<f64>().is_ok_and(f64::is_finite)
                || chrono::NaiveDate::parse_from_str(text, "%Y-%m-%d").is_ok()
                || chrono::DateTime::parse_from_rfc3339(text).is_ok()
                || chrono::NaiveDateTime::parse_from_str(text, "%Y-%m-%dT%H:%M:%S%.f").is_ok()
        }
        _ => true,
    }
}
fn joined(region: &Region) -> Vec<CellValue> {
    (0..=region.last - region.first)
        .map(|col| {
            CellValue::Text(
                region
                    .rows
                    .iter()
                    .filter_map(|r| match r.get(col) {
                        Some(CellValue::Text(s)) if !s.is_empty() => Some(s.as_str()),
                        _ => None,
                    })
                    .collect::<Vec<_>>()
                    .join(" "),
            )
        })
        .collect()
}
fn issue(region: &mut Region) -> Event {
    region.blocked = true;
    let pending = if region.confirmed {
        vec![]
    } else {
        region
            .rows
            .iter()
            .enumerate()
            .map(|(offset, row)| (region.start + offset as u32, row.clone()))
            .collect()
    };
    Event::Ambiguous {
        first: region.first,
        last: region.last,
        start: region.start,
        pending,
    }
}
impl Discovery {
    pub fn observe(&mut self, number: u32, row: &[CellValue], header: &HeaderConfig) -> Vec<Event> {
        let mut events = Vec::new();
        for region in &mut self.regions {
            let cells: Vec<_> = (region.first..=region.last)
                .map(|i| row.get(i).cloned().unwrap_or(CellValue::Empty))
                .collect();
            if cells.iter().all(CellValue::empty) {
                if !region.confirmed && !region.blocked {
                    events.push(issue(region));
                }
                events.push(Event::Close {
                    first: region.first,
                    last: region.last,
                });
                continue;
            }
            if region.blocked {
                continue;
            }
            let all_text = cells
                .iter()
                .all(|c| matches!(c,CellValue::Text(s) if !s.is_empty()));
            let has_evidence = cells.iter().any(evidence);
            if region.confirmed {
                if cells
                    .iter()
                    .zip(&region.rows[region.repeat])
                    .all(|(a, b)| match (a, b) {
                        (CellValue::Text(a), CellValue::Text(b)) => {
                            header.normalize(a) == header.normalize(b)
                        }
                        _ => false,
                    })
                {
                    events.push(Event::Header {
                        number,
                        first: region.first,
                        raw: joined(region),
                        repeated: true,
                    });
                    region.repeat = (region.repeat + 1) % region.rows.len();
                } else if region.repeat != 0 || (all_text && !has_evidence) {
                    events.push(issue(region));
                }
            } else if number != region.end + 1 {
                events.push(issue(region));
            } else if region.rows.len() < header.rows {
                if all_text {
                    region.rows.push(cells);
                    region.end = number;
                } else {
                    events.push(issue(region));
                }
            } else if has_evidence {
                events.push(Event::Header {
                    number: region.end,
                    first: region.first,
                    raw: joined(region),
                    repeated: false,
                });
                region.confirmed = true;
            } else {
                events.push(issue(region));
            }
        }
        self.regions.retain(|r| {
            !events
                .iter()
                .any(|e| matches!(e,Event::Close{first,last} if *first==r.first && *last==r.last))
        });
        let mut col = 0;
        while col < row.len() {
            if row[col].empty() || self.regions.iter().any(|r| r.first <= col && col <= r.last) {
                col += 1;
                continue;
            }
            let first = col;
            col += 1;
            while col < row.len()
                && !row[col].empty()
                && !self.regions.iter().any(|r| r.first <= col && col <= r.last)
            {
                col += 1;
            }
            if col - first >= header.min_columns
                && row[first..col]
                    .iter()
                    .all(|v| matches!(v, CellValue::Text(_)))
            {
                self.regions.push(Region {
                    first,
                    last: col - 1,
                    start: number,
                    end: number,
                    rows: vec![row[first..col].to_vec()],
                    confirmed: false,
                    repeat: 0,
                    blocked: false,
                });
            }
        }
        events
    }
    pub fn finish(&mut self) -> Vec<Event> {
        let mut events = Vec::new();
        for region in &mut self.regions {
            if !region.confirmed && !region.blocked {
                events.push(issue(region));
            }
        }
        events
    }
}
