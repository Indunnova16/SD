"""Vistas para el sistema de inspecciones.

Incluye listados, detalles, formularios de inspección y dashboards.
"""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from .forms import CorrectiveActionForm, FindingForm, InspectionForm
from .models import (
    CorrectiveAction,
    Equipment,
    EquipmentCategory,
    Finding,
    Inspection,
)


@login_required
def dashboard(request):
    """Dashboard principal de inspecciones"""
    # Estadísticas generales
    total_inspections = Inspection.objects.count()
    completed_inspections = Inspection.objects.filter(status='completed').count()
    in_progress = Inspection.objects.filter(status='in_progress').count()
    critical_inspections = Inspection.objects.filter(criticality='critical').count()

    # Inspecciones recientes
    recent_inspections = Inspection.objects.select_related('equipment', 'inspector').order_by('-inspection_date')[:10]

    # Agrupar por semana
    from django.db.models.functions import TruncWeek

    inspections_by_week = (
        Inspection.objects
        .annotate(week=TruncWeek('inspection_date'))
        .values('week')
        .annotate(count=Count('id'))
        .order_by('-week')
    )

    context = {
        'total_inspections': total_inspections,
        'completed_inspections': completed_inspections,
        'in_progress': in_progress,
        'critical_inspections': critical_inspections,
        'recent_inspections': recent_inspections,
        'inspections_by_week': inspections_by_week,
    }

    return render(request, 'inspections/dashboard.html', context)


class InspectionListView(LoginRequiredMixin, ListView):
    """Listado de inspecciones con filtros"""
    model = Inspection
    template_name = 'inspections/inspection_list.html'
    paginate_by = 20
    context_object_name = 'inspections'

    def get_queryset(self):
        queryset = Inspection.objects.select_related('equipment', 'inspector').order_by('-inspection_date')

        # Filtros
        search = self.request.GET.get('search', '')
        status = self.request.GET.get('status', '')
        equipment_category = self.request.GET.get('category', '')

        if search:
            queryset = queryset.filter(
                Q(folio__icontains=search) |
                Q(equipment__name__icontains=search) |
                Q(inspector__first_name__icontains=search)
            )

        if status:
            queryset = queryset.filter(status=status)

        if equipment_category:
            queryset = queryset.filter(equipment__category_id=equipment_category)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = EquipmentCategory.objects.all()
        context['status_choices'] = Inspection.STATUS_CHOICES
        return context


class InspectionDetailView(LoginRequiredMixin, DetailView):
    """Detalle de una inspección"""
    model = Inspection
    template_name = 'inspections/inspection_detail.html'
    context_object_name = 'inspection'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inspection = self.object
        context['findings'] = inspection.findings.all()
        context['checklist'] = inspection.checklist
        return context


class InspectionCreateView(LoginRequiredMixin, CreateView):
    """Crear nueva inspección"""
    model = Inspection
    form_class = InspectionForm
    template_name = 'inspections/inspection_form.html'
    success_url = reverse_lazy('inspections:inspection-list')

    def form_valid(self, form):
        form.instance.inspector = self.request.user
        form.instance.folio = self._generate_folio()
        return super().form_valid(form)

    @staticmethod
    def _generate_folio():
        """Genera un folio único para la inspección"""
        from datetime import datetime
        year = datetime.now().year
        count = Inspection.objects.filter(folio__startswith=f"INS-{year}").count() + 1
        return f"INS-{year}-{count:03d}"


class EquipmentListView(LoginRequiredMixin, ListView):
    """Listado de equipos"""
    model = Equipment
    template_name = 'inspections/equipment_list.html'
    paginate_by = 20

    def get_queryset(self):
        queryset = Equipment.objects.filter(is_active=True).select_related('category')

        search = self.request.GET.get('search', '')
        category = self.request.GET.get('category', '')

        if search:
            queryset = queryset.filter(
                Q(folio__icontains=search) |
                Q(name__icontains=search)
            )

        if category:
            queryset = queryset.filter(category_id=category)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = EquipmentCategory.objects.all()
        return context


class FindingCreateView(LoginRequiredMixin, CreateView):
    """Agregar hallazgo a una inspección"""
    model = Finding
    form_class = FindingForm
    template_name = 'inspections/finding_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inspection_id = self.kwargs.get('inspection_id')
        context['inspection'] = get_object_or_404(Inspection, pk=inspection_id)
        return context

    def form_valid(self, form):
        inspection = get_object_or_404(Inspection, pk=self.kwargs.get('inspection_id'))
        form.instance.inspection = inspection
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('inspections:inspection-detail', kwargs={'pk': self.object.inspection.pk})


class CorrectiveActionCreateView(LoginRequiredMixin, CreateView):
    """Crear acción correctiva para un hallazgo"""
    model = CorrectiveAction
    form_class = CorrectiveActionForm
    template_name = 'inspections/corrective_action_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        finding_id = self.kwargs.get('finding_id')
        context['finding'] = get_object_or_404(Finding, pk=finding_id)
        return context

    def form_valid(self, form):
        finding = get_object_or_404(Finding, pk=self.kwargs.get('finding_id'))
        form.instance.finding = finding
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('inspections:inspection-detail', kwargs={'pk': self.object.finding.inspection.pk})
