// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

//! HMAC-SHA256 request signing, byte-compatible with
//! `foames.foames_mes.signing`: hex HMAC-SHA256 of `<timestamp>.<body>` with the
//! shared secret, sent as `X-FoaMES-Signature` + `X-FoaMES-Timestamp`.

use hmac::{Hmac, Mac};
use sha2::Sha256;

pub const SIGNATURE_HEADER: &str = "X-FoaMES-Signature";
pub const TIMESTAMP_HEADER: &str = "X-FoaMES-Timestamp";

/// Sign `<timestamp>.<body>`; returns the lowercase hex digest.
pub fn sign(secret: &str, timestamp: i64, body: &[u8]) -> String {
    let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(secret.as_bytes())
        .expect("HMAC accepts keys of any length");
    mac.update(timestamp.to_string().as_bytes());
    mac.update(b".");
    mac.update(body);
    hex::encode(mac.finalize().into_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signature_is_hex_hmac_sha256_of_timestamp_dot_body() {
        let sig = sign("sekrit", 1730000000, br#"{"events":[]}"#);
        assert_eq!(sig.len(), 64);
        assert!(sig.chars().all(|c| c.is_ascii_hexdigit()));
        // Deterministic and input-sensitive.
        assert_eq!(sig, sign("sekrit", 1730000000, br#"{"events":[]}"#));
        assert_ne!(sig, sign("sekrit", 1730000001, br#"{"events":[]}"#));
        assert_ne!(sig, sign("other", 1730000000, br#"{"events":[]}"#));
        assert_ne!(sig, sign("sekrit", 1730000000, br#"{"events":[1]}"#));
    }
}
