"""Validation tests for the signup form."""
from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, Membership, User


@pytest.mark.django_db
def test_signup_requires_email():
    c = Client()
    resp = c.post(reverse("auth:signup"), data={"display_name": "Just A Name", "password": "secret123"})
    assert resp.status_code == 200, "Expected re-render with errors, not redirect"
    assert b"Email is required" in resp.content
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_signup_requires_password():
    c = Client()
    resp = c.post(reverse("auth:signup"), data={"email": "a@b.com", "display_name": "A B"})
    assert resp.status_code == 200
    assert b"Password is required" in resp.content
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_signup_rejects_invalid_email():
    c = Client()
    resp = c.post(reverse("auth:signup"), data={"email": "not-an-email", "password": "secret123"})
    assert resp.status_code == 200
    assert b"valid email" in resp.content.lower()
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_signup_rejects_short_password():
    c = Client()
    resp = c.post(reverse("auth:signup"), data={"email": "a@b.com", "password": "1234"})
    assert resp.status_code == 200
    assert b"at least 6" in resp.content.lower() or b"6 characters" in resp.content
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_signup_rejects_duplicate_email():
    User.objects.create_user(username="dup@example.com", email="dup@example.com", password="x" * 12)
    c = Client()
    resp = c.post(reverse("auth:signup"), data={"email": "DUP@example.com", "password": "secret123"})
    assert resp.status_code == 200
    assert b"already exists" in resp.content
    assert User.objects.filter(email__iexact="dup@example.com").count() == 1


@pytest.mark.django_db
def test_signup_creates_user_and_account_and_logs_in():
    c = Client()
    resp = c.post(
        reverse("auth:signup"),
        data={"email": "alice@example.com", "display_name": "Alice", "password": "secret123"},
    )
    # Successful signup redirects into the new account dashboard.
    assert resp.status_code in (302, 303), resp.content[:500]
    user = User.objects.get(email__iexact="alice@example.com")
    assert user.first_name == "Alice"
    assert Membership.objects.filter(user=user, role=Membership.OWNER).count() == 1
    account = Account.objects.get(memberships__user=user)
    assert resp.url.startswith(f"/{account.slug}")
    # And the user is logged in.
    follow = c.get(resp.url)
    assert follow.status_code == 200


@pytest.mark.django_db
def test_login_uses_email_as_username():
    """Sanity: signup-created users can immediately log in by email."""
    c = Client()
    c.post(
        reverse("auth:signup"),
        data={"email": "bob@example.com", "password": "secret123"},
    )
    c.logout()
    resp = c.post(reverse("auth:login"), data={"username": "bob@example.com", "password": "secret123"})
    assert resp.status_code in (302, 303), resp.content[:500]
