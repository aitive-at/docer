from __future__ import annotations

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import EmailLoginForm, SignupForm
from .models import Membership
from .services import create_personal_account


class DocerLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        membership = (
            Membership.objects.filter(user=self.request.user)
            .select_related("account")
            .first()
        )
        if membership:
            return f"/{membership.account.slug}/"
        return "/"


def signup_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        membership = (
            Membership.objects.filter(user=request.user).select_related("account").first()
        )
        if membership:
            return redirect(f"/{membership.account.slug}/")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            account = create_personal_account(
                user, base_name=form.cleaned_data.get("display_name") or None
            )
            login(request, user)
            return redirect(f"/{account.slug}/")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("auth:login")
