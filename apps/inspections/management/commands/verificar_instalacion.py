"""Comando para verificar que la instalación del módulo de inspecciones sea correcta.

Uso:
    python manage.py verificar_instalacion
"""

from django.apps import apps
from django.core.management.base import BaseCommand

from apps.inspections.models import Equipment, EquipmentCategory, Inspection


class Command(BaseCommand):
    help = 'Verifica la instalación correcta del módulo de inspecciones'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('VERIFICACIÓN DE INSTALACIÓN - MÓDULO DE INSPECCIONES'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))

        checks = [
            ('✓ App registrado', self._verificar_app),
            ('✓ Modelos creados', self._verificar_modelos),
            ('✓ Categorías de equipos', self._verificar_categorias),
            ('✓ Equipos cargados', self._verificar_equipos),
            ('✓ Base de datos', self._verificar_base_datos),
        ]

        resultados = []
        for titulo, funcion in checks:
            try:
                resultado = funcion()
                resultados.append((titulo, resultado, True))
            except Exception as e:
                resultados.append((titulo, str(e), False))

        self._mostrar_resultados(resultados)
        self._mostrar_resumen(resultados)

    def _verificar_app(self):
        """Verifica que el app esté registrado"""
        try:
            apps.get_app_config('inspections')
            return 'App "inspections" está registrado en INSTALLED_APPS'
        except LookupError:
            raise Exception('App no registrado. Agrega "apps.inspections" a INSTALLED_APPS')

    def _verificar_modelos(self):
        """Verifica que los modelos existan"""
        import importlib.util

        try:
            models = [
                'apps.inspections.models.CorrectiveAction',
                'apps.inspections.models.Equipment',
                'apps.inspections.models.EquipmentCategory',
                'apps.inspections.models.Finding',
                'apps.inspections.models.Inspection',
                'apps.inspections.models.InspectionChecklist',
            ]
            for model in models:
                spec = importlib.util.find_spec(model)
                if spec is None:
                    raise ImportError(f'Model {model} not found')

            return '6 modelos disponibles (Category, Equipment, Inspection, Checklist, Finding, Action)'
        except ImportError as e:
            raise Exception(f'Error importando modelos: {str(e)}')

    def _verificar_categorias(self):
        """Verifica que las categorías existan"""
        count = EquipmentCategory.objects.count()
        if count == 0:
            return 'Sin categorías cargadas (ejecuta: cargar_equipos_energeticos)'
        return f'{count} categorías de equipos disponibles'

    def _verificar_equipos(self):
        """Verifica que los equipos estén cargados"""
        count = Equipment.objects.count()
        if count == 0:
            return 'Sin equipos cargados (ejecuta: cargar_equipos_energeticos)'

        activos = Equipment.objects.filter(is_active=True).count()
        return f'{count} equipos energéticos cargados ({activos} activos)'

    def _verificar_base_datos(self):
        """Verifica la integridad de la base de datos"""
        try:
            total_inspecc = Inspection.objects.count()
            return f'Base de datos operativa ({total_inspecc} inspecciones registradas)'
        except Exception as e:
            raise Exception(f'Error en base de datos: {str(e)}')

    def _mostrar_resultados(self, resultados):
        """Muestra los resultados individuales"""
        for titulo, detalles, exito in resultados:
            if exito:
                self.stdout.write(self.style.SUCCESS(f'{titulo}'))
                self.stdout.write(f'  {detalles}\n')
            else:
                self.stdout.write(self.style.ERROR(f'✗ {titulo}'))
                self.stdout.write(f'  {detalles}\n')

    def _mostrar_resumen(self, resultados):
        """Muestra un resumen final"""
        exitosos = sum(1 for _, _, exito in resultados if exito)
        total = len(resultados)

        self.stdout.write(self.style.SUCCESS('='*60))

        if exitosos == total:
            self.stdout.write(self.style.SUCCESS(f'\n✓ INSTALACIÓN CORRECTA ({exitosos}/{total})\n'))
            self.stdout.write('🎉 El módulo está listo para usar:\n')
            self.stdout.write('   1. Accede a: http://localhost:8000/inspecciones/\n')
            self.stdout.write('   2. Admin: http://localhost:8000/admin/\n')
            self.stdout.write('   3. ¡Comienza a crear inspecciones!\n')
        else:
            self.stdout.write(self.style.ERROR(f'\n✗ ERRORES DETECTADOS ({exitosos}/{total})\n'))
            self.stdout.write('Por favor ejecuta los pasos de instalación:\n')
            self.stdout.write('   1. python manage.py makemigrations inspections\n')
            self.stdout.write('   2. python manage.py migrate inspections\n')
            self.stdout.write('   3. python manage.py cargar_equipos_energeticos\n')

        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
