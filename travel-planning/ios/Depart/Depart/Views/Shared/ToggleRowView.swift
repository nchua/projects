import SwiftUI

/// Reusable toggle row: icon + label + description + toggle.
struct ToggleRowView: View {
    let icon: String
    let label: String
    var description: String?
    @Binding var isOn: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 15))
                .foregroundStyle(Color.departPrimary)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.departBody)
                    .foregroundStyle(Color.departTextPrimary)

                if let description {
                    Text(description)
                        .font(.departCaption)
                        .foregroundStyle(Color.departTextSecondary)
                }
            }

            Spacer()

            Toggle("", isOn: $isOn)
                .labelsHidden()
                .tint(Color.departPrimary)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(label)
        .accessibilityValue(isOn ? "On" : "Off")
        .accessibilityAddTraits(.isButton)
    }
}
