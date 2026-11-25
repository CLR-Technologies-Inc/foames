#!/bin/sh
# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
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
