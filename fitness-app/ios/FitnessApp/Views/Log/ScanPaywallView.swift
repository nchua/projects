import SwiftUI
import StoreKit

struct ScanPaywallView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var storeKitManager: StoreKitManager

    let onPurchaseComplete: () -> Void

    enum SelectedTier: String {
        case quick = "com.nickchua.fitnessapp.scan_20"
        case power = "com.nickchua.fitnessapp.scan_50"
        case srank = "com.nickchua.fitnessapp.scan_unlimited"
    }

    @State private var selectedTier: SelectedTier = .power
    @State private var showSuccess = false
    @State private var purchasedProduct: Product?

    private var selectedProduct: Product? {
        storeKitManager.products.first { $0.id == selectedTier.rawValue }
    }

    var body: some View {
        ZStack {
            Color.bgVoid.ignoresSafeArea()

            if showSuccess {
                successView
            } else {
                paywallContent
            }
        }
        .task {
            await storeKitManager.loadProducts()
        }
    }

    // MARK: - Paywall Content

    private var paywallContent: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Close button
                HStack {
                    Spacer()
                    Button {
                        dismiss()
                    } label: {
                        ZStack {
                            Circle()
                                .fill(Color.white.opacity(0.06))
                                .frame(width: 30, height: 30)
                                .overlay(
                                    Circle().stroke(Color.white.opacity(0.08), lineWidth: 1)
                                )
                            Image(systemName: "xmark")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.textSecondary)
                        }
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)

                // Hero icon with glow
                ZStack {
                    Circle()
                        .fill(Color.systemPrimary.opacity(0.06))
                        .frame(width: 140, height: 140)
                        .blur(radius: 40)

                    RoundedRectangle(cornerRadius: 20)
                        .fill(
                            LinearGradient(
                                colors: [Color.systemPrimary.opacity(0.12), Color.systemPrimary.opacity(0.04)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 72, height: 72)
                        .overlay(
                            RoundedRectangle(cornerRadius: 20)
                                .stroke(Color.systemPrimary.opacity(0.15), lineWidth: 1)
                        )
                        .overlay(
                            Image(systemName: "viewfinder")
                                .font(.system(size: 34))
                                .foregroundColor(.systemPrimary)
                        )
                }
                .padding(.vertical, 16)

                // Header
                VStack(spacing: 6) {
                    Text("SCREENSHOT SCANNER")
                        .font(.ariseHeader(size: 22, weight: .bold))
                        .foregroundColor(.textPrimary)
                        .tracking(3)

                    Text("AI-powered workout extraction from your gym app screenshots")
                        .font(.ariseBody(size: 13))
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(2)
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 6)

                // Usage depleted bar
                usageDepletedBar
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)

                // Tier cards
                VStack(spacing: 10) {
                    quickPackCard
                    powerPackCard
                    sRankCard
                }
                .padding(.horizontal, 20)

                // Features
                featuresSection
                    .padding(.horizontal, 20)
                    .padding(.top, 12)

                // Purchase button
                purchaseButton
                    .padding(.horizontal, 20)
                    .padding(.top, 16)

                // Bottom links
                HStack(spacing: 16) {
                    Button("Restore Purchases") {
                        Task { await storeKitManager.restorePurchases() }
                    }
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)

                    Circle().fill(Color.textMuted).frame(width: 3, height: 3)

                    Link("Terms", destination: URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!)
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)

                    Circle().fill(Color.textMuted).frame(width: 3, height: 3)

                    Link("Privacy", destination: URL(string: "https://backend-production-e316.up.railway.app/privacy")!)
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }
                .padding(.top, 12)
                .padding(.bottom, 40)
            }
        }
    }

    // MARK: - Usage Depleted Bar

    private var usageDepletedBar: some View {
        VStack(spacing: 8) {
            HStack {
                Text("MONTHLY FREE SCANS")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Spacer()

                Text("\(storeKitManager.scanBalance?.scanCredits ?? 0) / 3")
                    .font(.ariseDisplay(size: 13, weight: .bold))
                    .foregroundColor(.warningRed)
            }

            // Bar track
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.voidLight)
                        .frame(height: 5)

                    RoundedRectangle(cornerRadius: 3)
                        .fill(
                            LinearGradient(
                                colors: [Color.warningRed.opacity(0.3), Color.warningRed.opacity(0.15)],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width, height: 5)
                }
            }
            .frame(height: 5)

            HStack {
                Text("Free quota resets monthly")
                    .font(.ariseMono(size: 9))
                    .foregroundColor(.textMuted)
                Spacer()
            }
        }
        .padding(14)
        .background(Color.bgCard)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.warningRed.opacity(0.15), lineWidth: 1)
        )
    }

    // MARK: - Tier Cards

    private var quickPackCard: some View {
        tierCard(
            tier: .quick,
            iconName: "square.grid.2x2",
            iconColor: .textSecondary,
            iconBgColor: Color(hex: "A0A0B0").opacity(0.08),
            iconBorderColor: Color(hex: "A0A0B0").opacity(0.1),
            name: "QUICK PACK",
            detail: "20 scans",
            perScan: "~$0.10 / scan",
            price: "$1.99",
            priceUnit: "one-time",
            badge: nil,
            isPremium: false
        )
    }

    private var powerPackCard: some View {
        tierCard(
            tier: .power,
            iconName: "bolt.fill",
            iconColor: .systemPrimary,
            iconBgColor: Color.systemPrimary.opacity(0.08),
            iconBorderColor: Color.systemPrimary.opacity(0.12),
            name: "POWER PACK",
            detail: "50 scans",
            perScan: "~$0.08 / scan",
            price: "$3.99",
            priceUnit: "one-time",
            badge: "BEST VALUE",
            isPremium: false
        )
    }

    private var sRankCard: some View {
        tierCard(
            tier: .srank,
            iconName: "star.fill",
            iconColor: .gold,
            iconBgColor: Color.gold.opacity(0.08),
            iconBorderColor: Color.gold.opacity(0.12),
            name: "S-RANK SCANNER",
            detail: "Unlimited scans forever",
            perScan: nil,
            price: "$9.99",
            priceUnit: "lifetime",
            badge: "ONE-TIME PURCHASE",
            isPremium: true
        )
    }

    private func tierCard(
        tier: SelectedTier,
        iconName: String,
        iconColor: Color,
        iconBgColor: Color,
        iconBorderColor: Color,
        name: String,
        detail: String,
        perScan: String?,
        price: String,
        priceUnit: String,
        badge: String?,
        isPremium: Bool
    ) -> some View {
        let isSelected = selectedTier == tier

        return Button {
            withAnimation(.easeOut(duration: 0.2)) {
                selectedTier = tier
            }
        } label: {
            ZStack(alignment: .topTrailing) {
                HStack(spacing: 14) {
                    // Selection indicator
                    ZStack {
                        if isSelected {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(isPremium ? Color.gold : Color.systemPrimary)
                                .frame(width: 3, height: 24)
                                .shadow(color: isPremium ? Color.glowGold : Color.systemPrimaryGlow, radius: 6)
                        }
                    }
                    .frame(width: 3)

                    // Icon
                    ZStack {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(iconBgColor)
                            .frame(width: 42, height: 42)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(iconBorderColor, lineWidth: 1)
                            )

                        Image(systemName: iconName)
                            .font(.system(size: 18))
                            .foregroundColor(iconColor)
                    }

                    // Content
                    VStack(alignment: .leading, spacing: 2) {
                        Text(name)
                            .font(.ariseHeader(size: 15, weight: .bold))
                            .foregroundColor(isPremium ? .gold : .textPrimary)
                            .tracking(1)

                        HStack(spacing: 6) {
                            Text(detail)
                                .font(.ariseBody(size: 12))
                                .foregroundColor(.textSecondary)

                            if let perScan = perScan {
                                Text(perScan)
                                    .font(.ariseMono(size: 10))
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }

                    Spacer()

                    // Price
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(price)
                            .font(.ariseDisplay(size: 18, weight: .bold))
                            .foregroundColor(isPremium ? .gold : .textPrimary)

                        Text(priceUnit)
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }
                }
                .padding(14)

                // Badge
                if let badge = badge {
                    Text(badge)
                        .font(.ariseMono(size: 8, weight: .bold))
                        .tracking(1.5)
                        .foregroundColor(.bgVoid)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 3)
                        .background(isPremium ? Color.gold : Color.systemPrimary)
                        .cornerRadius(4)
                        .shadow(color: isPremium ? Color.glowGold : Color.systemPrimaryGlow, radius: 6)
                        .offset(y: -8)
                        .padding(.trailing, 16)
                }
            }
        }
        .background(
            Group {
                if isPremium {
                    LinearGradient(
                        colors: [Color.bgCard, Color.gold.opacity(isSelected ? 0.06 : 0.03)],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                } else {
                    Color.bgCard
                        .opacity(isSelected ? 1 : 1)
                        .overlay(Color.systemPrimary.opacity(isSelected ? 0.04 : 0))
                }
            }
        )
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(
                    isSelected
                        ? (isPremium ? Color.gold.opacity(0.4) : Color.systemPrimary.opacity(0.4))
                        : (isPremium ? Color.gold.opacity(0.15) : Color.white.opacity(0.04)),
                    lineWidth: 1.5
                )
        )
        .shadow(
            color: isSelected
                ? (isPremium ? Color.glowGold.opacity(0.3) : Color.systemPrimaryGlow.opacity(0.3))
                : .clear,
            radius: 12
        )
    }

    // MARK: - Features Section

    private var featuresSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("WHAT YOU GET")
                .font(.ariseMono(size: 9, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1.5)
                .padding(.bottom, 2)

            featureRow("AI extracts exercises, sets, reps & weight")
            featureRow("Supports multiple gym app formats")
            featureRow("Auto-creates workout entries with PRs")
        }
    }

    private func featureRow(_ text: String) -> some View {
        HStack(spacing: 10) {
            ZStack {
                Circle()
                    .fill(Color.successGreen.opacity(0.08))
                    .frame(width: 18, height: 18)
                    .overlay(
                        Circle().stroke(Color.successGreen.opacity(0.15), lineWidth: 1)
                    )

                Image(systemName: "checkmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.successGreen)
            }

            Text(text)
                .font(.ariseBody(size: 12))
                .foregroundColor(.textSecondary)
        }
    }

    // MARK: - Purchase Button

    private var purchaseButton: some View {
        let isPremium = selectedTier == .srank
        let buttonText: String
        let buttonColor: Color

        switch selectedTier {
        case .quick:
            buttonText = "PURCHASE — $1.99"
            buttonColor = .systemPrimary
        case .power:
            buttonText = "PURCHASE — $3.99"
            buttonColor = .systemPrimary
        case .srank:
            buttonText = "UNLOCK S-RANK — $9.99"
            buttonColor = .gold
        }

        return Button {
            guard let product = selectedProduct else { return }
            Task {
                let success = await storeKitManager.purchase(product)
                if success {
                    purchasedProduct = product
                    withAnimation(.easeOut(duration: 0.3)) {
                        showSuccess = true
                    }
                }
            }
        } label: {
            HStack(spacing: 8) {
                if storeKitManager.isPurchasing {
                    ProgressView()
                        .tint(Color.bgVoid)
                    Text("PROCESSING...")
                        .font(.ariseHeader(size: 16, weight: .bold))
                        .tracking(2)
                } else {
                    Text(buttonText)
                        .font(.ariseHeader(size: 16, weight: .bold))
                        .tracking(2)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 50)
            .background(
                LinearGradient(
                    colors: isPremium
                        ? [Color.gold, Color(hex: "C9A800")]
                        : [Color.systemPrimary, Color.systemPrimaryDim],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .foregroundColor(.bgVoid)
            .cornerRadius(14)
            .shadow(
                color: isPremium ? Color.glowGold : Color.systemPrimaryGlow,
                radius: 12
            )
        }
        .disabled(storeKitManager.isPurchasing || selectedProduct == nil)
    }

    // MARK: - Success View

    private var successView: some View {
        let isPremium = purchasedProduct?.id == StoreKitManager.scanUnlimited
        let balance = storeKitManager.scanBalance

        return VStack(spacing: 20) {
            Spacer()

            // Success ring
            ZStack {
                Circle()
                    .stroke(
                        isPremium ? Color.gold.opacity(0.2) : Color.systemPrimary.opacity(0.2),
                        lineWidth: 2
                    )
                    .frame(width: 96, height: 96)
                    .shadow(
                        color: isPremium ? Color.glowGold : Color.systemPrimaryGlow,
                        radius: 20
                    )

                Circle()
                    .fill(isPremium ? Color.gold.opacity(0.06) : Color.systemPrimary.opacity(0.06))
                    .frame(width: 96, height: 96)

                if isPremium {
                    Image(systemName: "star.fill")
                        .font(.system(size: 40))
                        .foregroundColor(.gold)
                } else {
                    Image(systemName: "checkmark")
                        .font(.system(size: 36, weight: .medium))
                        .foregroundColor(.systemPrimary)
                }
            }

            // Text
            VStack(spacing: 8) {
                Text(isPremium ? "S-RANK UNLOCKED" : "PURCHASE COMPLETE")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(isPremium ? .gold : .systemPrimary)
                    .tracking(2)

                Text(isPremium ? "Unlimited Scanner" : "Power Pack Activated")
                    .font(.ariseHeader(size: 22, weight: .bold))
                    .foregroundColor(.textPrimary)

                Text(isPremium
                     ? "You now have unlimited screenshot scanning. No quotas, no limits — forever."
                     : "\(storeKitManager.lastPurchaseResult?.creditsAdded ?? 0) screenshot scans have been added to your account.")
                    .font(.ariseBody(size: 14))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(2)
            }
            .padding(.horizontal, 32)

            // Balance card
            VStack(spacing: 6) {
                Text("AVAILABLE SCANS")
                    .font(.ariseMono(size: 9, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1.5)

                if isPremium || (balance?.hasUnlimited == true) {
                    Text("∞")
                        .font(.ariseDisplay(size: 32, weight: .bold))
                        .foregroundColor(.gold)

                    Text("UNLIMITED FOREVER")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(Color(hex: "C9A800"))
                        .tracking(1)
                } else {
                    Text("\(balance?.scanCredits ?? 0)")
                        .font(.ariseDisplay(size: 32, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text("SCREENSHOTS REMAINING")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(16)
            .background(Color.bgCard)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(
                        isPremium ? Color.gold.opacity(0.12) : Color.white.opacity(0.04),
                        lineWidth: 1
                    )
            )
            .padding(.horizontal, 32)

            Spacer()

            // CTA button
            Button {
                dismiss()
                onPurchaseComplete()
            } label: {
                Text("SCAN A SCREENSHOT")
                    .font(.ariseHeader(size: 16, weight: .bold))
                    .tracking(2)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .background(
                        LinearGradient(
                            colors: isPremium
                                ? [Color.gold, Color(hex: "C9A800")]
                                : [Color.systemPrimary, Color.systemPrimaryDim],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .foregroundColor(.bgVoid)
                    .cornerRadius(14)
                    .shadow(
                        color: isPremium ? Color.glowGold : Color.systemPrimaryGlow,
                        radius: 12
                    )
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 40)
        }
    }
}
