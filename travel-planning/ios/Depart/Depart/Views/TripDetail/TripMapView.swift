import MapKit
import SwiftUI

/// MapKit map showing route from origin to destination with overlay.
struct TripMapView: UIViewRepresentable {
    let originCoordinate: CLLocationCoordinate2D
    let destCoordinate: CLLocationCoordinate2D
    @Binding var route: MKRoute?

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.isZoomEnabled = true
        mapView.isScrollEnabled = true
        mapView.showsUserLocation = false

        // Add annotations
        let originAnnotation = MKPointAnnotation()
        originAnnotation.coordinate = originCoordinate
        originAnnotation.title = "Start"

        let destAnnotation = MKPointAnnotation()
        destAnnotation.coordinate = destCoordinate
        destAnnotation.title = "Destination"

        mapView.addAnnotations([originAnnotation, destAnnotation])

        // Request route
        fetchRoute(mapView: mapView)

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Route updates handled via binding
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    private func fetchRoute(mapView: MKMapView) {
        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: originCoordinate))
        request.destination = MKMapItem(placemark: MKPlacemark(coordinate: destCoordinate))
        request.transportType = .automobile

        let directions = MKDirections(request: request)
        directions.calculate { response, error in
            guard let response, let route = response.routes.first else {
                print("[TripMapView] Route error: \(error?.localizedDescription ?? "unknown")")
                return
            }

            DispatchQueue.main.async {
                self.route = route
                mapView.addOverlay(route.polyline)

                // Fit map to show entire route with padding
                let rect = route.polyline.boundingMapRect
                let padding = UIEdgeInsets(top: 60, left: 40, bottom: 60, right: 40)
                mapView.setVisibleMapRect(rect, edgePadding: padding, animated: false)
            }
        }
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, MKMapViewDelegate {
        let parent: TripMapView

        init(_ parent: TripMapView) {
            self.parent = parent
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let polyline = overlay as? MKPolyline {
                let renderer = MKPolylineRenderer(polyline: polyline)
                renderer.strokeColor = UIColor(Color.departPrimary)
                renderer.lineWidth = 5
                return renderer
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard !(annotation is MKUserLocation) else { return nil }

            let identifier = "TripPin"
            let view = mapView.dequeueReusableAnnotationView(withIdentifier: identifier)
                ?? MKMarkerAnnotationView(annotation: annotation, reuseIdentifier: identifier)

            if let markerView = view as? MKMarkerAnnotationView {
                if annotation.title == "Start" {
                    markerView.markerTintColor = UIColor(Color.departPrimary)
                    markerView.glyphImage = UIImage(systemName: "circle.fill")
                } else {
                    markerView.markerTintColor = UIColor(Color.departRed)
                    markerView.glyphImage = UIImage(systemName: "mappin")
                }
            }

            return view
        }
    }
}
