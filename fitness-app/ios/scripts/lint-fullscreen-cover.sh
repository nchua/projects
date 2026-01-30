#!/bin/bash

# lint-fullscreen-cover.sh
# Detects potential SwiftUI fullScreenCover state management issues that can cause black screens.
#
# Issue Pattern:
#   When using fullScreenCover(isPresented:) to iterate through multiple items
#   (e.g., showing PRs one by one), SwiftUI may reuse view instances instead of
#   creating new ones. This causes @State variables to retain stale values.
#
# The Fix:
#   Add .id(index) or .id(item.id) to force view recreation when iterating.
#
# Usage:
#   ./ios/scripts/lint-fullscreen-cover.sh [path]
#   Default path: ios/FitnessApp

set -e

SEARCH_PATH="${1:-ios/FitnessApp}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo "========================================"
echo "SwiftUI fullScreenCover Lint Check"
echo "========================================"
echo ""
echo "Scanning: $SEARCH_PATH"
echo ""

ISSUES_FOUND=0
WARNINGS_FOUND=0
FILES_CHECKED=0

# Function to check if a file has the dangerous pattern
check_file() {
    local file="$1"
    local relative_file="${file#$PROJECT_ROOT/}"

    # Check for fullScreenCover with isPresented binding
    if ! grep -q '\.fullScreenCover(isPresented:' "$file"; then
        return
    fi

    FILES_CHECKED=$((FILES_CHECKED + 1))

    # Get line numbers of fullScreenCover declarations
    local line_nums=$(grep -n '\.fullScreenCover(isPresented:' "$file" | cut -d: -f1)

    for line_num in $line_nums; do
        # Extract ~40 lines after the fullScreenCover declaration to analyze the content
        local context=$(sed -n "${line_num},$((line_num + 40))p" "$file")

        # CRITICAL: Check for iteration pattern (index < array.count)
        # This is the dangerous pattern that causes stale @State
        if echo "$context" | grep -qE 'if [a-zA-Z_]+Index\s*[<>]\s*[a-zA-Z_]+\.(count|length)'; then
            # Check if there's an .id() modifier within the conditional block
            if ! echo "$context" | grep -qE '\.id\([^)]+\)'; then
                echo -e "${RED}ERROR${NC}: Missing .id() modifier for iterated fullScreenCover"
                echo "  File: $relative_file:$line_num"
                echo "  Issue: fullScreenCover iterates through items without .id() modifier"
                echo "  Pattern: Uses index comparison (e.g., 'if currentIndex < items.count')"
                echo "  Risk: @State variables will be reused, causing stuck/black screens"
                echo "  Fix: Add .id(currentIndex) to the view inside the conditional"
                echo ""
                ISSUES_FOUND=$((ISSUES_FOUND + 1))
            else
                echo -e "${GREEN}OK${NC}: $relative_file:$line_num - has .id() modifier"
            fi
        fi

        # WARNING: Check for Color.clear fallback patterns
        if echo "$context" | grep -q 'Color.clear'; then
            local clear_start=$(echo "$context" | grep -n 'Color.clear' | head -1 | cut -d: -f1)
            if [ -n "$clear_start" ]; then
                local clear_context=$(echo "$context" | sed -n "${clear_start},$((clear_start + 10))p")

                # Check if fallback has proper cleanup (multiple state resets)
                local has_array_reset=$(echo "$clear_context" | grep -c '= \[\]' || true)
                local has_index_reset=$(echo "$clear_context" | grep -c '= 0' || true)
                local has_bool_reset=$(echo "$clear_context" | grep -c '= false' || true)

                local total_resets=$((has_array_reset + has_index_reset + has_bool_reset))

                if [ "$total_resets" -lt 2 ]; then
                    # Only warn if this is an iteration pattern
                    if echo "$context" | grep -qE 'if [a-zA-Z_]+Index\s*[<>]'; then
                        echo -e "${YELLOW}WARNING${NC}: Incomplete fallback cleanup in iteration pattern"
                        echo "  File: $relative_file:$line_num"
                        echo "  Issue: Color.clear fallback should reset all iteration state"
                        echo "  Fix: Reset array, index, and isPresented in the fallback branch"
                        echo ""
                        WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
                    fi
                fi
            fi
        fi
    done
}

# Function to check for views that auto-dismiss without guards
check_auto_dismiss_views() {
    local file="$1"
    local relative_file="${file#$PROJECT_ROOT/}"

    # Look for celebration/popup views that have auto-dismiss timers
    if grep -q 'DispatchQueue.main.asyncAfter\|Timer.scheduledTimer' "$file"; then
        if grep -q 'onDismiss' "$file"; then
            # Check if there's a guard against double dismissal
            if grep -q '@State.*private.*var.*isDismissed' "$file"; then
                if ! grep -qE 'guard.*!isDismissed|guard.*isDismissed.*==.*false' "$file"; then
                    echo -e "${YELLOW}WARNING${NC}: Auto-dismiss view without dismissal guard"
                    echo "  File: $relative_file"
                    echo "  Issue: Has timer + onDismiss + isDismissed state but no guard"
                    echo "  Risk: Timer can fire after manual dismiss, calling onDismiss() twice"
                    echo "  Fix: Add 'guard !isDismissed else { return }' before onDismiss()"
                    echo ""
                    WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
                fi
            fi
        fi
    fi
}

# Find all Swift files and check them
echo "Checking for fullScreenCover state issues..."
echo ""

while IFS= read -r -d '' file; do
    check_file "$file"
    check_auto_dismiss_views "$file"
done < <(find "$PROJECT_ROOT/$SEARCH_PATH" -name "*.swift" -type f -print0 2>/dev/null)

# Summary
echo ""
echo "========================================"
echo "Summary"
echo "========================================"
echo -e "Files with fullScreenCover: ${CYAN}$FILES_CHECKED${NC}"

if [ $ISSUES_FOUND -eq 0 ] && [ $WARNINGS_FOUND -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    echo "No fullScreenCover state management issues detected."
    exit 0
else
    if [ $ISSUES_FOUND -gt 0 ]; then
        echo -e "${RED}Errors: $ISSUES_FOUND${NC} (must fix)"
    fi
    if [ $WARNINGS_FOUND -gt 0 ]; then
        echo -e "${YELLOW}Warnings: $WARNINGS_FOUND${NC} (review recommended)"
    fi
    echo ""
    echo "See CLAUDE.md section 'SwiftUI fullScreenCover State Management' for details."

    if [ $ISSUES_FOUND -gt 0 ]; then
        exit 1
    fi
    exit 0
fi
