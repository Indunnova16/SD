"""Tests for accounts models — `User.signature` field (SD#51, sub-item A1).

The `signature` field is aditive (blank=True, null=True) and mirrors the
existing `photo` field. These tests cover:
  - The field accepts blank/null (no signature set) without validation errors.
  - An ImageField assignment persists and round-trips via the DB.
  - A user created BEFORE this migration existed (simulated here by never
    setting `signature`, i.e. a "legacy" row) still loads fine with
    `signature` falsy — the migration must not require backfill.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

User = get_user_model()

# Minimal valid 2x2 PNG (passes PIL's full verify(), not just a truncated
# placeholder) — see apps/accounts/tests/test_views.py for the rationale.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a73"
    "0000001649444154789c63fccfc0c0c0c0c0c4c0c0c0c0c000000d1d01036ac29be"
    "90000000049454e44ae426082"
)


def _png_file(name="signature.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


class UserSignatureFieldTests(TestCase):
    """Field-level behavior of `User.signature` (SD#51 A1)."""

    def _make_user(self, **overrides):
        defaults = {
            "email": "signature_field@example.com",
            "password": "testpassword123",
            "first_name": "Firma",
            "last_name": "Test",
            "document_type": "CC",
            "document_number": "900000001",
            "job_position": "Coordinador",
            "job_profile": None,
            "hire_date": date(2024, 1, 1),
        }
        defaults.update(overrides)
        return User.objects.create_user(**defaults)

    def test_signature_blank_by_default_legacy_row(self):
        """A user with no signature assigned (legacy row pre-migration)
        loads without error and `signature` is falsy — no backfill required.
        """
        user = self._make_user()
        user.refresh_from_db()
        self.assertFalse(user.signature)

    def test_signature_field_accepts_null_and_blank(self):
        """Field is optional at the model level (blank=True, null=True)."""
        field = User._meta.get_field("signature")
        self.assertTrue(field.blank)
        self.assertTrue(field.null)

    def test_signature_upload_persists_and_roundtrips(self):
        """Assigning an image to `signature` persists and survives a reload."""
        user = self._make_user(document_number="900000002", email="signature_field2@example.com")
        user.signature.save("signature.png", _png_file(), save=True)

        user.refresh_from_db()
        self.assertTrue(user.signature)
        self.assertIn("users/signatures/", user.signature.name)

    def test_signature_upload_path_matches_spec(self):
        """upload_to must be 'users/signatures/' per the plan (not photos/)."""
        user = self._make_user(document_number="900000003", email="signature_field3@example.com")
        user.signature.save("firma.png", _png_file(), save=True)
        self.assertTrue(user.signature.name.startswith("users/signatures/"))
