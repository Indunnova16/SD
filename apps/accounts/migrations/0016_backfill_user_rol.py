"""Data migration: backfill `User.rol` desde `job_profile.code` (SD#58 A1).

Mapeo (decisión de Miguel, HITL 2026-07-06):
    LINIERO, TECNICO, OPERADOR                            -> EJECUTOR
    JEFE_CUADRILLA, INGENIERO_RESIDENTE, COORDINADOR_HSEQ  -> COORDINADOR
    ADMINISTRADOR                                          -> ADMINISTRADOR

Además, cualquier usuario con `is_staff=True` o `is_superuser=True` se
backfillea a ADMINISTRADOR con confianza, independientemente del código de
`job_profile` — cubre superusers creados sin `job_profile` explícito (ej.
`createsuperuser`, que no exige `job_profile`).

Códigos SIN mapeo automático confiable (evidencia F2, ver
`SD/SPRINTS/PLAN_2026-07-06_rbac_roles_acceso.md`): `COORDINADOR_VIZ`,
`CAPATAZ`, "TODOS LOS CARGOS", `CONTRATISTA`, `CONDUCTOR`, y `job_profile`
NULL o cualquier código desconocido — 4 de estos 5 códigos no estaban
contemplados en el mapeo original de Miguel y `CAPATAZ` en particular es
ambiguo (rol de mando de cuadrilla, similar a JEFE_CUADRILLA).

Decisión de esta migración (instrucción directa de Miguel para la ejecución
de A1, resuelve la ambigüedad que el PLAN dejaba abierta en la sección
"Riesgos y mitigaciones" como "a decidir en A1"): en vez de adivinar un rol
elevado (o dejar el campo en NULL, que es lo que F2 había propuesto
tentativamente) se asigna el default MÁS RESTRICTIVO — EJECUTOR — a estos
usuarios, documentando la decisión acá y emitiendo un reporte de conteo al
final del `RunPython` para que el Administrador los revise manualmente vía
la UI de Crear/Editar Usuario (sub-item A2). El campo `rol` sigue siendo
nullable a nivel de esquema (ver migración 0015) para soportar flujos
futuros (ej. import masivo A3 con fila sin columna `rol_acceso` y sin
sugerencia), pero esta migración de datos NO deja ningún usuario EXISTENTE
en NULL — todos quedan con un valor concreto.
"""

from django.db import migrations

EJECUTOR_CODES = {"LINIERO", "TECNICO", "OPERADOR"}
COORDINADOR_CODES = {"JEFE_CUADRILLA", "INGENIERO_RESIDENTE", "COORDINADOR_HSEQ"}
ADMINISTRADOR_CODES = {"ADMINISTRADOR"}

# Rol seguro (más restrictivo) para códigos sin mapeo automático confiable.
DEFAULT_SAFE_ROL = "EJECUTOR"


def resolve_rol(job_profile_code, is_staff=False, is_superuser=False):
    """Determina `(rol, is_confident)` para el backfill de un usuario existente.

    Orden de precedencia:
    1. `is_staff`/`is_superuser` (señal de alta confianza, independiente del
       código de `job_profile`) -> ADMINISTRADOR, confiado.
    2. código de `job_profile` mapeado explícitamente -> EJECUTOR/COORDINADOR/
       ADMINISTRADOR, confiado.
    3. código ambiguo, desconocido o NULL -> `DEFAULT_SAFE_ROL` (EJECUTOR),
       NO confiado — requiere revisión manual del Administrador post-deploy.
    """
    if is_superuser or is_staff:
        return "ADMINISTRADOR", True
    if job_profile_code in EJECUTOR_CODES:
        return "EJECUTOR", True
    if job_profile_code in COORDINADOR_CODES:
        return "COORDINADOR", True
    if job_profile_code in ADMINISTRADOR_CODES:
        return "ADMINISTRADOR", True
    return DEFAULT_SAFE_ROL, False


def backfill_rol(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    counts = {"EJECUTOR": 0, "COORDINADOR": 0, "ADMINISTRADOR": 0}
    sin_mapeo_defaulteado_ids = []

    for user in User.objects.select_related("job_profile").all():
        code = user.job_profile.code if user.job_profile_id else None
        rol, is_confident = resolve_rol(
            code, is_staff=user.is_staff, is_superuser=user.is_superuser
        )

        if is_confident:
            counts[rol] += 1
        else:
            sin_mapeo_defaulteado_ids.append(user.pk)

        user.rol = rol
        user.save(update_fields=["rol"])

    total = sum(counts.values()) + len(sin_mapeo_defaulteado_ids)
    if total:
        print(
            "\n[SD#58 A1] Backfill de User.rol completado sobre "
            f"{total} usuario(s). Confiados: EJECUTOR={counts['EJECUTOR']} "
            f"COORDINADOR={counts['COORDINADOR']} "
            f"ADMINISTRADOR={counts['ADMINISTRADOR']}. "
            f"Sin mapeo automático (defaulteados a EJECUTOR, requieren "
            f"revisión manual del Administrador vía A2): "
            f"{len(sin_mapeo_defaulteado_ids)} — ids: {sin_mapeo_defaulteado_ids}."
        )


def reverse_backfill(apps, schema_editor):
    # No-op: revertir a `rol=None` para TODOS los usuarios perdería la
    # distinción entre "backfilleado con confianza" y "defaulteado" sin
    # ningún beneficio real (la migración 0015, al revertirse, elimina la
    # columna de todas formas).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_user_rol_supervisor"),
    ]

    operations = [
        migrations.RunPython(backfill_rol, reverse_backfill),
    ]
