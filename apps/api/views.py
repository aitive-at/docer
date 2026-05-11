from __future__ import annotations

from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.scanners.models import Scanner
from apps.scans.models import Scan
from apps.scans.tasks import run_scan as run_scan_task

from .permissions import resolve_account_or_403
from .serializers import ScannerSerializer, ScanSerializer


@api_view(["GET", "POST"])
def scanner_list_create(request, account_slug):
    account = resolve_account_or_403(request, account_slug)
    if request.method == "GET":
        qs = Scanner.objects.filter(account=account)
        return Response(ScannerSerializer(qs, many=True).data)

    serializer = ScannerSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    scanner = Scanner(account=account, **serializer.validated_data)
    scanner.slug = scanner.make_unique_slug(scanner.name)
    scanner.save()
    return Response(ScannerSerializer(scanner).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
def scanner_detail(request, account_slug, scanner_slug):
    account = resolve_account_or_403(request, account_slug)
    scanner = get_object_or_404(Scanner, account=account, slug=scanner_slug)

    if request.method == "GET":
        return Response(ScannerSerializer(scanner).data)
    if request.method == "DELETE":
        scanner.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ScannerSerializer(scanner, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(ScannerSerializer(scanner).data)


@api_view(["POST"])
def scanner_scan(request, account_slug, scanner_slug):
    account = resolve_account_or_403(request, account_slug)
    scanner = get_object_or_404(Scanner, account=account, slug=scanner_slug)

    upload = request.FILES.get("file")
    if upload is None:
        return Response({"detail": "Multipart 'file' is required."}, status=400)

    from apps.files.services import ingest_upload

    stored = ingest_upload(account, upload, original_name=upload.name, mime=upload.content_type)
    scan = Scan.objects.create(account=account, scanner=scanner, file=stored)
    run_scan_task(scan.id)

    return Response(ScanSerializer(scan).data, status=status.HTTP_202_ACCEPTED)

scanner_scan.parser_classes = [MultiPartParser]


@api_view(["GET"])
def scan_detail(request, account_slug, scan_id):
    account = resolve_account_or_403(request, account_slug)
    scan = get_object_or_404(Scan, account=account, pk=scan_id)
    return Response(ScanSerializer(scan).data)


@api_view(["GET"])
def scan_page_image(request, account_slug, scan_id, index):
    account = resolve_account_or_403(request, account_slug)
    scan = get_object_or_404(Scan, account=account, pk=scan_id)
    page = scan.file.pages.filter(index=index).first()
    if page is None:
        raise Http404("Page not found")
    from apps.files.services import absolute_page_path

    path = absolute_page_path(page)
    if not path.exists():
        raise Http404("Page image not on disk")
    return FileResponse(open(path, "rb"), content_type="image/png")
