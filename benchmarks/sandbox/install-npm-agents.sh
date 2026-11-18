#!/bin/sh
# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

set -eu
[ "$#" -gt 0 ] || exit 0

npm install -g --ignore-scripts "$@"
for spec do
	# npm rebuild expects installed package names, rather than dist-tags or
	# version selectors. Preserve a scoped name before removing its selector.
	case "$spec" in
		@*) package="${spec#@}"; package="@${package%%@*}" ;;
		*) package="${spec%%@*}" ;;
	esac
	# Required native install scripts still run for each requested agent.
	npm rebuild -g "$package"
done
npm cache clean --force
