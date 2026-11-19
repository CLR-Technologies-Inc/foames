// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! foames-waft: a minimal native transport for machine events.
//!
//! WAFT (Lightweight Affordable Frequent Transmission) connects simulations,
//! machines and constrained edge devices to foaMES Core through the existing
//! signed machine-event webhook. It owns transport only: sampling, batching,
//! signing, bounded buffering, backoff and idempotent event ids. All MES rules —
//! state interpretation, counter deltas, permissions, audit — stay in Core.
//!
//! Modules: [`config`], [`event`], [`sign`], [`batcher`], [`sender`], [`sim`].

pub mod batcher;
pub mod config;
pub mod event;
pub mod sender;
pub mod sign;
pub mod sim;

pub use batcher::Batcher;
pub use config::Config;
pub use event::{Event, EventKind};
pub use sender::{Sender, Transport};

/// The WAFT wire protocol version. Bump on incompatible contract changes.
pub const PROTOCOL_VERSION: u32 = 1;

/// C ABI entry point: the protocol version this build speaks.
///
/// Stable across patch releases; consumers link `foames_waft.h` and check it
/// before use. Exposed for `cdylib`/`staticlib` builds.
#[no_mangle]
pub extern "C" fn foames_waft_protocol_version() -> u32 {
    PROTOCOL_VERSION
}
