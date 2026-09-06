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


# ---------------------------------------------------------------------------
# Debug/Release entitlements parity.
#
# The two files are hand-maintained (see ios/project.yml): xcodegen's
# `entitlements:` key writes CODE_SIGN_ENTITLEMENTS into every configuration and
# would clobber the per-config split. They must be identical except for
# aps-environment, which is `development` in Debug and `production` in Release.
# A Release build carrying `development` gets sandbox APNs tokens, and every
# production push silently fails.
# ---------------------------------------------------------------------------

DEBUG_ENT="$PROJECT_ROOT/ios/FitnessApp/FitnessApp.entitlements"
RELEASE_ENT="$PROJECT_ROOT/ios/FitnessApp/FitnessAppRelease.entitlements"

if [ ! -f "$RELEASE_ENT" ]; then
    echo -e "${RED}ERROR${NC}: Missing Release entitlements"
    echo "  File: ios/FitnessApp/FitnessAppRelease.entitlements"
    echo "  Fix: Recreate it mirroring FitnessApp.entitlements with"
    echo "       aps-environment set to 'production'."
    echo ""
    ISSUES=$((ISSUES + 1))
else
    # aps-environment must be development in Debug, production in Release.
    debug_aps=$(/usr/libexec/PlistBuddy -c "Print :aps-environment" "$DEBUG_ENT" 2>/dev/null || echo "")
    release_aps=$(/usr/libexec/PlistBuddy -c "Print :aps-environment" "$RELEASE_ENT" 2>/dev/null || echo "")

    if [ "$debug_aps" != "development" ]; then
        echo -e "${RED}ERROR${NC}: Debug aps-environment is '$debug_aps', expected 'development'"
        echo "  File: ios/FitnessApp/FitnessApp.entitlements"
        echo ""
        ISSUES=$((ISSUES + 1))
    fi

    if [ "$release_aps" != "production" ]; then
        echo -e "${RED}ERROR${NC}: Release aps-environment is '$release_aps', expected 'production'"
        echo "  File: ios/FitnessApp/FitnessAppRelease.entitlements"
        echo "  Why: App Store / TestFlight builds need production APNs tokens."
        echo ""
        ISSUES=$((ISSUES + 1))
    fi

    # Every other key must match exactly, so a capability added to one file
    # cannot go missing from the other.
    debug_keys=$(/usr/libexec/PlistBuddy -c "Print" "$DEBUG_ENT" | grep -oE "^ +[a-zA-Z0-9._-]+ = " | sed 's/[ =]//g' | grep -v "^aps-environment$" | sort)
    release_keys=$(/usr/libexec/PlistBuddy -c "Print" "$RELEASE_ENT" | grep -oE "^ +[a-zA-Z0-9._-]+ = " | sed 's/[ =]//g' | grep -v "^aps-environment$" | sort)

    if [ "$debug_keys" != "$release_keys" ]; then
        echo -e "${RED}ERROR${NC}: Debug and Release entitlements have drifted"
        echo "  Files: ios/FitnessApp/FitnessApp.entitlements"
        echo "         ios/FitnessApp/FitnessAppRelease.entitlements"
        echo "  Diff (Debug vs Release, aps-environment excluded):"
        diff <(echo "$debug_keys") <(echo "$release_keys") | sed 's/^/    /'
        echo "  Fix: add the missing capability to whichever file lacks it."
        echo ""
        ISSUES=$((ISSUES + 1))
    fi
fi

# A regenerated `entitlements:` block in project.yml silently re-clobbers the
# per-config split, so fail loudly if one reappears.
if grep -qE "^    entitlements:" "$PROJECT_ROOT/ios/project.yml" 2>/dev/null; then
    echo -e "${RED}ERROR${NC}: project.yml has an 'entitlements:' block"
    echo "  File: ios/project.yml"
    echo "  Why: it writes CODE_SIGN_ENTITLEMENTS into EVERY configuration,"
    echo "       overriding the Debug/Release split and shipping a"
    echo "       development APNs entitlement to the App Store."
    echo "  Fix: remove it; set CODE_SIGN_ENTITLEMENTS under settings.configs."
    echo ""
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC} No banned entitlements found."
    exit 0
else
    echo -e "${RED}Found $ISSUES issue(s).${NC}"
    echo "These entitlements cause 'Provisioning profile doesn't match' build failures."
    exit 1
fi
