"""
Indexa en AWS Rekognition la foto de referencia (`User.photo`) de los usuarios
activos. Idempotente: por defecto solo procesa quienes aún no tienen aws_face_id.

Uso:
    python manage.py index_faces            # solo pendientes
    python manage.py index_faces --all      # reindexa también los ya indexados
    python manage.py index_faces --dry-run  # lista sin llamar a AWS
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Indexa las fotos de los usuarios en la collection de AWS Rekognition."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Reindexa también los ya indexados.")
        parser.add_argument("--dry-run", action="store_true", help="No llama a AWS, solo lista.")

    def handle(self, *args, **options):
        from apps.attendance.services_rekognition import (
            NoFaceDetectedError,
            RekognitionError,
            RekognitionService,
        )

        qs = User.objects.filter(is_active=True).exclude(photo="")
        if not options["all"]:
            qs = qs.filter(aws_face_id="")

        total = qs.count()
        self.stdout.write(f"Usuarios a procesar: {total}")
        if options["dry_run"]:
            for u in qs:
                self.stdout.write(f"  - {u} (id={u.id})")
            return

        if total:
            RekognitionService.ensure_collection()

        ok = failed = 0
        for u in qs:
            try:
                face_id = RekognitionService.index_user_face(u)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ {u} -> {face_id}"))
            except NoFaceDetectedError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f"  ⚠ {u}: sin rostro válido ({exc})"))
            except RekognitionError as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  ✗ {u}: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"Listo. Indexados: {ok} · Fallidos: {failed}"))
