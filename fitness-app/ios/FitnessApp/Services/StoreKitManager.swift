import Foundation
import StoreKit
import SwiftUI

@MainActor
class StoreKitManager: ObservableObject {
    static let shared = StoreKitManager()

    // Product IDs
    static let scan20 = "com.nickchua.fitnessapp.scan_20"
    static let scan50 = "com.nickchua.fitnessapp.scan_50"
    static let scanUnlimited = "com.nickchua.fitnessapp.scan_unlimited"

    @Published var products: [Product] = []
    @Published var scanBalance: ScanBalanceResponse?
    @Published var isPurchasing = false
    @Published var purchaseError: String?
    @Published var lastPurchaseResult: PurchaseVerifyResponse?

    private var transactionListener: Task<Void, Never>?

    var canScan: Bool {
        guard let balance = scanBalance else { return true } // Assume yes until loaded
        return balance.hasUnlimited || balance.scanCredits > 0
    }

    var creditsDisplay: String {
        guard let balance = scanBalance else { return "..." }
        if balance.hasUnlimited { return "∞" }
        return "\(balance.scanCredits)"
    }

    private init() {
        transactionListener = listenForTransactions()
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Load Products

    func loadProducts() async {
        do {
            let productIDs: Set<String> = [
                Self.scan20,
                Self.scan50,
                Self.scanUnlimited
            ]
            let storeProducts = try await Product.products(for: productIDs)
            // Sort: scan_20, scan_50, scan_unlimited
            products = storeProducts.sorted { a, b in
                let order: [String: Int] = [
                    Self.scan20: 0,
                    Self.scan50: 1,
                    Self.scanUnlimited: 2
                ]
                return (order[a.id] ?? 99) < (order[b.id] ?? 99)
            }
        } catch {
            print("Failed to load products: \(error)")
        }
    }

    // MARK: - Fetch Balance

    func fetchBalance() async {
        do {
            scanBalance = try await APIClient.shared.getScanBalance()
        } catch {
            print("Failed to fetch scan balance: \(error)")
        }
    }

    // MARK: - Purchase

    func purchase(_ product: Product) async -> Bool {
        isPurchasing = true
        purchaseError = nil
        lastPurchaseResult = nil

        do {
            let result = try await product.purchase()

            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)

                // Verify with backend
                let verifyResponse = try await APIClient.shared.verifyPurchase(
                    transactionId: String(transaction.id),
                    productId: product.id,
                    signedTransaction: nil
                )
                lastPurchaseResult = verifyResponse

                // Update local balance
                await fetchBalance()

                // Finish the transaction
                await transaction.finish()

                isPurchasing = false
                return true

            case .userCancelled:
                isPurchasing = false
                return false

            case .pending:
                purchaseError = "Purchase is pending approval."
                isPurchasing = false
                return false

            @unknown default:
                isPurchasing = false
                return false
            }
        } catch {
            purchaseError = error.localizedDescription
            isPurchasing = false
            return false
        }
    }

    // MARK: - Restore Purchases

    func restorePurchases() async {
        do {
            try await AppStore.sync()

            // Check for unlimited entitlement
            for await result in Transaction.currentEntitlements {
                if let transaction = try? checkVerified(result) {
                    if transaction.productID == Self.scanUnlimited {
                        // Verify with backend
                        let _ = try? await APIClient.shared.verifyPurchase(
                            transactionId: String(transaction.id),
                            productId: transaction.productID,
                            signedTransaction: nil
                        )
                    }
                }
            }

            // Refresh balance from backend
            await fetchBalance()
        } catch {
            purchaseError = "Failed to restore purchases: \(error.localizedDescription)"
        }
    }

    // MARK: - Transaction Listener

    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached { [weak self] in
            for await result in Transaction.updates {
                if let transaction = try? self?.checkVerified(result) {
                    // Verify with backend
                    let _ = try? await APIClient.shared.verifyPurchase(
                        transactionId: String(transaction.id),
                        productId: transaction.productID,
                        signedTransaction: nil
                    )
                    await transaction.finish()
                    await self?.fetchBalance()
                }
            }
        }
    }

    // MARK: - Helpers

    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified(_, let error):
            throw error
        case .verified(let value):
            return value
        }
    }
}
