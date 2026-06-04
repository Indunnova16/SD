"""
Lógica de asistencia diaria (entrada/salida) desacoplada del reconocimiento.

Portado de Logisticacargues, retargeteado a `accounts.User`. El "día laboral"
es configurable vía `settings.ATTENDANCE_WORKDAY_ROLLOVER_HOUR`:
    - None  -> el día laboral = día calendario (default SD).
    - 22    -> una marcación a las 22:00+ cuenta para el día siguiente
               (replica el turno noche de Logisticacargues).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .models import AttendanceRecord


class AttendanceService:
    @staticmethod
    def _work_day_date(at_time, at_date):
        """
        Devuelve la fecha del día laboral al que pertenece una marcación.

        Si `ATTENDANCE_WORKDAY_ROLLOVER_HOUR` está definido y la marcación
        ocurre a esa hora o después, pertenece al día siguiente.
        """
        rollover = getattr(settings, "ATTENDANCE_WORKDAY_ROLLOVER_HOUR", None)
        if rollover is not None and at_time >= time(int(rollover), 0):
            return at_date + timedelta(days=1)
        return at_date

    @staticmethod
    def check_in(user, registered_by):
        """Crea o actualiza el AttendanceRecord del día con check_in = ahora."""
        today = timezone.localdate()
        now = timezone.localtime().time()
        work_date = AttendanceService._work_day_date(now, today)
        record, created = AttendanceRecord.objects.get_or_create(
            user=user,
            date=work_date,
            defaults={
                "check_in": now,
                "registered_by": registered_by,
            },
        )
        if not created and record.check_in is None:
            record.check_in = now
            record.registered_by = registered_by
            record.save(update_fields=["check_in", "registered_by", "updated_at"])
        return record

    @staticmethod
    def check_out(user, registered_by):
        """Actualiza el AttendanceRecord del día con check_out = ahora y calcula horas."""
        today = timezone.localdate()
        now = timezone.localtime().time()
        work_date = AttendanceService._work_day_date(now, today)
        try:
            record = AttendanceRecord.objects.get(user=user, date=work_date)
        except AttendanceRecord.DoesNotExist:
            return AttendanceRecord.objects.create(
                user=user,
                date=work_date,
                check_out=now,
                registered_by=registered_by,
            )

        record.check_out = now
        record.registered_by = registered_by

        if record.check_in:
            dt_in = datetime.combine(work_date, record.check_in)
            dt_out = datetime.combine(work_date, now)
            # Turno nocturno: la salida es el día siguiente (ej. entra 22:00, sale 06:00).
            if dt_out < dt_in:
                dt_out += timedelta(days=1)
            diff = dt_out - dt_in
            hours = Decimal(str(round(diff.total_seconds() / 3600, 2)))
            record.hours_worked = max(hours, Decimal("0"))
        record.save(update_fields=["check_out", "hours_worked", "registered_by", "updated_at"])
        return record
