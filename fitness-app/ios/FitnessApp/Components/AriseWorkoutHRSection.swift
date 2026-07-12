import SwiftUI

/// Session-level heart-rate block shared by the Home recent-workout card and the
/// History workout-detail screen. Renders avg/peak BPM `StatCard`s, a strain card
/// (WHOOP-only), and an `AriseHRZoneBar`, under a section header carrying the
/// provenance badge.
///
/// Every field is optional: when the workout has no HR data the whole view is
/// `EmptyView` (gated on `hasHRData`), so a legacy / non-HR workout renders
/// byte-identically to before. Strain is shown ONLY for WHOOP sessions — it is
/// absent (not "—") on Apple-Watch sessions, which never carry strain.
struct AriseWorkoutHRSection: View {
    let workout: WorkoutResponse
    var title: String = "Biometrics"

    var body: some View {
        if workout.hasHRData {
            VStack(alignment: .leading, spacing: 12) {
                AriseSectionHeader(
                    title: title,
                    trailing: AnyView(AriseSourceBadge(source: workout.hrSource))
                )

                HStack(spacing: 12) {
                    if let avg = workout.avgHeartRate {
                        StatCard(
                            icon: "heart.fill",
                            value: "\(avg)",
                            label: "AVG BPM",
                            useSystemIcon: true,
                            valueColor: .systemPrimary
                        )
                    }
                    if let peak = workout.peakHeartRate {
                        StatCard(
                            icon: "heart.fill",
                            value: "\(peak)",
                            label: "PEAK BPM",
                            useSystemIcon: true,
                            valueColor: .warningRed,
                            showGlow: true
                        )
                    }
                    // Unified Strain (ARISE v2 §7.1): one metric, source-badged
                    // upstream in the section header. WHOOP strain wins; else
                    // the HR-zone exertion proxy; absent without HR data.
                    if let strain = workout.ariseStrain {
                        StatCard(
                            icon: "bolt.fill",
                            value: String(format: "%.1f", strain.value),
                            label: "STRAIN",
                            useSystemIcon: true,
                            valueColor: .orange
                        )
                    }
                }

                if let zones = workout.hrZoneSeconds,
                   AriseHRZoneBar.hasRenderableZones(zones) {
                    AriseHRZoneBar(zoneSeconds: zones)
                }
            }
        }
    }
}
