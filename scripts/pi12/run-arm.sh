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

# Resolve the prompt file to an absolute path up front — the run cd's into the
# arm worktree, so a relative path would silently resolve against the wrong tree.
case "$PROMPT_FILE" in /*) ;; *) PROMPT_FILE="$PWD/$PROMPT_FILE" ;; esac
[ -r "$PROMPT_FILE" ] || { echo "ABORT: prompt file not readable: $PROMPT_FILE" >&2; exit 2; }

PINNED_VERSION="2.1.224"
# Observed output format on the pinned build: "2.1.224 (Claude Code)" — version is field 1.
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

# Arm C preflight: a live, correct-version ACE backend is an OPERATOR PRECONDITION
# (the runner never provisions it — provisioning carries credentials and state that
# don't belong in the instrument). The runner's job is to FAIL CLOSED: a dead or
# wrong-version backend would silently degrade arm C to bare Sonnet and invalidate
# the C-vs-B claim. Operator must export:
#   ACE_HEALTH_URL              e.g. http://127.0.0.1:PORT/health
#   ACE_EXPECTED_VERSION_REGEX  default '1\.1\.' (the shipped 1.1 CI journey)
if [ "$ACE" = 1 ]; then
  : "${ACE_HEALTH_URL:?ABORT: arm C requires ACE_HEALTH_URL (live 1.1.x ACE backend precondition)}"
  ACE_EXPECTED_VERSION_REGEX=${ACE_EXPECTED_VERSION_REGEX:-'1\.1\.'}
  HEALTH=$(curl -fsS --max-time 10 "$ACE_HEALTH_URL") || {
    echo "ABORT: ACE backend health check failed at $ACE_HEALTH_URL" >&2; exit 4; }
  echo "$HEALTH" | grep -Eq "$ACE_EXPECTED_VERSION_REGEX" || {
    echo "ABORT: ACE backend version does not match /$ACE_EXPECTED_VERSION_REGEX/ — got: $HEALTH" >&2; exit 4; }
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

# Arm C post-run check: verify the ACE MCP tools were actually exercised. Zero ACE
# tool calls means the arm silently degraded to bare Sonnet — flagged in meta; the
# operator rules the run degraded/invalid per spec section 7, never quietly keeps it.
if [ "$ACE" = 1 ]; then
  SESSION_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id",""))' "$OUT" 2>/dev/null || echo "")
  ACE_CALLS=0
  if [ -n "$SESSION_ID" ]; then
    TRANSCRIPT=$(ls "$HOME"/.claude/projects/*/"$SESSION_ID".jsonl 2>/dev/null | head -1 || true)
    [ -n "$TRANSCRIPT" ] && ACE_CALLS=$(grep -c '"mcp__' "$TRANSCRIPT" 2>/dev/null || echo 0)
  fi
  echo "ace_mcp_calls=$ACE_CALLS" >> "$META"
  if [ "$ACE_CALLS" = "0" ]; then
    echo "WARNING: arm C made ZERO ACE MCP calls — treat as degraded (silent bare-Sonnet fallback)" | tee -a "$META" >&2
  fi
fi

# Token budget (30M) is operator-monitored from the result usage, not hard-enforced:
# disclosed limitation -- CC has no native token-ceiling flag. Session id + usage
# for the capture record are in the result JSON.
echo "result: $OUT"; echo "meta:   $META"
echo "worktree left in place for review/diff: $WT (remove with: git worktree remove --force $WT)"
