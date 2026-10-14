#!/bin/bash

# lint-swiftui-bindings.sh
# Rejects index-based SwiftUI bindings like `$items[index]`.
#
# Issue:
#   A row bound with `$array[i]` traps with "Index out of range" when the array
#   shrinks while the row is still mounted: SwiftUI re-reads the binding before
#   the ForEach drops the row. When it does that changes between iOS releases,
#   so the crash tends to appear after an upgrade (2026-09-27: every hunt
#   submit crashed once LogViewModel.resetWorkout() emptied the list).
#
# Fix:
#   Bind by id: `$items.element(matching: item)` (Utils/Extensions.swift).
#   A deliberate exception can carry `// lint:allow-index-binding` on its line.
#
# Usage:
#   ./ios/scripts/lint-swiftui-bindings.sh
#   Exits 1 if an index-based binding is found.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# A projected binding (`$name` / `$a.b`) subscripted by position. `$0[` is a
# closure argument (starts with a digit) and `$dict["key"]` is a dictionary
# binding (yields an optional, can't trap), so neither matches.
PATTERN='\$[A-Za-z_][A-Za-z0-9_.]*\[[^]"]'

echo "========================================"
echo "SwiftUI Index-Binding Lint Check"
echo "========================================"
echo ""

# Skip comment lines and explicit opt-outs.
matches=$(grep -rnE --include='*.swift' "$PATTERN" "$PROJECT_ROOT/ios/FitnessApp" \
    | grep -vE '^[^:]+:[0-9]+:[[:space:]]*//' \
    | grep -v 'lint:allow-index-binding' || true)

if [ -z "$matches" ]; then
    echo -e "${GREEN}All checks passed!${NC} No index-based bindings found."
    exit 0
fi

while IFS= read -r match; do
    echo -e "${RED}ERROR${NC}: Index-based binding"
    echo "  ${match#$PROJECT_ROOT/}"
    echo ""
done <<< "$matches"

echo -e "${RED}Found $(echo "$matches" | wc -l | tr -d ' ') issue(s).${NC}"
echo "Bind rows by id instead: \$items.element(matching: item)"
echo "(Traps with 'Index out of range' when the array shrinks under a mounted row.)"
exit 1
