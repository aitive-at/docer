from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("apps.accounts.urls", namespace="auth")),
    path("api/v1/", include("apps.api.urls", namespace="api")),
    path("", include("apps.web.urls", namespace="web")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
