from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("<slug:account_slug>/scanners", views.scanner_list_create, name="scanner_list_create"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>", views.scanner_detail, name="scanner_detail"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>/scan", views.scanner_scan, name="scanner_scan"),
    path("<slug:account_slug>/scans/<int:scan_id>", views.scan_detail, name="scan_detail"),
    path("<slug:account_slug>/scans/<int:scan_id>/pages/<int:index>.png", views.scan_page_image, name="scan_page_image"),
]
