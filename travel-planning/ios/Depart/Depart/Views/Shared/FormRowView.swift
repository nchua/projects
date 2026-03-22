import SwiftUI

/// Reusable form row: icon + label + value + chevron.
struct FormRowView: View {
    let icon: String
    let label: String
    var value: String = ""
    var showChevron: Bool = true

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 15))
                .foregroundStyle(Color.departPrimary)
                .frame(width: 24)

            Text(label)
                .font(.departBody)
                .foregroundStyle(Color.departTextPrimary)

            Spacer()

            if !value.isEmpty {
                Text(value)
                    .font(.departCallout)
                    .foregroundStyle(Color.departTextSecondary)
                    .lineLimit(1)
            }

            if showChevron {
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color.departTextSecondary.opacity(0.5))
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(label)
        .accessibilityValue(value)
    }
}
