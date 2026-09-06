from django.conf import settings
from django.core.management.base import BaseCommand

from pagos.models import PlanServicio, Suscripcion


class Command(BaseCommand):
    help = "Crea el plan de servicio y la suscripcion inicial (lee de settings PAGOS_PLAN_*)"

    def handle(self, *args, **options):
        plan_name = getattr(settings, "PAGOS_PLAN_NAME", "Plan SaaS")
        plan_price = getattr(settings, "PAGOS_PLAN_PRICE", 150000)
        plan_desc = getattr(
            settings, "PAGOS_PLAN_DESCRIPTION", "Plataforma SaaS + Hosting + Soporte"
        )

        plan, created = PlanServicio.objects.get_or_create(
            nombre=plan_name,
            defaults={
                "precio": plan_price,
                "descripcion": plan_desc,
                "activo": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Plan creado: {plan}"))
        else:
            self.stdout.write(self.style.WARNING(f"Plan ya existe: {plan}"))

        suscripcion, created = Suscripcion.objects.get_or_create(
            plan=plan, defaults={"estado": "PENDIENTE"}
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Suscripcion creada: {suscripcion}"))
        else:
            self.stdout.write(self.style.WARNING(f"Suscripcion ya existe: {suscripcion}"))
