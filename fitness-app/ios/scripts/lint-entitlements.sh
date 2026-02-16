#!/bin/bash

# lint-entitlements.sh
# Detects banned entitlements that cause provisioning profile build failures.
#
# Issue:
#   Apple Pay (com.apple.developer.in-app-payments) requires a specific provisioning
#   profile with merchant ID. StoreKit 2 IAPs do NOT need this entitlement, but
#   xcodegen will regenerate it if present in project.yml. This script catches it
#   in both places.
#
# Usage:
#   ./ios/scripts/lint-entitlements.sh
#   Exits 1 if banned entitlements are found.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Banned entitlements that cause provisioning failures
BANNED_ENTITLEMENTS=(
    "com.apple.developer.in-app-payments"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "========================================"
echo "Entitlements Lint Check"
echo "========================================"
echo ""

ISSUES=0

for entitlement in "${BANNED_ENTITLEMENTS[@]}"; do
    # Check project.yml (xcodegen source of truth)
    if grep -q "$entitlement" "$PROJECT_ROOT/ios/project.yml" 2>/dev/null; then
        echo -e "${RED}ERROR${NC}: Banned entitlement in project.yml"
        echo "  Key: $entitlement"
        echo "  File: ios/project.yml"
        echo "  Fix: Remove from entitlements.properties in project.yml"
        echo "  Note: StoreKit 2 IAPs do NOT need Apple Pay entitlement"
        echo ""
        ISSUES=$((ISSUES + 1))
    fi

    # Check .entitlements plist
    if grep -q "$entitlement" "$PROJECT_ROOT/ios/FitnessApp/FitnessApp.entitlements" 2>/dev/null; then
        echo -e "${RED}ERROR${NC}: Banned entitlement in entitlements plist"
        echo "  Key: $entitlement"
        echo "  File: ios/FitnessApp/FitnessApp.entitlements"
        echo "  Fix: Remove the key+value pair from the plist"
        echo ""
        ISSUES=$((ISSUES + 1))
    fi
done

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC} No banned entitlements found."
    exit 0
else
    echo -e "${RED}Found $ISSUES issue(s).${NC}"
    echo "These entitlements cause 'Provisioning profile doesn't match' build failures."
    exit 1
fi
