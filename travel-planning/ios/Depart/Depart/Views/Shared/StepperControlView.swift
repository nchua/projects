import SwiftUI

/// Generic stepper with - / value / + layout.
struct StepperControlView: View {
    let label: String
    @Binding var value: Int
    let range: ClosedRange<Int>
    let step: Int
    let unit: String

    init(
        _ label: String,
        value: Binding<Int>,
        in range: ClosedRange<Int> = 0...120,
        step: Int = 5,
        unit: String = "min"
    ) {
        self.label = label
        self._value = value
        self.range = range
        self.step = step
        self.unit = unit
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label)
                .font(.departCaption)
                .foregroundStyle(Color.departTextSecondary)

            HStack(spacing: 0) {
                Button {
                    let newValue = value - step
                    if newValue >= range.lowerBound {
                        value = newValue
                    }
                } label: {
                    Image(systemName: "minus")
                        .font(.system(size: 16, weight: .semibold))
                        .frame(width: 44, height: 44)
                }
                .disabled(value <= range.lowerBound)
                .accessibilityLabel("Decrease \(label)")

                Text("\(value) \(unit)")
                    .font(.departHeadline)
                    .frame(minWidth: 60)
                    .accessibilityLabel(label)
                    .accessibilityValue("\(value) \(unit)")

                Button {
                    let newValue = value + step
                    if newValue <= range.upperBound {
                        value = newValue
                    }
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 16, weight: .semibold))
                        .frame(width: 44, height: 44)
                }
                .disabled(value >= range.upperBound)
                .accessibilityLabel("Increase \(label)")
            }
            .background(Color.departSurface)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }
}
