#!/usr/bin/env bash
# Reports new PR review comments since the last check. Skips pull requests whose
# checks all pass (SUCCESS/NEUTRAL/SKIPPED) — once CI is green we stop watching.
# Runs as a Devin CLI SessionStart hook; output is injected as additionalContext.
set -uo pipefail

GH="gh"
command -v gh >/dev/null 2>&1 || GH="/c/Program Files/GitHub CLI/gh.exe"

REPO_SLUG="$(git remote get-url origin 2>/dev/null | sed -E 's#.*github.com[:/]##; s#\.git$##')"
[ -n "$REPO_SLUG" ] || exit 0

STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/devin-pr-watch"
mkdir -p "$STATE_DIR"
SAFE="$(printf '%s' "$REPO_SLUG" | tr '/' '-')"
STATE_FILE="$STATE_DIR/$SAFE.seen"
DONE_FILE="$STATE_DIR/$SAFE.done"
SEED=0
[ -f "$STATE_FILE" ] || SEED=1
touch "$STATE_FILE" "$DONE_FILE"

# key|pr|kind|id|user|date|excerpt  -> we only need pr|kind|id for dedupe
new_comments=""

while read -r pr; do
	[ -n "$pr" ] || continue
	# Stop watching a PR once every check has passed.
	bad="$("$GH" pr view "$pr" --repo "$REPO_SLUG" --json statusCheckRollup \
		--jq '[.statusCheckRollup[]? | (.conclusion // .state // .status // "")
			| select(. != "SUCCESS" and . != "NEUTRAL" and . != "SKIPPED")] | length' 2>/dev/null)"
	total="$("$GH" pr view "$pr" --repo "$REPO_SLUG" --json statusCheckRollup \
		--jq '[.statusCheckRollup[]?] | length' 2>/dev/null)"
	if [ "${total:-0}" -gt 0 ] && [ "${bad:-1}" = "0" ]; then
		grep -qx "$pr" "$DONE_FILE" || echo "$pr" >> "$DONE_FILE"
		continue
	fi

	for spec in "issue:$REPO_SLUG/issues/$pr/comments" "review:$REPO_SLUG/pulls/$pr/comments" "reviews:$REPO_SLUG/pulls/$pr/reviews"; do
		kind="${spec%%:*}"
		endpoint="${spec#*:}"
		while IFS=$'\t' read -r id user date body; do
			[ -n "$id" ] || continue
			key="$pr|$kind|$id"
			if grep -qxF "$key" "$STATE_FILE"; then
				continue
			fi
			echo "$key" >> "$STATE_FILE"
			[ "$SEED" = "1" ] && continue
			excerpt="$(printf '%s' "$body" | tr '\n' ' ' | cut -c1-300)"
			new_comments="${new_comments}PR #${pr} ${kind} by ${user} (${date}): ${excerpt}
"
		done < <("$GH" api --paginate "repos/$endpoint" \
			--jq '.[] | select(.body != null or .state != null)
				| "\(.id)\t\(.user.login)\t\(.submitted_at // .created_at // "")\t\(((.body // .state) | tostring) | gsub("[\r\n\t]+"; " "))"' 2>/dev/null)
	done
done < <("$GH" pr list --repo "$REPO_SLUG" --state open --limit 50 --json number --jq '.[].number' 2>/dev/null)

[ "$SEED" = "1" ] && exit 0
[ -z "$new_comments" ] && exit 0

printf '%s' "New pull request activity since your last check:

$new_comments
Triage each comment: fix genuine issues, reply to questions, and ignore bot noise." \
	| perl -MJSON::PP -e 'local $/; my $t=<STDIN>; print encode_json({hookSpecificOutput=>{hookEventName=>"SessionStart",additionalContext=>$t}})'
