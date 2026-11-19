// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! Machine-event contract: the JSON shape foaMES Core already accepts.
//!
//! Events match `foames.foames_mes.api.ingest_machine_events`: a POST of
//! `{"events": [...]}` where each event is `{"machine", "type", "timestamp",
//! "id", ...}` with type-specific fields (`state`, `counter`+`value`,
//! `name`+`value`, `code`/`text`). `#[serde(flatten)]` carries those fields
//! without WAFT interpreting them — transformation stays at the edge, rules in
//! Core.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// The five event types Core understands.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub enum EventKind {
    State,
    Count,
    Measurement,
    Alarm,
    Message,
}

impl EventKind {
    pub fn as_str(self) -> &'static str {
        match self {
            EventKind::State => "State",
            EventKind::Count => "Count",
            EventKind::Measurement => "Measurement",
            EventKind::Alarm => "Alarm",
            EventKind::Message => "Message",
        }
    }
}

static EVENT_SEQ: AtomicU64 = AtomicU64::new(0);

/// One machine event. `extra` holds the type-specific fields verbatim.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    /// The machine's Source ID in foaMES.
    pub machine: String,
    #[serde(rename = "type")]
    pub kind: EventKind,
    /// Unix seconds (Core also accepts ISO-8601).
    pub timestamp: i64,
    /// Stable idempotency id: `<machine>-<unix_nanos>-<seq>`.
    pub id: String,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl Event {
    pub fn now(machine: &str, kind: EventKind) -> Self {
        Self::at(machine, kind, unix_now())
    }

    pub fn at(machine: &str, kind: EventKind, timestamp: i64) -> Self {
        let seq = EVENT_SEQ.fetch_add(1, Ordering::Relaxed);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.subsec_nanos())
            .unwrap_or(0);
        Event {
            machine: machine.to_string(),
            kind,
            timestamp,
            id: format!("{machine}-{timestamp}-{nanos:09}-{seq:06}"),
            extra: Map::new(),
        }
    }

    /// Attach a field (e.g. `counter`, `value`, `state`, `text`).
    pub fn with(mut self, key: &str, value: Value) -> Self {
        self.extra.insert(key.to_string(), value);
        self
    }

    pub fn to_json(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }
}

pub fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn event_serializes_to_foames_shape() {
        let event = Event::now("press-1", EventKind::Count)
            .with("counter", serde_json::json!("good"))
            .with("value", serde_json::json!(1234));
        let v = event.to_json();
        assert_eq!(v["machine"], "press-1");
        assert_eq!(v["type"], "Count");
        assert!(v["timestamp"].is_i64());
        assert!(v["id"].as_str().unwrap().starts_with("press-1-"));
        assert_eq!(v["counter"], "good");
        assert_eq!(v["value"], 1234);
    }

    #[test]
    fn ids_are_unique() {
        let a = Event::now("m", EventKind::Message).with("text", Value::from("x"));
        let b = Event::now("m", EventKind::Message).with("text", Value::from("x"));
        assert_ne!(a.id, b.id);
    }

    #[test]
    fn envelope_wraps_events() {
        let events = vec![Event::now("m", EventKind::State).with("state", Value::from("Running"))];
        let v = envelope(&events);
        assert_eq!(v["events"].as_array().unwrap().len(), 1);
    }
}

/// Wrap events in the webhook body Core expects.
pub fn envelope(events: &[Event]) -> Value {
    let list: Vec<Value> = events.iter().map(Event::to_json).collect();
    serde_json::json!({ "events": list })
}
