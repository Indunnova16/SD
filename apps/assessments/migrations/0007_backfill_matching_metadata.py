# Generated for SD#57.3 (fix hacia adelante + backfill).

from django.db import migrations


def backfill_matching_metadata(apps, schema_editor):
    """SD#57.3: builder_add_lesson (Ruta B) creaba preguntas tipo Emparejamiento
    sin poblar question.metadata['match_pairs'] -- AssessmentService.
    _grade_objective_answer arma correct_map EXCLUSIVAMENTE desde metadata, asi
    que esas preguntas quedaban SIEMPRE incorrectas sin importar la respuesta
    del estudiante (confirmado en BD prod: questions id=25 e id=37, metadata='{}').

    Este backfill es GENERICO (no hardcodea 25/37 -- Miguel y F2 decidieron
    cubrir cualquier otra fila con el mismo hueco que pueda existir antes del
    deploy) y deriva match_pairs de los Answer YA CREADOS (fuente de verdad
    real, la misma que ve el builder y el estudiante), sin re-calificar
    attempt_answers/assessment_attempts ya guardados (decision explicita de
    Miguel: 0 certificaciones reales afectadas segun BD prod).
    """
    Question = apps.get_model("assessments", "Question")
    for question in Question.objects.filter(question_type="matching", metadata={}):
        pairs = [
            {"left": answer.text, "right": answer.feedback}
            for answer in question.answers.order_by("order")
        ]
        if not pairs:
            # Sin Answer creados (pregunta matching vacia/incompleta) -- nada
            # que derivar, no tocar.
            continue
        question.metadata = {"match_pairs": pairs}
        question.save(update_fields=["metadata"])


def noop_reverse(apps, schema_editor):
    # No reversible por diseño: no distinguimos qué preguntas tenían metadata
    # vacío "legítimamente" (nunca se pobló) de las que este backfill llenó.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0006_alter_max_attempts_default_and_backfill"),
    ]

    operations = [
        migrations.RunPython(backfill_matching_metadata, noop_reverse),
    ]
