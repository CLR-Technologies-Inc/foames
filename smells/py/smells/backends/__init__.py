# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Backend adapters: the contract every language implementation fulfils.

A backend loads a model once, then `infer(inputs)` is called once per timed
iteration. `inputs` is a list of nested-list tensors materialised by
`smells.manifest.make_inputs`; adapters may convert to numpy/ndarray/etc.
"""
