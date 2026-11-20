// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! foames-waft CLI: run the simulator/sender loop against foaMES Core.
//!
//!     foames-waft run --config waft.json [--once]
//!     foames-waft bench --config waft.json --duration 10
//!
//! The webhook secret is read from the environment variable named by
//! `secret_env` in the config (e.g. FOAMES_WEBHOOK_SECRET); it is never taken
//! on the command line, written to files or logged.

use foames_waft::batcher::Batcher;
use foames_waft::config::Config;
use foames_waft::sender::{ReqwestTransport, Sender};
use foames_waft::sim::Simulator;
use std::path::PathBuf;
use std::process::ExitCode;
use std::thread;
use std::time::{Duration, Instant};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("run") => run(&args),
        Some("bench") => bench(&args),
        _ => {
            eprintln!("usage: foames-waft run --config <file> [--once] | bench --config <file> --duration <secs>");
            ExitCode::from(2)
        }
    }
}

fn parse_args(args: &[String]) -> (PathBuf, Option<u64>, bool) {
    let mut config = None;
    let mut duration = None;
    let mut once = false;
    let mut i = 2;
    while i < args.len() {
        match args[i].as_str() {
            "--config" => {
                i += 1;
                config = args.get(i).map(PathBuf::from);
            }
            "--duration" => {
                i += 1;
                duration = args.get(i).and_then(|s| s.parse().ok());
            }
            "--once" => once = true,
            _ => {}
        }
        i += 1;
    }
    (config.unwrap_or_else(|| PathBuf::from("waft.json")), duration, once)
}

fn load(args: &[String]) -> Result<(Config, String), String> {
    let (path, _, _) = parse_args(args);
    let cfg = Config::load(&path).map_err(|e| e.to_string())?;
    let secret = cfg.secret_from_process().map_err(|e| e.to_string())?;
    Ok((cfg, secret))
}

fn run(args: &[String]) -> ExitCode {
    let (_, _, once) = parse_args(args);
    let (cfg, secret) = match load(args) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("config: {e}");
            return ExitCode::from(2);
        }
    };
    if cfg.sample_rate_hz == 0 {
        eprintln!("config: sample_rate_hz is 0; nothing to send");
        return ExitCode::from(2);
    }
    let transport = match ReqwestTransport::new() {
        Ok(t) => t,
        Err(e) => {
            eprintln!("transport: {e}");
            return ExitCode::from(1);
        }
    };
    let mut sender = Sender::new(&cfg.endpoint, &secret, &transport, cfg.timeout());
    let mut batcher = Batcher::new(cfg.max_buffer, cfg.batch_size);
    let mut sim = Simulator::new(&cfg.machine, cfg.sample_rate_hz);
    let flush = cfg.flush_interval();
    let mut last_flush = Instant::now();

    loop {
        for event in sim.poll() {
            batcher.push(event);
        }
        if batcher.len() >= cfg.batch_size || last_flush.elapsed() >= flush {
            let batch = batcher.drain_batch();
            if !batch.is_empty() {
                if let Err(e) = sender.send_batch(&batch) {
                    eprintln!("send: {e} ({} events affected)", batch.len());
                    // Requeue in order so the next batch keeps FIFO sequence.
                    for event in batch {
                        let _ = batcher.push(event);
                    }
                }
            }
            last_flush = Instant::now();
        }
        if once {
            // One-shot mode: flush everything queued, then exit.
            let batch = batcher.drain_all(cfg.batch_size * 100);
            if !batch.is_empty() {
                let _ = sender.send_batch(&batch);
            }
            report(&sender, &batcher);
            return ExitCode::SUCCESS;
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn bench(args: &[String]) -> ExitCode {
    let (_, duration, _) = parse_args(args);
    let secs = duration.unwrap_or(10);
    let (cfg, secret) = match load(args) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("config: {e}");
            return ExitCode::from(2);
        }
    };
    let transport = match ReqwestTransport::new() {
        Ok(t) => t,
        Err(e) => {
            eprintln!("transport: {e}");
            return ExitCode::from(1);
        }
    };
    let mut sender = Sender::new(&cfg.endpoint, &secret, &transport, cfg.timeout());
    let mut batcher = Batcher::new(cfg.max_buffer, cfg.batch_size);
    let mut sim = Simulator::new(&cfg.machine, cfg.sample_rate_hz.max(1));
    let mut latencies: Vec<f64> = Vec::new();
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(secs) {
        for event in sim.poll() {
            batcher.push(event);
        }
        if batcher.len() >= cfg.batch_size {
            let batch = batcher.drain_batch();
            let t0 = Instant::now();
            match sender.send_batch(&batch) {
                Ok(()) => latencies.push(t0.elapsed().as_secs_f64() * 1000.0),
                Err(_) => {}
            }
        }
        thread::sleep(Duration::from_millis(2));
    }
    let batch = batcher.drain_all(cfg.batch_size * 100);
    if !batch.is_empty() {
        let t0 = Instant::now();
        if sender.send_batch(&batch).is_ok() {
            latencies.push(t0.elapsed().as_secs_f64() * 1000.0);
        }
    }
    latencies.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let p = |q: f64| -> f64 {
        if latencies.is_empty() {
            0.0
        } else {
            latencies[((latencies.len() - 1) as f64 * q) as usize]
        }
    };
    println!(
        "waft bench: {} events in {}s ({:.0}/s), batches={}, latency ms p50={:.1} p95={:.1} p99={:.1}, sent={} failed={} dropped={}",
        cfg.sample_rate_hz as u64 * secs,
        secs,
        cfg.sample_rate_hz as f64,
        latencies.len(),
        p(0.50),
        p(0.95),
        p(0.99),
        sender.sent,
        sender.failed,
        batcher.dropped,
    );
    ExitCode::SUCCESS
}

fn report(sender: &Sender<impl foames_waft::sender::Transport>, batcher: &Batcher) {
    eprintln!(
        "waft: sent={} failed={} buffered={} dropped={}",
        sender.sent,
        sender.failed,
        batcher.len(),
        batcher.dropped
    );
}
