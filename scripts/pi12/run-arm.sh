#!/usr/bin/env bash
# ACE Builds ACE arm runner v1
# Harness: ace-builds-ace-harness-v1, frozen digest
#   5ec835f197ebfb8c9e81e72b506ff119b1e77e0ab795139fd39b7ab5c8a18130 (commit a48eb8a)
# Launches ONE arm of ONE preregistered subject as a fresh headless Claude Code
# session in an isolated worktree, per spec sections 2-3. Operator reviews this
# script before first use; changes after first use are configuration drift.
#
# Usage: run-arm.sh <subject-id> <A|B|C> <frozen-head-sha> <prompt-file> [ace-mcp-config.json]
#   A = bare claude-fable-5 (evidence-only)   B = bare claude-sonnet-5 (evidence-only)
#   C = claude-sonnet-5 + ACE MCP (production candidate; requires mcp config arg)
set -euo pipefail

SUBJECT=${1:?subject id}; ARM=${2:?arm A|B|C}; HEAD=${3:?frozen head sha}
PROMPT_FILE=${4:?prompt file}; MCP_CONFIG=${5:-}

PINNED_VERSION="2.1.224"
ACTUAL_VERSION=$(claude --version | awk '{print $1}')
if [ "$ACTUAL_VERSION" != "$PINNED_VERSION" ]; then
  echo "ABORT: claude version $ACTUAL_VERSION != pinned $PINNED_VERSION (drift -> exploratory)" >&2
  exit 3
fi

case "$ARM" in
  A) MODEL="claude-fable-5";  ACE=0 ;;
  B) MODEL="claude-sonnet-5"; ACE=0 ;;
  C) MODEL="claude-sonnet-5"; ACE=1 ;;
  *) echo "arm must be A, B, or C" >&2; exit 2 ;;
esac
if [ "$ACE" = 1 ] && [ -z "$MCP_CONFIG" ]; then
  echo "arm C requires the ACE MCP config path" >&2; exit 2
fi

RUN_ID="aba-${SUBJECT}-arm${ARM}-$(date -u +%Y%m%dT%H%M%SZ)"
WT=$(mktemp -d "${TMPDIR:-/tmp}/${RUN_ID}-XXXX")
git worktree add --detach "$WT" "$HEAD" >/dev/null

# Frozen base allowlist; web excluded in every arm (spec section 3).
ALLOWED="Read,Write,Edit,Bash,Glob,Grep,TodoWrite"
ARGS=(-p --model "$MODEL"
      --allowedTools "$ALLOWED"
      --disallowedTools "WebSearch,WebFetch"
      --output-format json)
if [ "$ACE" = 1 ]; then
  ARGS+=(--mcp-config "$MCP_CONFIG" --strict-mcp-config)
else
  ARGS+=(--strict-mcp-config)   # no MCP servers resolve in bare arms
fi

OUT="${RUN_ID}-result.json"; META="${RUN_ID}-meta.txt"
{
  echo "run_id=$RUN_ID"; echo "subject=$SUBJECT"; echo "arm=$ARM"; echo "model=$MODEL"
  echo "frozen_head=$HEAD"; echo "worktree=$WT"; echo "cc_version=$ACTUAL_VERSION"
  echo "harness_digest=5ec835f197ebfb8c9e81e72b506ff119b1e77e0ab795139fd39b7ab5c8a18130"
  echo "started_utc=$(date -u +%FT%TZ)"
} > "$META"

# 8h wall-clock cap (spec section 3). Exit 124 = timeout, a recorded terminal state.
set +e
( cd "$WT" && timeout 28800 claude "${ARGS[@]}" < "$OLDPWD/$PROMPT_FILE" ) > "$OUT"
STATUS=$?
set -e
{
  echo "ended_utc=$(date -u +%FT%TZ)"; echo "exit_status=$STATUS (124=wall-clock cap)"
} >> "$META"

# Token budget (30M) is operator-monitored from the result usage, not hard-enforced:
# disclosed limitation -- CC has no native token-ceiling flag. Session id + usage
# for the capture record are in the result JSON.
echo "result: $OUT"; echo "meta:   $META"
echo "worktree left in place for review/diff: $WT (remove with: git worktree remove --force $WT)"
