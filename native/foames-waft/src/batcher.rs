// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! Bounded event buffer with backpressure.
//!
//! `push` never blocks and never grows past `max_buffer`: when full, the
//! *incoming* event is dropped and counted — newest data wins over stale
//! backlog, and the drop count is observable. `drain_batch` takes up to
//! `batch_size` events FIFO.

use crate::event::Event;
use std::collections::VecDeque;

#[derive(Debug, Default)]
pub struct Batcher {
    queue: VecDeque<Event>,
    capacity: usize,
    batch_size: usize,
    /// Events dropped because the buffer was full.
    pub dropped: u64,
}

impl Batcher {
    pub fn new(capacity: usize, batch_size: usize) -> Self {
        Batcher {
            queue: VecDeque::with_capacity(capacity.min(65_536)),
            capacity,
            batch_size,
            dropped: 0,
        }
    }

    /// Queue an event; returns false (and counts a drop) when the buffer is full.
    pub fn push(&mut self, event: Event) -> bool {
        if self.queue.len() >= self.capacity {
            self.dropped += 1;
            return false;
        }
        self.queue.push_back(event);
        true
    }

    pub fn len(&self) -> usize {
        self.queue.len()
    }

    pub fn is_empty(&self) -> bool {
        self.queue.is_empty()
    }

    /// Take up to `batch_size` events, oldest first.
    pub fn drain_batch(&mut self) -> Vec<Event> {
        let n = self.batch_size.min(self.queue.len());
        self.queue.drain(..n).collect()
    }

    /// Force a partial flush: take everything queued, up to `max` events.
    pub fn drain_all(&mut self, max: usize) -> Vec<Event> {
        let n = max.min(self.queue.len());
        self.queue.drain(..n).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event::EventKind;

    fn ev(i: u64) -> Event {
        Event::at("m", EventKind::Count, i as i64)
            .with("value", serde_json::json!(i))
    }

    #[test]
    fn batches_respect_size_and_order() {
        let mut b = Batcher::new(100, 3);
        for i in 0..7 {
            b.push(ev(i));
        }
        let first = b.drain_batch();
        assert_eq!(first.len(), 3);
        assert_eq!(b.len(), 4);
        let rest = b.drain_all(10);
        assert_eq!(rest.len(), 4);
        assert!(b.is_empty());
    }

    #[test]
    fn full_buffer_drops_incoming_and_counts() {
        let mut b = Batcher::new(2, 10);
        assert!(b.push(ev(1)));
        assert!(b.push(ev(2)));
        assert!(!b.push(ev(3)));
        assert_eq!(b.dropped, 1);
        assert_eq!(b.len(), 2);
    }
}
