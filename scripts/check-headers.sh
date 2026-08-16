#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/check-headers.sh
#  Purpose:  Verify every tracked source file carries the standard header
#            (CODING-STANDARDS.md §1) and grep staged files for obvious
#            secrets. Runs in the test suite and in the smoke test.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# docs/SPEC.md is the immutable founding specification; LICENSE is upstream text.
EXEMPT_REGEX='^(docs/SPEC\.md|LICENSE|.*\.gitkeep|.*\.json)$'
CHECKED_REGEX='(\.py|\.sh|\.sql|\.ya?ml|\.toml|\.md|\.cf|\.conf|\.env\.example|Dockerfile|\.gitignore)$'
REQUIRED_FIELDS=("menabò — an experiment" "File:" "Purpose:" "Author:" "Created:" "License:" "Part of:")

failures=0
checked=0
while IFS= read -r file; do
    [[ "$file" =~ $EXEMPT_REGEX ]] && continue
    [[ "$file" =~ $CHECKED_REGEX ]] || continue
    checked=$((checked + 1))
    head_block="$(head -n 15 "$file")"
    for field in "${REQUIRED_FIELDS[@]}"; do
        if ! grep -qF "$field" <<< "$head_block"; then
            echo "MISSING HEADER FIELD '$field': $file"
            failures=$((failures + 1))
        fi
    done
done < <(git ls-files)

# Obvious secret patterns must never be committed (CODING-STANDARDS.md §6).
secret_pattern='(-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|GK[0-9a-f]{24})'
secret_hits="$(git ls-files -z | xargs -0 grep -lIE "$secret_pattern" 2>/dev/null \
    | grep -vE 'scripts/check-headers\.sh$' || true)"
if [[ -n "$secret_hits" ]]; then
    echo "POSSIBLE SECRETS IN TRACKED FILES:"
    echo "$secret_hits"
    failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
    echo "check-headers: $failures problem(s) across $checked checked files."
    exit 1
fi
echo "check-headers: OK ($checked files checked)."
