from django.contrib import admin
from .models import PlanServicio, Suscripcion, Pago, DatosFacturacion


@admin.register(PlanServicio)
class PlanServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'activo', 'created_at')
    list_filter = ('activo',)


@admin.register(DatosFacturacion)
class DatosFacturacionAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'tipo_identificacion', 'numero_identificacion', 'email', 'alegra_contacto_id', 'created_at')
    list_filter = ('tipo_persona', 'tipo_identificacion', 'regimen')
    search_fields = ('razon_social', 'numero_identificacion', 'email')
    readonly_fields = ('alegra_contacto_id',)


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = ('plan', 'estado', 'datos_facturacion', 'created_at', 'updated_at')
    list_filter = ('estado',)


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('suscripcion', 'monto', 'estado', 'wompi_transaction_id', 'alegra_invoice_id', 'created_at')
    list_filter = ('estado',)
    readonly_fields = ('detalle_respuesta', 'alegra_invoice_id')
