import SwiftUI

/// Banner shown when the device is offline.
struct OfflineBannerView: View {
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 14))
            Text("Can't check traffic. Using last known conditions.")
                .font(.departCaption)
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity)
        .background(Color.departOrange)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}
