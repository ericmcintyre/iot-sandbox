from django.urls import path

from devices.views import PayloadIngestView

urlpatterns = [
    path("payloads/", PayloadIngestView.as_view(), name="payload-ingest"),
]
