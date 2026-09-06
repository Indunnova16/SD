from django.db import models
from django.db.models import Q
from django.utils import timezone


def calcular_n_meses(monto, precio_mes):
    """Cuantos meses cubre un pago de `monto` para un plan de `precio_mes`.

    Redondea al entero mas cercano y nunca devuelve menos de 1 -- un pago
    parcial/menor a un mes igual cuenta como 1 mes cubierto (evita que un
    precio en 0, o un redondeo a la baja, deje avanzar la fecha 0 meses y la
    suscripcion quede trabada en requiere_pago=True pese a tener un pago
    aprobado). Misma formula que ya usaba alegra.py para la cantidad del
    item de la factura -- unificada aca para que el avance de
    fecha_proximo_pago y la facturacion nunca queden desincronizados."""
    precio_mes = float(precio_mes or 0)
    if precio_mes <= 0:
        return 1
    return max(1, round(float(monto) / precio_mes))


class PlanServicio(models.Model):
    nombre = models.CharField("Nombre del plan", max_length=100)
    precio = models.DecimalField("Precio mensual (COP)", max_digits=12, decimal_places=2)
    descripcion = models.TextField("Descripcion", blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plan de Servicio"
        verbose_name_plural = "Planes de Servicio"

    def __str__(self):
        return f"{self.nombre} - ${float(self.precio):,.0f} COP/mes"


class DatosFacturacion(models.Model):
    TIPO_PERSONA_CHOICES = [
        ("JURIDICA", "Persona Juridica"),
        ("NATURAL", "Persona Natural"),
    ]
    TIPO_IDENTIFICACION_CHOICES = [
        ("NIT", "NIT"),
        ("CC", "Cedula de Ciudadania"),
        ("CE", "Cedula de Extranjeria"),
    ]
    REGIMEN_CHOICES = [
        ("COMMON_REGIME", "Regimen Comun"),
        ("SIMPLIFIED_REGIME", "Regimen Simplificado"),
    ]

    tipo_persona = models.CharField("Tipo de persona", max_length=10, choices=TIPO_PERSONA_CHOICES)
    razon_social = models.CharField("Razon social / Nombre", max_length=200)
    tipo_identificacion = models.CharField(
        "Tipo de identificacion", max_length=5, choices=TIPO_IDENTIFICACION_CHOICES
    )
    numero_identificacion = models.CharField("Numero de identificacion", max_length=20)
    dv = models.CharField("Digito de verificacion", max_length=1, blank=True)
    email = models.EmailField("Email de facturacion")
    telefono = models.CharField("Telefono", max_length=20)
    direccion = models.CharField("Direccion", max_length=200)
    ciudad = models.CharField("Ciudad", max_length=100)
    departamento = models.CharField("Departamento", max_length=100)
    regimen = models.CharField(
        "Regimen", max_length=20, choices=REGIMEN_CHOICES, default="COMMON_REGIME"
    )
    alegra_contacto_id = models.CharField(  # noqa: DJ001
        "ID Contacto Alegra", max_length=50, blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Datos de Facturacion"
        verbose_name_plural = "Datos de Facturacion"

    def __str__(self):
        return f"{self.razon_social} - {self.tipo_identificacion} {self.numero_identificacion}"


class Suscripcion(models.Model):
    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente de Pago"),
        ("ACTIVA", "Activa"),
        ("SUSPENDIDA", "Suspendida"),
        ("CANCELADA", "Cancelada"),
    ]

    plan = models.ForeignKey(PlanServicio, on_delete=models.PROTECT, related_name="suscripciones")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="PENDIENTE")
    fecha_proximo_pago = models.DateField("Proximo Pago", null=True, blank=True)
    wompi_payment_source_id = models.CharField(max_length=100, blank=True)
    datos_facturacion = models.ForeignKey(
        DatosFacturacion,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="suscripciones",
        verbose_name="Datos de facturacion",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Suscripcion"
        verbose_name_plural = "Suscripciones"

    def __str__(self):
        return f"{self.plan.nombre} - {self.get_estado_display()}"

    @property
    def requiere_pago(self):
        """True si corresponde mostrar el flujo de pago: la suscripcion nunca
        estuvo activa, o su fecha_proximo_pago ya se cumplio/vencio. NO depende
        solo del flag estatico `estado` (que solo se setea a ACTIVA en el pago
        exitoso y nunca se revierte por si solo)."""
        if self.estado != "ACTIVA":
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

    @property
    def meses_atraso(self):
        """Meses completos de atraso respecto a fecha_proximo_pago. 0 si esta
        al dia, sin fecha aun, o el pago no ha vencido. Sirve para sugerir
        cuantos meses pagar de una vez en el checkout (issue: clientes que se
        atrasan mas de un mes solo pagaban 1 y quedaban atrasados igual,
        porque el sistema no distinguia "vencido hoy" de "vencido hace 2
        meses")."""
        hoy = timezone.localdate()
        if not self.fecha_proximo_pago or self.fecha_proximo_pago >= hoy:
            return 0
        return (
            (hoy.year - self.fecha_proximo_pago.year) * 12
            + (hoy.month - self.fecha_proximo_pago.month)
            + 1
        )


class Pago(models.Model):
    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("APROBADO", "Aprobado"),
        ("RECHAZADO", "Rechazado"),
        ("ANULADO", "Anulado"),
        ("ERROR", "Error"),
    ]

    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.CASCADE, related_name="pagos")
    monto = models.DecimalField("Monto (COP)", max_digits=12, decimal_places=2)
    n_meses = models.PositiveSmallIntegerField(
        "Meses cubiertos",
        default=1,
        help_text="Cuantos meses de suscripcion cubre este pago (monto / precio del plan al momento del pago).",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="PENDIENTE")
    wompi_transaction_id = models.CharField(
        "ID Transaccion WOMPI", max_length=100, blank=True, db_index=True
    )
    wompi_reference = models.CharField("Referencia WOMPI", max_length=100, blank=True)
    detalle_respuesta = models.JSONField("Detalle respuesta WOMPI", default=dict, blank=True)
    alegra_invoice_id = models.CharField("ID Factura Alegra", max_length=50, blank=True, null=True)  # noqa: DJ001
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wompi_reference"],
                condition=~Q(wompi_reference=""),
                name="uniq_wompi_reference_no_vacio",
            ),
            models.UniqueConstraint(
                fields=["wompi_transaction_id"],
                condition=~Q(wompi_transaction_id=""),
                name="uniq_wompi_transaction_id_no_vacio",
            ),
        ]

    def __str__(self):
        return f"Pago ${float(self.monto):,.0f} - {self.get_estado_display()} - {self.created_at:%Y-%m-%d}"
