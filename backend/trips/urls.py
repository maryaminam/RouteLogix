from django.urls import path
from .views import TripPlanView, TripDetailView, LocationSearchView

urlpatterns = [
    path("trips/plan/", TripPlanView.as_view(), name="trip-plan"),
    path("trips/<int:pk>/", TripDetailView.as_view(), name="trip-detail"),
    path("locations/search/", LocationSearchView.as_view(), name="location-search"),
]
