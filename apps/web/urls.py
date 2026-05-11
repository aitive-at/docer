from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.root_redirect, name="root"),
    path("<slug:account_slug>/", views.dashboard, name="dashboard"),
    path("<slug:account_slug>/scanners/", views.scanner_list, name="scanner_list"),
    path("<slug:account_slug>/scanners/new", views.scanner_create, name="scanner_create"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>/", views.scanner_detail, name="scanner_detail"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>/edit", views.scanner_edit, name="scanner_edit"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>/copy", views.scanner_copy, name="scanner_copy"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>/delete", views.scanner_delete, name="scanner_delete"),
    path("<slug:account_slug>/scanners/<slug:scanner_slug>/scan", views.scan_create, name="scan_create"),
    path("<slug:account_slug>/scans/<int:scan_id>/", views.scan_detail, name="scan_detail"),
    path("<slug:account_slug>/scans/<int:scan_id>/page/<int:index>.png", views.scan_page_image, name="scan_page_image"),
    path("<slug:account_slug>/scans/<int:scan_id>/progress", views.scan_progress_fragment, name="scan_progress"),
    path("<slug:account_slug>/settings/api-keys", views.api_keys, name="api_keys"),
]
