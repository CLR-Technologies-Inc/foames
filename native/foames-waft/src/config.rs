// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! Configuration: endpoint, identity, sampling/batching limits, transport
//! security and the secret's *environment variable name* — never the secret.

use serde::{Deserialize, Serialize};
use std::env;
use std::path::Path;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    /// Full webhook URL, e.g. https://mes.example.com/api/method/foames.foames_mes.api.ingest_machine_events
    pub endpoint: String,
    /// Machine Source ID events are posted under.
    pub machine: String,
    /// Name of the env var holding the webhook secret (e.g. FOAMES_WEBHOOK_SECRET).
    /// The value itself is read at send time and never stored or logged.
    pub secret_env: String,
    /// Events per POST body.
    #[serde(default = "default_batch")]
    pub batch_size: usize,
    /// Max events buffered while the endpoint is unreachable.
    #[serde(default = "default_buffer")]
    pub max_buffer: usize,
    /// Flush interval when the batch is not yet full.
    #[serde(default = "default_flush_ms")]
    pub flush_interval_ms: u64,
    /// Per-request timeout.
    #[serde(default = "default_timeout_ms")]
    pub timeout_ms: u64,
    /// Simulation sample rate in events/second (0 disables the built-in sim).
    #[serde(default)]
    pub sample_rate_hz: u32,
    /// Base URL allowlist note: only https endpoints are allowed unless
    /// `allow_http` is set for isolated lab use.
    #[serde(default)]
    pub allow_http: bool,
}

fn default_batch() -> usize {
    100
}
fn default_buffer() -> usize {
    10_000
}
fn default_flush_ms() -> u64 {
    1_000
}
fn default_timeout_ms() -> u64 {
    10_000
}

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("cannot read config {0}: {1}")]
    Io(String, String),
    #[error("invalid config: {0}")]
    Invalid(String),
    #[error("secret env var {0} is not set")]
    MissingSecret(String),
    #[error("endpoint must be https (set allow_http only for isolated labs)")]
    InsecureEndpoint,
}

impl Config {
    pub fn load(path: &Path) -> Result<Self, ConfigError> {
        let text = std::fs::read_to_string(path)
            .map_err(|e| ConfigError::Io(path.display().to_string(), e.to_string()))?;
        let cfg: Config = serde_json::from_str(&text)
            .map_err(|e| ConfigError::Invalid(e.to_string()))?;
        cfg.validate()?;
        Ok(cfg)
    }

    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.endpoint.is_empty() || self.machine.is_empty() || self.secret_env.is_empty() {
            return Err(ConfigError::Invalid(
                "endpoint, machine and secret_env are required".into(),
            ));
        }
        if !self.allow_http && !self.endpoint.starts_with("https://") {
            return Err(ConfigError::InsecureEndpoint);
        }
        if self.batch_size == 0 || self.max_buffer < self.batch_size {
            return Err(ConfigError::Invalid(
                "batch_size must be > 0 and <= max_buffer".into(),
            ));
        }
        Ok(())
    }

    /// Read the webhook secret from the environment variable it names.
    pub fn secret(&self, env: &dyn Fn(&str) -> Option<String>) -> Result<String, ConfigError> {
        env(&self.secret_env)
            .filter(|s| !s.is_empty())
            .ok_or_else(|| ConfigError::MissingSecret(self.secret_env.clone()))
    }

    pub fn secret_from_process(&self) -> Result<String, ConfigError> {
        self.secret(&|name| env::var(name).ok())
    }

    pub fn flush_interval(&self) -> Duration {
        Duration::from_millis(self.flush_interval_ms)
    }

    pub fn timeout(&self) -> Duration {
        Duration::from_millis(self.timeout_ms)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg_json() -> &'static str {
        r#"{"endpoint":"https://mes.example.com/hook","machine":"m1","secret_env":"FOAMES_WEBHOOK_SECRET","sample_rate_hz":10}"#
    }

    #[test]
    fn parses_minimal_config_with_defaults() {
        let cfg: Config = serde_json::from_str(cfg_json()).unwrap();
        cfg.validate().unwrap();
        assert_eq!(cfg.batch_size, 100);
        assert_eq!(cfg.max_buffer, 10_000);
    }

    #[test]
    fn https_required_unless_allowed() {
        let mut cfg: Config = serde_json::from_str(cfg_json()).unwrap();
        cfg.endpoint = "http://mes.lan/hook".into();
        assert!(matches!(cfg.validate(), Err(ConfigError::InsecureEndpoint)));
        cfg.allow_http = true;
        cfg.validate().unwrap();
    }

    #[test]
    fn secret_comes_from_named_env_only() {
        let cfg: Config = serde_json::from_str(cfg_json()).unwrap();
        let secret = cfg.secret(&|name| (name == "FOAMES_WEBHOOK_SECRET").then(|| "s3cr3t".to_string())).unwrap();
        assert_eq!(secret, "s3cr3t");
        assert!(matches!(
            cfg.secret(&|_| None),
            Err(ConfigError::MissingSecret(_))
        ));
    }

    #[test]
    fn rejects_empty_required_fields() {
        let cfg: Config = serde_json::from_str(r#"{"endpoint":"","machine":"m","secret_env":"E"}"#).unwrap();
        assert!(cfg.validate().is_err());
    }
}
