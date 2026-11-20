// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

/*
 * foames-waft C ABI (protocol version 1).
 *
 * Link against libfoames_waft (cdylib/staticlib) or use the foames-waft CLI.
 * The only stable entry point today is the protocol version; event production
 * and transport are exercised through the Rust API/CLI. Secrets are always
 * supplied by the caller at runtime — never compiled in.
 */

#ifndef FOAMES_WAFT_H
#define FOAMES_WAFT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Protocol version this build speaks. Check before use; bump = incompatible. */
uint32_t foames_waft_protocol_version(void);

#ifdef __cplusplus
}
#endif

#endif /* FOAMES_WAFT_H */
