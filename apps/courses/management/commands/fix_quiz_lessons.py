"""Management command to fix quiz lessons without assessments."""

from django.core.management.base import BaseCommand

from apps.assessments.models import Assessment
from apps.courses.models import Lesson


class Command(BaseCommand):
    help = "Create missing assessments for quiz-type lessons"

    def handle(self, *args, **options):
        quiz_lessons = Lesson.objects.filter(lesson_type="quiz")
        fixed = 0

        for lesson in quiz_lessons:
            if not lesson.assessments.exists():
                try:
                    course = lesson.module.course
                    Assessment.objects.create(
                        title=lesson.title,
                        assessment_type="quiz",
                        passing_score=80,
                        max_attempts=3,
                        course=course,
                        lesson=lesson,
                        created_by=course.created_by,
                        status="published",
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Fixed: {lesson.title} (ID: {lesson.id})")
                    )
                    fixed += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Error fixing {lesson.title}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\n✓ Fixed {fixed} quiz lessons"))
