"""Tests para los modelos de inspecciones."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.inspections.models import (
    CorrectiveAction,
    Equipment,
    EquipmentCategory,
    Finding,
    Inspection,
)

User = get_user_model()


class EquipmentCategoryTestCase(TestCase):
    """Tests para EquipmentCategory"""

    def setUp(self):
        self.category = EquipmentCategory.objects.create(
            name="Excavadoras", description="Máquinas excavadoras"
        )

    def test_category_creation(self):
        """Verifica que la categoría se crea correctamente"""
        self.assertEqual(self.category.name, "Excavadoras")
        self.assertEqual(str(self.category), "Excavadoras")

    def test_category_str_representation(self):
        """Verifica la representación en string"""
        self.assertEqual(str(self.category), "Excavadoras")


class EquipmentTestCase(TestCase):
    """Tests para Equipment"""

    def setUp(self):
        self.category = EquipmentCategory.objects.create(name="Excavadoras")
        self.equipment = Equipment.objects.create(
            folio="EXC-001",
            name="Excavadora CAT 320",
            category=self.category,
            location="Planta Principal",
            acquisition_date=date(2020, 1, 15),
            serial_number="CAT320-001",
        )

    def test_equipment_creation(self):
        """Verifica que el equipo se crea correctamente"""
        self.assertEqual(self.equipment.folio, "EXC-001")
        self.assertTrue(self.equipment.is_active)

    def test_equipment_str_representation(self):
        """Verifica la representación en string"""
        expected = "EXC-001 - Excavadora CAT 320"
        self.assertEqual(str(self.equipment), expected)


class InspectionTestCase(TestCase):
    """Tests para Inspection"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="inspector@test.com", password="password", first_name="Inspector",
            hire_date=date(2020, 1, 1),
        )
        self.category = EquipmentCategory.objects.create(name="Excavadoras")
        self.equipment = Equipment.objects.create(
            folio="EXC-001",
            name="Excavadora CAT 320",
            category=self.category,
            location="Planta Principal",
            acquisition_date=date(2020, 1, 15),
        )
        self.inspection = Inspection.objects.create(
            folio="INS-2024-001",
            equipment=self.equipment,
            inspector=self.user,
            scheduled_date=date.today(),
            location="Planta Principal",
            status="pending",
            criticality="low",
        )

    def test_inspection_creation(self):
        """Verifica que la inspección se crea correctamente"""
        self.assertEqual(self.inspection.folio, "INS-2024-001")
        self.assertEqual(self.inspection.status, "pending")

    def test_inspection_mark_as_completed(self):
        """Verifica que se puede marcar como completada"""
        self.inspection.mark_as_completed()
        self.assertEqual(self.inspection.status, "completed")
        self.assertIsNotNone(self.inspection.completed_at)


class FindingTestCase(TestCase):
    """Tests para Finding"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="inspector@test.com", password="password", first_name="Inspector",
            hire_date=date(2020, 1, 1),
        )
        self.category = EquipmentCategory.objects.create(name="Excavadoras")
        self.equipment = Equipment.objects.create(
            folio="EXC-001",
            name="Excavadora CAT 320",
            category=self.category,
            location="Planta Principal",
            acquisition_date=date(2020, 1, 15),
        )
        self.inspection = Inspection.objects.create(
            folio="INS-2024-001",
            equipment=self.equipment,
            inspector=self.user,
            scheduled_date=date.today(),
            location="Planta Principal",
        )
        self.finding = Finding.objects.create(
            inspection=self.inspection, description="Fisura en la estructura", severity="critical"
        )

    def test_finding_creation(self):
        """Verifica que el hallazgo se crea correctamente"""
        self.assertEqual(self.finding.severity, "critical")
        self.assertEqual(self.finding.inspection, self.inspection)


class CorrectiveActionTestCase(TestCase):
    """Tests para CorrectiveAction"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="inspector@test.com", password="password", first_name="Inspector",
            hire_date=date(2020, 1, 1), document_number="900000001",
        )
        self.responsible = User.objects.create_user(
            email="resp@test.com", password="password", first_name="Responsible",
            hire_date=date(2020, 1, 1), document_number="900000002",
        )
        self.category = EquipmentCategory.objects.create(name="Excavadoras")
        self.equipment = Equipment.objects.create(
            folio="EXC-001",
            name="Excavadora CAT 320",
            category=self.category,
            location="Planta Principal",
            acquisition_date=date(2020, 1, 15),
        )
        self.inspection = Inspection.objects.create(
            folio="INS-2024-001",
            equipment=self.equipment,
            inspector=self.user,
            scheduled_date=date.today(),
            location="Planta Principal",
        )
        self.finding = Finding.objects.create(
            inspection=self.inspection, description="Fisura en la estructura", severity="critical"
        )
        self.action = CorrectiveAction.objects.create(
            finding=self.finding,
            description="Reparar estructura",
            responsible=self.responsible,
            due_date=date.today(),
            status="pending",
        )

    def test_corrective_action_creation(self):
        """Verifica que la acción correctiva se crea correctamente"""
        self.assertEqual(self.action.status, "pending")
        self.assertEqual(self.action.responsible, self.responsible)

    def test_corrective_action_is_overdue(self):
        """Verifica que se detectan acciones vencidas"""
        from datetime import timedelta

        self.action.due_date = date.today() - timedelta(days=1)
        self.assertTrue(self.action.is_overdue)
