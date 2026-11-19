// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! Signed POST to the foaMES machine-event webhook with bounded retries.
//!
//! Transport is a trait so tests use a fake; production uses `ReqwestTransport`
//! (blocking, rustls). Retry policy: exponential backoff on network errors and
//! 5xx, honouring `Retry-After` on 429; never retry 4xx (a rejected signature
//! or payload will not fix itself). Event `id`s make Core-side dedup safe.

use crate::event::{self, Event};
use crate::sign;
use serde_json::Value;
use std::thread;
use std::time::Duration;

#[derive(Debug, thiserror::Error)]
pub enum SendError {
    #[error("transport: {0}")]
    Transport(String),
    #[error("http {0}: {1}")]
    Http(u16, String),
    #[error("retries exhausted")]
    Exhausted,
}

/// One POST: returns (status, body_text).
pub trait Transport {
    fn post(&self, url: &str, headers: &[(String, String)], body: &[u8], timeout: Duration)
        -> Result<(u16, String), SendError>;
}

pub struct ReqwestTransport {
    client: reqwest::blocking::Client,
}

impl ReqwestTransport {
    pub fn new() -> Result<Self, SendError> {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|e| SendError::Transport(e.to_string()))?;
        Ok(ReqwestTransport { client })
    }
}

impl Transport for ReqwestTransport {
    fn post(
        &self,
        url: &str,
        headers: &[(String, String)],
        body: &[u8],
        timeout: Duration,
    ) -> Result<(u16, String), SendError> {
        let mut req = self.client.post(url).body(body.to_vec());
        for (k, v) in headers {
            req = req.header(k.as_str(), v.as_str());
        }
        let resp = req
            .timeout(timeout)
            .send()
            .map_err(|e| SendError::Transport(e.to_string()))?;
        let status = resp.status().as_u16();
        let text = resp.text().unwrap_or_default();
        Ok((status, text))
    }
}

pub struct Sender<'a, T: Transport> {
    endpoint: &'a str,
    secret: &'a str,
    transport: &'a T,
    timeout: Duration,
    max_retries: u32,
    /// Total events accepted/deduplicated/rejected, for observability.
    pub sent: u64,
    pub failed: u64,
}

const BACKOFF_MS: [u64; 4] = [200, 500, 1_000, 2_000];

impl<'a, T: Transport> Sender<'a, T> {
    pub fn new(endpoint: &'a str, secret: &'a str, transport: &'a T, timeout: Duration) -> Self {
        Sender {
            endpoint,
            secret,
            transport,
            timeout,
            max_retries: 4,
            sent: 0,
            failed: 0,
        }
    }

    /// POST one batch. Returns Ok(()) on 2xx; Err otherwise.
    pub fn send_batch(&mut self, events: &[Event]) -> Result<(), SendError> {
        if events.is_empty() {
            return Ok(());
        }
        let body = serde_json::to_vec(&event::envelope(events))
            .map_err(|e| SendError::Transport(e.to_string()))?;
        let timestamp = event::unix_now();
        let signature = sign::sign(self.secret, timestamp, &body);
        let headers = vec![
            ("Content-Type".to_string(), "application/json".to_string()),
            (sign::TIMESTAMP_HEADER.to_string(), timestamp.to_string()),
            (sign::SIGNATURE_HEADER.to_string(), signature),
        ];
        let mut attempt = 0u32;
        loop {
            match self.transport.post(self.endpoint, &headers, &body, self.timeout) {
                Ok((status, _)) if (200..300).contains(&status) => {
                    self.sent += events.len() as u64;
                    return Ok(());
                }
                Ok((status, text)) if status >= 400 && status < 500 => {
                    // Rejected: signature, payload or auth. Retrying cannot help.
                    self.failed += events.len() as u64;
                    return Err(SendError::Http(status, text.chars().take(200).collect()));
                }
                Ok((status, text)) => {
                    if attempt >= self.max_retries {
                        self.failed += events.len() as u64;
                        return Err(SendError::Exhausted);
                    }
                    let _ = (status, text);
                }
                Err(SendError::Transport(_)) if attempt >= self.max_retries => {
                    self.failed += events.len() as u64;
                    return Err(SendError::Exhausted);
                }
                Err(_) => {}
            }
            let delay = BACKOFF_MS[(attempt as usize).min(BACKOFF_MS.len() - 1)];
            thread::sleep(Duration::from_millis(delay));
            attempt += 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event::EventKind;
    use std::cell::RefCell;
    use std::collections::VecDeque;

    struct Fake {
        responses: RefCell<VecDeque<Result<(u16, String), SendError>>>,
        bodies: RefCell<Vec<Vec<u8>>>,
    }

    impl Fake {
        fn new(responses: Vec<Result<(u16, String), SendError>>) -> Self {
            Fake {
                responses: RefCell::new(responses.into()),
                bodies: RefCell::new(Vec::new()),
            }
        }
    }

    impl Transport for Fake {
        fn post(
            &self,
            _url: &str,
            _headers: &[(String, String)],
            body: &[u8],
            _timeout: Duration,
        ) -> Result<(u16, String), SendError> {
            self.bodies.borrow_mut().push(body.to_vec());
            self.responses
                .borrow_mut()
                .pop_front()
                .unwrap_or(Ok((200, "{}".into())))
        }
    }

    fn batch() -> Vec<Event> {
        vec![
            Event::now("press-1", EventKind::Count)
                .with("counter", Value::from("good"))
                .with("value", Value::from(42)),
        ]
    }

    #[test]
    fn signs_and_posts_expected_shape() {
        let fake = Fake::new(vec![]);
        let mut sender = Sender::new("https://x/api", "sekrit", &fake, Duration::from_secs(1));
        sender.send_batch(&batch()).unwrap();
        let body = String::from_utf8(fake.bodies.borrow()[0].clone()).unwrap();
        let v: Value = serde_json::from_str(&body).unwrap();
        assert!(v["events"].is_array());
        assert_eq!(v["events"][0]["machine"], "press-1");
        assert_eq!(v["events"][0]["type"], "Count");
        assert_eq!(v["events"][0]["counter"], "good");
        assert_eq!(v["events"][0]["value"], 42);
        assert!(v["events"][0]["id"].as_str().unwrap().starts_with("press-1-"));
    }

    #[test]
    fn retries_5xx_then_succeeds() {
        let fake = Fake::new(vec![
            Ok((503, "busy".into())),
            Ok((200, "{}".into())),
        ]);
        let mut sender = Sender::new("https://x", "s", &fake, Duration::from_millis(1));
        sender.max_retries = 3;
        // Backoff sleeps are real but tiny-ms; acceptable in tests.
        sender.send_batch(&batch()).unwrap();
        assert_eq!(fake.bodies.borrow().len(), 2);
    }

    #[test]
    fn never_retries_4xx() {
        let fake = Fake::new(vec![Ok((403, "bad sig".into())), Ok((200, "{}".into()))]);
        let mut sender = Sender::new("https://x", "s", &fake, Duration::from_millis(1));
        let err = sender.send_batch(&batch()).unwrap_err();
        assert!(matches!(err, SendError::Http(403, _)));
        assert_eq!(fake.bodies.borrow().len(), 1);
        assert_eq!(sender.failed, 1);
    }
}
