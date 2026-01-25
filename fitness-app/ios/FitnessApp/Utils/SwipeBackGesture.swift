import SwiftUI

/// A ViewModifier that adds swipe-from-left-edge gesture to dismiss views.
/// Use this on views with `.navigationBarHidden(true)` and custom back buttons
/// to restore the expected iOS swipe-back navigation behavior.
struct SwipeBackGesture: ViewModifier {
    @Environment(\.dismiss) private var dismiss
    @GestureState private var dragOffset: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .offset(x: dragOffset)
            .gesture(
                DragGesture()
                    .updating($dragOffset) { value, state, _ in
                        // Only allow right swipe starting from left edge (within 50pt)
                        if value.startLocation.x < 50 && value.translation.width > 0 {
                            state = value.translation.width
                        }
                    }
                    .onEnded { value in
                        // Dismiss if swiped far enough (100pt) from left edge
                        if value.startLocation.x < 50 && value.translation.width > 100 {
                            dismiss()
                        }
                    }
            )
            .animation(.interactiveSpring(), value: dragOffset)
    }
}

extension View {
    /// Adds a swipe-from-left-edge gesture that dismisses the view.
    /// Apply to views that hide the navigation bar and use custom back buttons.
    func swipeBackGesture() -> some View {
        modifier(SwipeBackGesture())
    }
}
