#!/usr/bin/env bash
# Run one prompt through a coding agent, non-interactively.
#
# Usage:
#   agent_call.sh <claude|codex|pi> "prompt text"   # prompt as arguments
#   agent_call.sh <claude|codex|pi> <<EOF ...       # or on stdin
#
# Environment:
#   AGENT_MODEL     model override, passed through to the agent (default: per agent below)
#   AGENT_PROVIDER  provider override, pi only                  (default: openrouter)
#
# All agents are run in their fully autonomous mode: they may edit files and run
# commands without asking. Only use this on a throwaway worker.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: agent_call.sh <claude|codex|pi> [prompt]" >&2
    exit 2
fi

AGENT="$1"
shift

if [ "$#" -gt 0 ]; then
    PROMPT="$*"
else
    PROMPT="$(cat)"
fi

if [ -z "${PROMPT//[[:space:]]/}" ]; then
    echo "agent_call.sh: empty prompt" >&2
    exit 2
fi

case "$AGENT" in
claude)
    args=(--print --dangerously-skip-permissions)
    # Running as root additionally needs IS_SANDBOX=1 for the flag above.
    [ -n "${AGENT_MODEL:-}" ] && args+=(--model "$AGENT_MODEL")
    exec claude "${args[@]}" -- "$PROMPT"
    ;;
codex)
    args=(exec --dangerously-bypass-approvals-and-sandbox)
    [ -n "${AGENT_MODEL:-}" ] && args+=(--model "$AGENT_MODEL")
    exec codex "${args[@]}" -- "$PROMPT"
    ;;
pi)
    args=(--model "${AGENT_MODEL:-z-ai/glm-5.2}" --provider "${AGENT_PROVIDER:-openrouter}")
    exec pi "${args[@]}" <<<"$PROMPT"
    ;;
*)
    echo "agent_call.sh: unknown AGENT '${AGENT}' (expected claude, codex or pi)" >&2
    exit 2
    ;;
esac
