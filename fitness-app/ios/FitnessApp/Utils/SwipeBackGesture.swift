import UIKit

/// Re-enables the native iOS swipe-back gesture on all pushed views,
/// even when `.navigationBarHidden(true)` is set.
/// UIKit disables `interactivePopGestureRecognizer` when the nav bar is hidden;
/// this extension re-enables it globally by becoming the gesture's delegate.
extension UINavigationController: @retroactive UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }

    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        return viewControllers.count > 1
    }
}
