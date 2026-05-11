"""Web (HTMX) views."""
from __future__ import annotations

import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from PIL import Image, ImageDraw

from apps.accounts.models import ApiKey, Membership
from apps.canonicalize import list_data_types
from apps.files.models import PageImage
from apps.scanners.models import Scanner
from apps.scans.models import Scan, ScanFieldResult
from apps.scans.tasks import run_scan as run_scan_task

from .forms import ApiKeyForm, ScannerForm, ScanUploadForm


def _editor_context(scanner: Scanner | None) -> dict:
    """Context for the graphical schema editor (Alpine.js)."""
    types = [dt for dt in list_data_types() if dt["key"] != "uid"]
    initial_schema = (scanner.schema_json or {"fields": []}) if scanner else {"fields": []}
    return {
        "editor_data_types": types,
        "editor_initial_schema": initial_schema,
        "editor_max_depth": 6,
    }


def _require_member(request: HttpRequest) -> HttpResponse | None:
    if not request.user.is_authenticated:
        return redirect("auth:login")
    if request.account is None:
        return HttpResponseForbidden("Account context missing")
    if request.account_membership is None:
        return HttpResponseForbidden("Not a member of this account")
    return None


def root_redirect(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("auth:login")
    membership = (
        Membership.objects.filter(user=request.user).select_related("account").first()
    )
    if membership:
        return redirect("web:dashboard", account_slug=membership.account.slug)
    return redirect("auth:logout")


@login_required
def dashboard(request: HttpRequest, account_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    recent = (
        Scan.objects.filter(account=account)
        .select_related("scanner", "file")
        .order_by("-created_at")[:10]
    )
    scanners = Scanner.objects.filter(account=account).order_by("-updated_at")[:5]
    return render(
        request,
        "web/dashboard.html",
        {
            "account": account,
            "recent_scans": recent,
            "scanners": scanners,
        },
    )


@login_required
def scanner_list(request: HttpRequest, account_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scanners = Scanner.objects.filter(account=account).order_by("-updated_at")
    return render(request, "web/scanner_list.html", {"account": account, "scanners": scanners})


@login_required
def scanner_create(request: HttpRequest, account_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    if request.method == "POST":
        form = ScannerForm(request.POST)
        if form.is_valid():
            scanner = form.save(commit=False)
            scanner.account = account
            scanner.schema_json = form.cleaned_data["schema_json_text"]
            scanner.slug = scanner.make_unique_slug(scanner.name)
            scanner.save()
            messages.success(request, "Scanner created.")
            return redirect("web:scanner_detail", account_slug=account.slug, scanner_slug=scanner.slug)
    else:
        form = ScannerForm()
    return render(
        request,
        "web/scanner_form.html",
        {"account": account, "form": form, "scanner": None, **_editor_context(None)},
    )


@login_required
def scanner_edit(request: HttpRequest, account_slug: str, scanner_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scanner = get_object_or_404(Scanner, account=account, slug=scanner_slug)
    if request.method == "POST":
        form = ScannerForm(request.POST, instance=scanner)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.schema_json = form.cleaned_data["schema_json_text"]
            obj.save()
            messages.success(request, "Scanner saved.")
            return redirect("web:scanner_detail", account_slug=account.slug, scanner_slug=scanner.slug)
    else:
        form = ScannerForm(instance=scanner)
    return render(
        request,
        "web/scanner_form.html",
        {"account": account, "form": form, "scanner": scanner, **_editor_context(scanner)},
    )


@login_required
def scanner_detail(request: HttpRequest, account_slug: str, scanner_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scanner = get_object_or_404(Scanner, account=account, slug=scanner_slug)
    recent = scanner.scans.order_by("-created_at")[:8]
    return render(
        request,
        "web/scanner_detail.html",
        {
            "account": account,
            "scanner": scanner,
            "schema_fields": (scanner.schema_json or {}).get("fields", []),
            "recent_scans": recent,
            "scan_count": scanner.scans.count(),
        },
    )


@login_required
def scanner_copy(request: HttpRequest, account_slug: str, scanner_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    if request.method != "POST":
        return redirect("web:scanner_detail", account_slug=account_slug, scanner_slug=scanner_slug)
    account = request.account
    src = get_object_or_404(Scanner, account=account, slug=scanner_slug)
    copy = Scanner(
        account=account,
        name=f"{src.name} (copy)",
        description=src.description,
        priming_prompt=src.priming_prompt,
        language_hint=src.language_hint,
        model_override=src.model_override,
        schema_json=src.schema_json,
    )
    copy.slug = copy.make_unique_slug(copy.name)
    copy.save()
    messages.success(request, f"Copied to “{copy.name}”.")
    return redirect("web:scanner_edit", account_slug=account.slug, scanner_slug=copy.slug)


@login_required
def scanner_delete(request: HttpRequest, account_slug: str, scanner_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    if request.method != "POST":
        return redirect("web:scanner_detail", account_slug=account_slug, scanner_slug=scanner_slug)
    account = request.account
    scanner = get_object_or_404(Scanner, account=account, slug=scanner_slug)
    name = scanner.name
    scanner.delete()
    messages.success(request, f"Deleted scanner “{name}”.")
    return redirect("web:scanner_list", account_slug=account.slug)


@login_required
def scan_create(request: HttpRequest, account_slug: str, scanner_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scanner = get_object_or_404(Scanner, account=account, slug=scanner_slug)
    if request.method == "POST":
        form = ScanUploadForm(request.POST, request.FILES)
        if form.is_valid():
            from apps.files.services import ingest_upload

            uploaded = form.cleaned_data["file"]
            stored = ingest_upload(account, uploaded, original_name=uploaded.name, mime=uploaded.content_type)
            scan = Scan.objects.create(account=account, scanner=scanner, file=stored)
            run_scan_task(scan.id)
            return redirect("web:scan_detail", account_slug=account.slug, scan_id=scan.id)
    else:
        form = ScanUploadForm()
    return render(
        request,
        "web/scan_create.html",
        {"account": account, "scanner": scanner, "form": form},
    )


@login_required
def scan_detail(request: HttpRequest, account_slug: str, scan_id: int) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scan = get_object_or_404(
        Scan.objects.select_related("scanner", "file"), account=account, pk=scan_id
    )
    field_results = list(scan.field_results.all())
    pages = list(scan.file.pages.all())
    return render(
        request,
        "web/scan_detail.html",
        {
            "account": account,
            "scan": scan,
            "field_results": field_results,
            "pages": pages,
        },
    )


@login_required
def scan_progress_fragment(request: HttpRequest, account_slug: str, scan_id: int) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scan = get_object_or_404(
        Scan.objects.select_related("scanner", "file"), account=account, pk=scan_id
    )
    ctx = {"account": account, "scan": scan}
    # When terminal, also feed the OOB result-panel partial.
    if scan.is_terminal():
        ctx["field_results"] = list(scan.field_results.all())
        ctx["pages"] = list(scan.file.pages.all())
    return render(request, "web/_scan_progress.html", ctx)


@login_required
def scan_page_image(
    request: HttpRequest, account_slug: str, scan_id: int, index: int
) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    scan = get_object_or_404(Scan, account=account, pk=scan_id)
    page = scan.file.pages.filter(index=index).first()
    if page is None:
        raise Http404("Page not found")

    from apps.files.services import absolute_page_path

    path = absolute_page_path(page)
    if not path.exists():
        raise Http404("Page image not on disk")

    overlay = request.GET.get("overlay") == "1"
    if not overlay:
        return FileResponse(open(path, "rb"), content_type="image/png")

    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    boxed = scan.field_results.filter(page_index=index).exclude(bbox=None)
    for fr in boxed:
        bb = fr.bbox
        if not bb or len(bb) != 4:
            continue
        x0, y0, x1, y1 = bb
        if max(x0, y0, x1, y1) <= 1.0:
            x0, x1 = x0 * img.width, x1 * img.width
            y0, y1 = y0 * img.height, y1 * img.height
        draw.rectangle([x0, y0, x1, y1], outline=(214, 75, 106, 255), width=3)
        draw.rectangle([x0, y0, x1, y1], fill=(214, 75, 106, 30))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type="image/png")


@login_required
def api_keys(request: HttpRequest, account_slug: str) -> HttpResponse:
    deny = _require_member(request)
    if deny:
        return deny
    account = request.account
    new_key_plaintext = None
    if request.method == "POST":
        if "revoke" in request.POST:
            from django.utils import timezone

            ApiKey.objects.filter(
                account=account, pk=request.POST["revoke"], revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
            messages.success(request, "API key revoked.")
            return HttpResponseRedirect(
                reverse("web:api_keys", kwargs={"account_slug": account.slug})
            )

        form = ApiKeyForm(request.POST)
        if form.is_valid():
            _, new_key_plaintext = ApiKey.issue(
                account=account, user=request.user, name=form.cleaned_data["name"]
            )
    else:
        form = ApiKeyForm()
    keys = ApiKey.objects.filter(account=account).order_by("-created_at")
    return render(
        request,
        "web/api_keys.html",
        {
            "account": account,
            "form": form,
            "keys": keys,
            "new_key_plaintext": new_key_plaintext,
        },
    )
