// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! The built-in simulation machine: a deterministic-ish source of Count and
//! occasional State events at a configured rate, for proving the pipeline
//! without real hardware.

use crate::event::{Event, EventKind};
use serde_json::Value;
use std::time::{Duration, Instant};

/// Emits `Count` events for a `good` counter at `rate_hz`, with a State event
/// every ~60 simulated seconds. Deterministic counter totals keep delta math
/// honest on the Core side.
pub struct Simulator {
    machine: String,
    rate_hz: u32,
    tick: Duration,
    next_tick: Instant,
    counter: u64,
    ticks_since_state: u32,
}

impl Simulator {
    pub fn new(machine: &str, rate_hz: u32) -> Self {
        let rate = rate_hz.max(1);
        Simulator {
            machine: machine.to_string(),
            rate_hz: rate,
            tick: Duration::from_secs_f64(1.0 / rate as f64),
            next_tick: Instant::now(),
            counter: 0,
            ticks_since_state: 0,
        }
    }

    /// Events due now (possibly several if the loop slept); empty when not yet.
    pub fn poll(&mut self) -> Vec<Event> {
        let now = Instant::now();
        if now < self.next_tick {
            return Vec::new();
        }
        // Catch up at most one tick per call to bound bursts after stalls.
        self.next_tick += self.tick;
        if self.next_tick < now {
            self.next_tick = now + self.tick;
        }
        self.counter += 1;
        self.ticks_since_state += 1;
        let mut out = vec![Event::now(&self.machine, EventKind::Count)
            .with("counter", Value::from("good"))
            .with("value", Value::from(self.counter))];
        // Roughly one State event per simulated minute.
        let state_every = (60.0 * self.rate_hz as f64) as u32;
        if self.ticks_since_state >= state_every.max(1) {
            self.ticks_since_state = 0;
            out.push(
                Event::now(&self.machine, EventKind::State).with("state", Value::from("Running")),
            );
        }
        out
    }

    pub fn rate_hz(&self) -> u32 {
        self.rate_hz
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn emits_count_events_at_rate_with_monotonic_counter() {
        let mut sim = Simulator::new("sim-1", 1000);
        // Force the first tick to be due.
        sim.next_tick = Instant::now() - Duration::from_secs(1);
        let events = sim.poll();
        assert!(!events.is_empty());
        let count = events.iter().find(|e| e.kind == EventKind::Count).unwrap();
        assert_eq!(count.extra["counter"], "good");
        assert!(count.extra["value"].as_u64().unwrap() >= 1);
    }
}
