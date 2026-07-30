from django.db import models
from django.db.models import Q
from django.utils import timezone


class PlanServicio(models.Model):
    nombre = models.CharField('Nombre del plan', max_length=100)
    precio = models.DecimalField('Precio mensual (COP)', max_digits=12, decimal_places=2)
    descripcion = models.TextField('Descripcion', blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plan de Servicio'
        verbose_name_plural = 'Planes de Servicio'

    def __str__(self):
        return f"{self.nombre} - ${float(self.precio):,.0f} COP/mes"


class DatosFacturacion(models.Model):
    TIPO_PERSONA_CHOICES = [
        ('JURIDICA', 'Persona Juridica'),
        ('NATURAL', 'Persona Natural'),
    ]
    TIPO_IDENTIFICACION_CHOICES = [
        ('NIT', 'NIT'),
        ('CC', 'Cedula de Ciudadania'),
        ('CE', 'Cedula de Extranjeria'),
    ]
    REGIMEN_CHOICES = [
        ('COMMON_REGIME', 'Regimen Comun'),
        ('SIMPLIFIED_REGIME', 'Regimen Simplificado'),
    ]

    tipo_persona = models.CharField('Tipo de persona', max_length=10, choices=TIPO_PERSONA_CHOICES)
    razon_social = models.CharField('Razon social / Nombre', max_length=200)
    tipo_identificacion = models.CharField('Tipo de identificacion', max_length=5, choices=TIPO_IDENTIFICACION_CHOICES)
    numero_identificacion = models.CharField('Numero de identificacion', max_length=20)
    dv = models.CharField('Digito de verificacion', max_length=1, blank=True)
    email = models.EmailField('Email de facturacion')
    telefono = models.CharField('Telefono', max_length=20)
    direccion = models.CharField('Direccion', max_length=200)
    ciudad = models.CharField('Ciudad', max_length=100)
    departamento = models.CharField('Departamento', max_length=100)
    regimen = models.CharField('Regimen', max_length=20, choices=REGIMEN_CHOICES, default='COMMON_REGIME')
    alegra_contacto_id = models.CharField('ID Contacto Alegra', max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Datos de Facturacion'
        verbose_name_plural = 'Datos de Facturacion'

    def __str__(self):
        return f"{self.razon_social} - {self.tipo_identificacion} {self.numero_identificacion}"


class Suscripcion(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Pago'),
        ('ACTIVA', 'Activa'),
        ('SUSPENDIDA', 'Suspendida'),
        ('CANCELADA', 'Cancelada'),
    ]

    plan = models.ForeignKey(PlanServicio, on_delete=models.PROTECT, related_name='suscripciones')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    fecha_proximo_pago = models.DateField('Proximo Pago', null=True, blank=True)
    wompi_payment_source_id = models.CharField(max_length=100, blank=True)
    datos_facturacion = models.ForeignKey(
        DatosFacturacion, on_delete=models.SET_NULL,
        blank=True, null=True, related_name='suscripciones',
        verbose_name='Datos de facturacion'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Suscripcion'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f"{self.plan.nombre} - {self.get_estado_display()}"

    @property
    def requiere_pago(self):
        """True si corresponde mostrar el flujo de pago: la suscripcion nunca
        estuvo activa, o su fecha_proximo_pago ya se cumplio/vencio. NO depende
        solo del flag estatico `estado` (que solo se setea a ACTIVA en el pago
        exitoso y nunca se revierte por si solo)."""
        if self.estado != 'ACTIVA':
            return True
        if not self.fecha_proximo_pago:
            return False
        return timezone.localdate() >= self.fecha_proximo_pago

    @property
    def alerta_pago_vencido(self):
        """True cuando el pago lleva 5+ dias vencido sin realizarse -- dispara
        el banner de aviso al admin (mas permisivo que requiere_pago, que se
        activa el mismo dia del vencimiento para habilitar el widget de pago)."""
        if not self.requiere_pago or not self.fecha_proximo_pago:
            return False
        return (timezone.localdate() - self.fecha_proximo_pago).days >= 5


class Pago(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('ANULADO', 'Anulado'),
        ('ERROR', 'Error'),
    ]

    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField('Monto (COP)', max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    wompi_transaction_id = models.CharField('ID Transaccion WOMPI', max_length=100, blank=True, db_index=True)
    wompi_reference = models.CharField('Referencia WOMPI', max_length=100, blank=True)
    detalle_respuesta = models.JSONField('Detalle respuesta WOMPI', default=dict, blank=True)
    alegra_invoice_id = models.CharField('ID Factura Alegra', max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['wompi_reference'],
                condition=~Q(wompi_reference=''),
                name='uniq_wompi_reference_no_vacio',
            ),
            models.UniqueConstraint(
                fields=['wompi_transaction_id'],
                condition=~Q(wompi_transaction_id=''),
                name='uniq_wompi_transaction_id_no_vacio',
            ),
        ]

    def __str__(self):
        return f"Pago ${float(self.monto):,.0f} - {self.get_estado_display()} - {self.created_at:%Y-%m-%d}"
