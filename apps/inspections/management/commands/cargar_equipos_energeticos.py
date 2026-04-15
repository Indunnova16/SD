"""Comando para cargar equipos del sector energético (transmisión eléctrica).

Uso:
    python manage.py cargar_equipos_energeticos
"""

from datetime import date

from django.core.management.base import BaseCommand

from apps.inspections.models import Equipment, EquipmentCategory


class Command(BaseCommand):
    help = 'Carga equipos del sector energético de transmisión eléctrica'

    def handle(self, *args, **options):
        self.stdout.write('Cargando equipos del sector energético...\n')

        # Crear categorías
        categorias = self._crear_categorias()

        # Cargar equipos por categoría
        self._cargar_estructuras(categorias)
        self._cargar_aisladores(categorias)
        self._cargar_conductores(categorias)
        self._cargar_herrajes(categorias)
        self._cargar_transformadores(categorias)

        self.stdout.write(self.style.SUCCESS('✓ Datos cargados exitosamente'))

    def _crear_categorias(self):
        """Crea las categorías de equipos del sector energético"""
        categorias = {}

        estructuras_data = {
            'name': 'Estructuras y Postes',
            'description': 'Torres, postes y estructuras de soporte para líneas de transmisión'
        }
        categorias['estructuras'], created = EquipmentCategory.objects.get_or_create(
            name=estructuras_data['name'],
            defaults=estructuras_data
        )
        if created:
            self.stdout.write(f"  ✓ Categoría creada: {estructuras_data['name']}")

        aisladores_data = {
            'name': 'Aisladores y Cadenas',
            'description': 'Aisladores de cerámica, vidrio y cadenas de aislamiento'
        }
        categorias['aisladores'], created = EquipmentCategory.objects.get_or_create(
            name=aisladores_data['name'],
            defaults=aisladores_data
        )
        if created:
            self.stdout.write(f"  ✓ Categoría creada: {aisladores_data['name']}")

        conductores_data = {
            'name': 'Conductores y Cables',
            'description': 'Conductores de aluminio, cobre y cables de guarda'
        }
        categorias['conductores'], created = EquipmentCategory.objects.get_or_create(
            name=conductores_data['name'],
            defaults=conductores_data
        )
        if created:
            self.stdout.write(f"  ✓ Categoría creada: {conductores_data['name']}")

        herrajes_data = {
            'name': 'Herrajes y Fijaciones',
            'description': 'Grapas, crucetas, ménsulas y elementos de fijación'
        }
        categorias['herrajes'], created = EquipmentCategory.objects.get_or_create(
            name=herrajes_data['name'],
            defaults=herrajes_data
        )
        if created:
            self.stdout.write(f"  ✓ Categoría creada: {herrajes_data['name']}")

        transformadores_data = {
            'name': 'Transformadores',
            'description': 'Transformadores de potencia y distribución'
        }
        categorias['transformadores'], created = EquipmentCategory.objects.get_or_create(
            name=transformadores_data['name'],
            defaults=transformadores_data
        )
        if created:
            self.stdout.write(f"  ✓ Categoría creada: {transformadores_data['name']}")

        return categorias

    def _cargar_estructuras(self, categorias):
        """Carga estructuras y postes"""
        equipos = [
            {
                'folio': 'EST-001',
                'name': 'Torre Celosía 230kV - Tipo A',
                'location': 'Línea Bogotá-Medellín, km 45',
                'serial_number': 'TCL-230A-2019-001',
                'acquisition_date': date(2019, 3, 15),
            },
            {
                'folio': 'EST-002',
                'name': 'Poste Concreto 138kV',
                'location': 'Línea Cali-Buenaventura, km 12',
                'serial_number': 'PC-138-2020-001',
                'acquisition_date': date(2020, 6, 20),
            },
            {
                'folio': 'EST-003',
                'name': 'Torre Tubular 500kV',
                'location': 'Línea Guatapé-Medellín, km 8',
                'serial_number': 'TT-500-2018-001',
                'acquisition_date': date(2018, 1, 10),
            },
            {
                'folio': 'EST-004',
                'name': 'Poste Madera Tratada 34.5kV',
                'location': 'Distribución zona urbana, Cra 7',
                'serial_number': 'PM-34.5-2021-001',
                'acquisition_date': date(2021, 2, 14),
            },
        ]

        self._crear_equipos(equipos, categorias['estructuras'])

    def _cargar_aisladores(self, categorias):
        """Carga aisladores y cadenas"""
        equipos = [
            {
                'folio': 'AIS-001',
                'name': 'Cadena de Aisladores 230kV - Tipo Línea',
                'location': 'Almacén Central - Bogotá',
                'serial_number': 'CAI-230-2020-001',
                'acquisition_date': date(2020, 5, 22),
            },
            {
                'folio': 'AIS-002',
                'name': 'Aislador Cerámica Porcelana 138kV',
                'location': 'Línea Cali-Popayán, km 30',
                'serial_number': 'ACP-138-2019-001',
                'acquisition_date': date(2019, 9, 8),
            },
            {
                'folio': 'AIS-003',
                'name': 'Cadena de Aisladores Vidrio 500kV',
                'location': 'Almacén Centro de Distribución',
                'serial_number': 'CAV-500-2020-001',
                'acquisition_date': date(2020, 11, 3),
            },
            {
                'folio': 'AIS-004',
                'name': 'Aislador Polimérico 69kV',
                'location': 'Línea Rural Zona 3, km 15',
                'serial_number': 'APO-69-2021-001',
                'acquisition_date': date(2021, 4, 18),
            },
        ]

        self._crear_equipos(equipos, categorias['aisladores'])

    def _cargar_conductores(self, categorias):
        """Carga conductores y cables"""
        equipos = [
            {
                'folio': 'CON-001',
                'name': 'Conductor ACSR 4/0 AWG - Tramo 230kV',
                'location': 'Línea Bogotá-Medellín, km 45-65',
                'serial_number': 'ACSR-4-0-2019-001',
                'acquisition_date': date(2019, 7, 11),
            },
            {
                'folio': 'CON-002',
                'name': 'Cable de Guarda ACSR 3/8" 138kV',
                'location': 'Línea Cali-Buenaventura',
                'serial_number': 'CG-ACSR-2020-001',
                'acquisition_date': date(2020, 8, 25),
            },
            {
                'folio': 'CON-003',
                'name': 'Conductor Aluminio 500kcmil 500kV',
                'location': 'Almacén Materiales - Medellín',
                'serial_number': 'CAL-500k-2020-001',
                'acquisition_date': date(2020, 2, 29),
            },
            {
                'folio': 'CON-004',
                'name': 'Conductor Cobre Desnudo 2 AWG',
                'location': 'Línea Distribución Zona 1',
                'serial_number': 'CCD-2-2021-001',
                'acquisition_date': date(2021, 5, 7),
            },
        ]

        self._crear_equipos(equipos, categorias['conductores'])

    def _cargar_herrajes(self, categorias):
        """Carga herrajes y fijaciones"""
        equipos = [
            {
                'folio': 'HER-001',
                'name': 'Cruceta de Hierro 230kV',
                'location': 'Torre Celosía - Línea principal',
                'serial_number': 'CRZ-230-2019-001',
                'acquisition_date': date(2019, 4, 16),
            },
            {
                'folio': 'HER-002',
                'name': 'Grapa de Suspensión Aluminio 138kV',
                'location': 'Almacén Bogotá',
                'serial_number': 'GSA-138-2020-001',
                'acquisition_date': date(2020, 10, 9),
            },
            {
                'folio': 'HER-003',
                'name': 'Ménsula de Soporte Acero Galvanizado',
                'location': 'Línea Distribución, varios puntos',
                'serial_number': 'MSA-GAL-2021-001',
                'acquisition_date': date(2021, 1, 22),
            },
            {
                'folio': 'HER-004',
                'name': 'Tornillería Acero Inox 500kV',
                'location': 'Centro de Mantenimiento',
                'serial_number': 'TAI-500-2020-001',
                'acquisition_date': date(2020, 12, 5),
            },
        ]

        self._crear_equipos(equipos, categorias['herrajes'])

    def _cargar_transformadores(self, categorias):
        """Carga transformadores"""
        equipos = [
            {
                'folio': 'TRF-001',
                'name': 'Transformador de Potencia 230/138kV 200MVA',
                'location': 'Subestación Central - Bogotá',
                'serial_number': 'TRF-230-138-2018-001',
                'acquisition_date': date(2018, 5, 20),
            },
            {
                'folio': 'TRF-002',
                'name': 'Transformador de Distribución 13.8/0.46kV 10MVA',
                'location': 'Subestación Zona Industrial',
                'serial_number': 'TRF-13.8-0.46-2019-001',
                'acquisition_date': date(2019, 8, 14),
            },
            {
                'folio': 'TRF-003',
                'name': 'Transformador de Potencia 500/230kV 300MVA',
                'location': 'Subestación Guatapé',
                'serial_number': 'TRF-500-230-2017-001',
                'acquisition_date': date(2017, 11, 3),
            },
            {
                'folio': 'TRF-004',
                'name': 'Transformador Trifásico 69/13.8kV 30MVA',
                'location': 'Subestación Rural km 45',
                'serial_number': 'TRF-69-13.8-2020-001',
                'acquisition_date': date(2020, 3, 17),
            },
        ]

        self._crear_equipos(equipos, categorias['transformadores'])

    def _crear_equipos(self, equipos_data, categoria):
        """Crea equipos en la base de datos"""
        for equipo_data in equipos_data:
            equipo, created = Equipment.objects.get_or_create(
                folio=equipo_data['folio'],
                defaults={
                    'name': equipo_data['name'],
                    'category': categoria,
                    'location': equipo_data['location'],
                    'serial_number': equipo_data['serial_number'],
                    'acquisition_date': equipo_data['acquisition_date'],
                    'is_active': True,
                }
            )
            if created:
                self.stdout.write(f"  ✓ Equipo creado: {equipo_data['folio']} - {equipo_data['name']}")
            else:
                self.stdout.write(f"  ℹ Equipo existente: {equipo_data['folio']}")
