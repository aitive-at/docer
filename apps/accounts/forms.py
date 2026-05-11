from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from .models import User


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))


class SignupForm(forms.Form):
    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email", "required": "required"}),
        error_messages={"required": "Email is required.", "invalid": "Enter a valid email address."},
    )
    password = forms.CharField(
        required=True,
        label="Password",
        min_length=6,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "required": "required"}),
        error_messages={"required": "Password is required.", "min_length": "Password must be at least 6 characters."},
    )
    display_name = forms.CharField(
        max_length=120,
        required=False,
        label="Display name",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").lower().strip()
        if not email:
            raise forms.ValidationError("Email is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password(self) -> str:
        pw = self.cleaned_data.get("password") or ""
        if not pw:
            raise forms.ValidationError("Password is required.")
        validate_password(pw)
        return pw

    def save(self) -> User:
        email = self.cleaned_data["email"]
        user = User(
            username=email,
            email=email,
            first_name=(self.cleaned_data.get("display_name") or "")[:30],
        )
        user.set_password(self.cleaned_data["password"])
        user.save()
        return user
