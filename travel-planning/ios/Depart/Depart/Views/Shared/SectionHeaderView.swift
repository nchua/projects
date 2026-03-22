import SwiftUI

/// Uppercase caption-2 section title with optional trailing content.
struct SectionHeaderView: View {
    let title: String
    var trailing: String?

    var body: some View {
        HStack {
            Text(title)
                .departSectionTitle()

            Spacer()

            if let trailing {
                Text(trailing)
                    .font(.departCaption)
                    .foregroundStyle(Color.departTextSecondary)
            }
        }
        .padding(.horizontal, 4)
    }
}
