"""
Tests del kiosko de marcación facial (vista pública) y del servicio de asistencia.

El reconocimiento (AWS Rekognition) se mockea siempre — no se hacen llamadas reales.
"""

from datetime import date
from datetime import time as dtime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

import pytest

from apps.attendance.models import AttendanceRecord, FaceCheckEvent
from apps.attendance.services import AttendanceService

User = get_user_model()

# PNG 1x1 mínimo válido
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_user(doc="99999999"):
    return User.objects.create_user(
        email=f"u{doc}@example.com",
        password="x",
        first_name="QA",
        last_name="Tester",
        document_type="CC",
        document_number=doc,
        job_position="Operario",
        hire_date=date(2024, 1, 1),
    )


class _FakeRekogResult:
    """Stub del resultado de RekognitionService.search_face."""

    def __init__(self, user, similarity=99.5, matched=True, aws_face_id="fake-face-id"):
        self.matched = matched
        self.user = user
        self.similarity = similarity
        self.aws_face_id = aws_face_id


def _post_selfie(client, kind):
    url = reverse("attendance:mobile_face_checkin")
    selfie = SimpleUploadedFile("selfie.png", PNG_BYTES, content_type="image/png")
    return client.post(url, {"selfie": selfie, "kind": kind})


@pytest.mark.django_db
class TestMobileFaceCheckIn:
    def test_get_renders_kiosk(self):
        resp = Client().get(reverse("attendance:mobile_face_checkin"))
        assert resp.status_code == 200
        assert b"Marcaci" in resp.content

    def test_invalid_kind_returns_400(self):
        selfie = SimpleUploadedFile("s.png", PNG_BYTES, content_type="image/png")
        resp = Client().post(
            reverse("attendance:mobile_face_checkin"),
            {"selfie": selfie, "kind": "foo"},
        )
        assert resp.status_code == 400

    def test_missing_selfie_returns_400(self):
        resp = Client().post(reverse("attendance:mobile_face_checkin"), {"kind": "check_in"})
        assert resp.status_code == 400

    def test_check_in_match_creates_record_and_event(self):
        user = _make_user()
        with patch(
            "apps.attendance.services_rekognition.RekognitionService.search_face",
            return_value=_FakeRekogResult(user),
        ):
            resp = _post_selfie(Client(), "check_in")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == FaceCheckEvent.STATUS_MATCHED
        assert len(data["time"]) == 5  # HH:MM
        rec = AttendanceRecord.objects.get(user=user)
        assert rec.check_in is not None
        ev = FaceCheckEvent.objects.get()
        assert ev.user == user
        assert ev.status == FaceCheckEvent.STATUS_MATCHED

    def test_time_str_matches_record_check_in(self):
        user = _make_user()
        with patch(
            "apps.attendance.services_rekognition.RekognitionService.search_face",
            return_value=_FakeRekogResult(user),
        ):
            data = _post_selfie(Client(), "check_in").json()
        rec = AttendanceRecord.objects.get(user=user)
        expected = rec.check_in.strftime("%H:%M")
        assert data["time"] == expected

    def test_no_match_does_not_create_record(self):
        with patch(
            "apps.attendance.services_rekognition.RekognitionService.search_face",
            return_value=_FakeRekogResult(None, similarity=0.0, matched=False, aws_face_id=""),
        ):
            data = _post_selfie(Client(), "check_in").json()
        assert data["ok"] is False
        assert data["status"] == FaceCheckEvent.STATUS_NO_MATCH
        assert AttendanceRecord.objects.count() == 0
        assert FaceCheckEvent.objects.filter(status=FaceCheckEvent.STATUS_NO_MATCH).count() == 1


@pytest.mark.django_db
class TestAttendanceService:
    def test_check_out_computes_hours(self):
        user = _make_user("11111111")
        rec = AttendanceService.check_in(user, registered_by=None)
        rec.check_in = dtime(8, 0)
        rec.save(update_fields=["check_in"])
        out = AttendanceService.check_out(user, registered_by=None)
        # check_out usa la hora actual; solo verificamos que calcula horas no-negativas
        assert out.hours_worked is not None
        assert out.hours_worked >= 0

    def test_rollover_none_uses_calendar_day(self, settings):
        settings.ATTENDANCE_WORKDAY_ROLLOVER_HOUR = None
        from django.utils import timezone

        d = AttendanceService._work_day_date(dtime(23, 30), timezone.localdate())
        assert d == timezone.localdate()

    def test_rollover_22_rolls_to_next_day(self, settings):
        settings.ATTENDANCE_WORKDAY_ROLLOVER_HOUR = 22
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        assert AttendanceService._work_day_date(dtime(22, 5), today) == today + timedelta(days=1)
        assert AttendanceService._work_day_date(dtime(21, 0), today) == today


@pytest.mark.django_db
class TestRekognitionService:
    """search_face con el cliente boto3 mockeado (sin llamadas reales)."""

    def test_search_face_match_returns_user(self, settings):
        settings.AWS_ACCESS_KEY_ID = "x"
        settings.AWS_SECRET_ACCESS_KEY = "y"
        user = _make_user("22222222")
        fake_resp = {
            "FaceMatches": [
                {
                    "Similarity": 98.7,
                    "Face": {"FaceId": "fid-1", "ExternalImageId": str(user.id)},
                }
            ]
        }
        from apps.attendance.services_rekognition import RekognitionService

        with patch.object(RekognitionService, "_client") as mock_client:
            mock_client.return_value.search_faces_by_image.return_value = fake_resp
            result = RekognitionService.search_face(b"bytes")
        assert result.matched is True
        assert result.user == user
        assert result.similarity == 98.7

    def test_search_face_no_match(self, settings):
        settings.AWS_ACCESS_KEY_ID = "x"
        settings.AWS_SECRET_ACCESS_KEY = "y"
        from apps.attendance.services_rekognition import RekognitionService

        with patch.object(RekognitionService, "_client") as mock_client:
            mock_client.return_value.search_faces_by_image.return_value = {"FaceMatches": []}
            result = RekognitionService.search_face(b"bytes")
        assert result.matched is False
        assert result.user is None
