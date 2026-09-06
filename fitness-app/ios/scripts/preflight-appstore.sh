#!/bin/bash
#
# preflight-appstore.sh
# Mechanical pre-upload checks for an App Store / TestFlight build.
#
# Catches the class of problem that a green build and a passing test suite
# cannot see: metadata that is present but wrong, contracts that have drifted
# across the iOS/backend boundary, and assets that Apple rejects on ingest.
#
# Judgement calls (screenshots, copy, demo account, IAP products created in
# App Store Connect) are NOT checkable here — see docs/app-store-launch.md.
#
# Usage:
#   bash ios/scripts/preflight-appstore.sh
#   Exits 1 if any check fails.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
IOS="$PROJECT_ROOT/ios"
BACKEND="$PROJECT_ROOT/backend"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
ISSUES=0
WARNINGS=0

fail() { echo -e "${RED}FAIL${NC}: $1"; shift; for l in "$@"; do echo "  $l"; done; echo ""; ISSUES=$((ISSUES + 1)); }
warn() { echo -e "${YELLOW}WARN${NC}: $1"; shift; for l in "$@"; do echo "  $l"; done; echo ""; WARNINGS=$((WARNINGS + 1)); }
pass() { echo -e "${GREEN}ok${NC}   $1"; }

echo "========================================"
echo "App Store Preflight"
echo "========================================"
echo ""

# --- 1. Entitlements -------------------------------------------------------
echo "--- Entitlements ---"
if bash "$SCRIPT_DIR/lint-entitlements.sh" > /tmp/preflight-ent.log 2>&1; then
    pass "entitlements lint (Debug/Release parity, aps-environment, banned keys)"
else
    fail "entitlements lint failed" "Run: bash ios/scripts/lint-entitlements.sh"
    sed 's/^/  /' /tmp/preflight-ent.log
fi

# --- 2. Info.plist ---------------------------------------------------------
echo "--- Info.plist ---"
PLIST="$IOS/FitnessApp/Info.plist"

enc=$(/usr/libexec/PlistBuddy -c "Print :ITSAppUsesNonExemptEncryption" "$PLIST" 2>/dev/null || echo "MISSING")
if [ "$enc" = "MISSING" ]; then
    fail "ITSAppUsesNonExemptEncryption not declared" \
         "App Store Connect will prompt for export compliance on every upload." \
         "Fix: add it to info.properties in ios/project.yml, then xcodegen generate."
else
    pass "export compliance declared (ITSAppUsesNonExemptEncryption = $enc)"
fi

short=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$PLIST" 2>/dev/null || echo "")
build=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$PLIST" 2>/dev/null || echo "")
if [ -z "$short" ] || [ -z "$build" ]; then
    fail "missing version keys" "CFBundleShortVersionString='$short' CFBundleVersion='$build'"
else
    pass "version $short (build $build)"
    echo "       Every upload needs a unique, increasing CFBundleVersion."
fi

# Usage strings must exist for each permission the app actually requests.
for key in NSHealthShareUsageDescription NSHealthUpdateUsageDescription NSPhotoLibraryUsageDescription; do
    v=$(/usr/libexec/PlistBuddy -c "Print :$key" "$PLIST" 2>/dev/null || echo "")
    if [ -z "$v" ]; then
        fail "$key missing" "Apple rejects builds that request a permission with no purpose string."
    elif [ ${#v} -lt 25 ]; then
        warn "$key is very short (${#v} chars)" "Vague purpose strings draw 5.1.1 rejections."
    fi
done
pass "permission purpose strings present"

# --- 3. Privacy manifest ---------------------------------------------------
echo "--- Privacy manifest ---"
MANIFEST="$IOS/FitnessApp/Resources/PrivacyInfo.xcprivacy"
if [ ! -f "$MANIFEST" ]; then
    fail "PrivacyInfo.xcprivacy missing" "Expected at ios/FitnessApp/Resources/"
elif ! plutil -lint "$MANIFEST" > /dev/null 2>&1; then
    fail "PrivacyInfo.xcprivacy is not valid plist" "Run: plutil -lint $MANIFEST"
else
    types=$(/usr/libexec/PlistBuddy -c "Print :NSPrivacyCollectedDataTypes" "$MANIFEST" 2>/dev/null | grep -c "NSPrivacyCollectedDataType = " || true)
    if [ "$types" -eq 0 ]; then
        fail "privacy manifest declares zero collected data types" \
             "The app collects email, health, fitness, photos, and user content." \
             "An empty declaration contradicts the published /privacy page."
    else
        pass "privacy manifest valid, $types collected data type(s) declared"
    fi
    apis=$(/usr/libexec/PlistBuddy -c "Print :NSPrivacyAccessedAPITypes" "$MANIFEST" 2>/dev/null | grep -c "NSPrivacyAccessedAPIType = " || true)
    pass "$apis required-reason API categor(ies) declared"
fi

# --- 4. App icon -----------------------------------------------------------
echo "--- App icon ---"
ICON="$IOS/FitnessApp/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
if [ ! -f "$ICON" ]; then
    fail "AppIcon.png missing"
else
    dims=$(sips -g pixelWidth -g pixelHeight "$ICON" 2>/dev/null | awk '/pixel/ {print $2}' | paste -sd'x' -)
    alpha=$(sips -g hasAlpha "$ICON" 2>/dev/null | awk '/hasAlpha/ {print $2}')
    if [ "$dims" != "1024x1024" ]; then
        fail "app icon is ${dims}, must be 1024x1024"
    elif [ "$alpha" = "yes" ]; then
        fail "app icon has an alpha channel" \
             "Apple rejects icons with transparency on ingest." \
             "Fix: flatten onto an opaque background."
    else
        pass "app icon 1024x1024, no alpha"
    fi
fi

# --- 5. Cross-boundary contract: IAP product IDs ---------------------------
# The iOS Product IDs, the backend catalog, and App Store Connect must agree
# exactly. A mismatch makes Product.products(for:) silently return fewer
# products and the paywall renders empty — with no error anywhere.
echo "--- IAP product IDs (iOS <-> backend) ---"
ios_ids=$(grep -oE '"com\.nickchua\.fitnessapp\.[a-z_0-9]+"' "$IOS/FitnessApp/Services/StoreKitManager.swift" 2>/dev/null | tr -d '"' | sort -u)
be_ids=$(grep -oE '"com\.nickchua\.fitnessapp\.[a-z_0-9]+"' "$BACKEND/app/services/entitlement_service.py" 2>/dev/null | tr -d '"' | sort -u)
if [ -z "$ios_ids" ] || [ -z "$be_ids" ]; then
    warn "could not extract product IDs from one or both sides" "Check the grep targets in this script."
elif [ "$ios_ids" != "$be_ids" ]; then
    fail "IAP product IDs differ between iOS and backend" "$(diff <(echo "$ios_ids") <(echo "$be_ids") | sed 's/^/  /')"
else
    pass "$(echo "$ios_ids" | wc -l | tr -d ' ') product IDs match across iOS and backend"
    echo "$ios_ids" | sed 's/^/       /'
    echo "       These must also exist verbatim in App Store Connect."
fi

# --- 6. API base URL -------------------------------------------------------
echo "--- API base URL ---"
if grep -qE 'baseURL *= *"http://(localhost|127\.0\.0\.1)' "$IOS/FitnessApp/Services/APIClient.swift" 2>/dev/null; then
    # Only a problem if it is not inside a #if DEBUG branch.
    if ! grep -B3 'baseURL *= *"http://localhost' "$IOS/FitnessApp/Services/APIClient.swift" | grep -q "#if DEBUG"; then
        fail "APIClient points at localhost outside a #if DEBUG branch" \
             "A shipped build would talk to nothing."
    fi
fi
prod=$(grep -oE 'https://[a-z0-9.-]+\.up\.railway\.app' "$IOS/FitnessApp/Services/APIClient.swift" 2>/dev/null | head -1)
[ -n "$prod" ] && pass "release base URL: $prod" || warn "no production base URL found in APIClient.swift"

# --- 7. Required public URLs ----------------------------------------------
# App Store Connect requires a reachable privacy policy URL and support URL.
echo "--- Public URLs ---"
if [ -n "${prod:-}" ]; then
    for path in privacy terms support; do
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 12 "$prod/$path" 2>/dev/null || echo "000")
        if [ "$code" = "200" ]; then
            pass "$prod/$path -> 200"
        else
            fail "$prod/$path -> $code" "App Store Connect needs a live privacy policy and support URL."
        fi
    done
else
    warn "skipped URL checks (no base URL)"
fi

# --- 8. Release build settings --------------------------------------------
echo "--- Release build settings ---"
if [ -d "$IOS/FitnessApp.xcodeproj" ]; then
    fam=$(xcodebuild -project "$IOS/FitnessApp.xcodeproj" -target FitnessApp -configuration Release -showBuildSettings 2>/dev/null | awk '/ TARGETED_DEVICE_FAMILY =/ {print $3}')
    if [ "$fam" = "1" ]; then
        pass "iPhone only (TARGETED_DEVICE_FAMILY = 1)"
    else
        warn "TARGETED_DEVICE_FAMILY is '$fam', expected 1 (iPhone only)" \
             "Claiming iPad obligates a separate iPad screenshot set and an" \
             "iPad-worthy layout. Decided iPhone-only 2026-09-06; see" \
             "docs/app-store-launch.md Phase 0.3."
    fi

    rel_ent=$(xcodebuild -project "$IOS/FitnessApp.xcodeproj" -target FitnessApp -configuration Release -showBuildSettings 2>/dev/null | awk '/ CODE_SIGN_ENTITLEMENTS =/ {print $3}')
    if [ "$rel_ent" = "FitnessApp/FitnessAppRelease.entitlements" ]; then
        pass "Release uses production entitlements ($rel_ent)"
    else
        fail "Release CODE_SIGN_ENTITLEMENTS is '$rel_ent'" \
             "Expected FitnessApp/FitnessAppRelease.entitlements (aps-environment=production)." \
             "Run xcodegen generate; check settings.configs in ios/project.yml."
    fi
else
    warn "FitnessApp.xcodeproj not found" "Run: cd ios && xcodegen generate"
fi

# --- Summary ---------------------------------------------------------------
echo "========================================"
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}Preflight passed.${NC} $WARNINGS warning(s)."
    echo ""
    echo "Still requires a human (see docs/app-store-launch.md):"
    echo "  - Paid Applications Agreement active in App Store Connect"
    echo "  - IAP products created in ASC with matching IDs + review screenshots"
    echo "  - Screenshots captured from the real app"
    echo "  - Demo account credentials in App Review Notes"
    exit 0
else
    echo -e "${RED}Preflight failed: $ISSUES issue(s), $WARNINGS warning(s).${NC}"
    exit 1
fi
