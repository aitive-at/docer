from django.urls import path

from . import views

app_name = "auth"

urlpatterns = [
    path("login", views.DocerLoginView.as_view(), name="login"),
    path("signup", views.signup_view, name="signup"),
    path("logout", views.logout_view, name="logout"),
]
