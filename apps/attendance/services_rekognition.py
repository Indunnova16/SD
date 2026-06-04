"""
Integración con AWS Rekognition para reconocimiento facial del personal.

Portado de Logisticacargues, retargeteado a `accounts.User`. La foto de
referencia es `User.photo`; el match guarda `User.aws_face_id`.

Flujo:
    1. Indexado: User.photo -> RekognitionService.index_user_face(user)
       -> guarda User.aws_face_id.
    2. Marcación: selfie -> RekognitionService.search_face(bytes)
       -> retorna SearchResult(user, similarity, aws_face_id, matched).

Configuración (settings):
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
    REKOGNITION_COLLECTION_ID
    REKOGNITION_MATCH_THRESHOLD (default 90)
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class RekognitionError(Exception):
    pass


class NoFaceDetectedError(RekognitionError):
    pass


class MissingReferencePhotoError(RekognitionError):
    """La ruta de User.photo en BD apunta a un archivo que no existe en el storage."""

    pass


@dataclass
class SearchResult:
    user: object  # User | None
    similarity: float  # 0..100
    aws_face_id: str
    matched: bool


class RekognitionService:
    @classmethod
    def _client(cls):
        if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY):
            raise RekognitionError(
                "Credenciales AWS no configuradas. Define AWS_ACCESS_KEY_ID "
                "y AWS_SECRET_ACCESS_KEY en variables de entorno."
            )
        return boto3.client(
            "rekognition",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    @classmethod
    def ensure_collection(cls):
        """Crea la collection si no existe. Idempotente."""
        client = cls._client()
        collection_id = settings.REKOGNITION_COLLECTION_ID
        try:
            client.describe_collection(CollectionId=collection_id)
            return False
        except client.exceptions.ResourceNotFoundException:
            client.create_collection(CollectionId=collection_id)
            logger.info("Rekognition collection creada: %s", collection_id)
            return True

    @classmethod
    def index_user_face(cls, user):
        """
        Indexa la foto de referencia (`user.photo`) en la collection Rekognition.
        Si el usuario ya tenía un aws_face_id, lo elimina solo DESPUÉS de indexar
        la nueva foto correctamente — así un fallo al leer/validar la nueva foto
        no deja al usuario sin cara en AWS.
        Devuelve el FaceId asignado.
        """
        if not user.photo:
            raise RekognitionError("El usuario no tiene foto de referencia.")

        client = cls._client()
        cls.ensure_collection()

        # Leer la nueva foto ANTES de tocar AWS. Si el archivo no existe
        # (e.g. quedó huérfano por un cambio de storage), la cara vieja
        # permanece intacta y el usuario puede seguir marcando.
        try:
            with user.photo.open("rb") as fh:
                image_bytes = fh.read()
        except FileNotFoundError as exc:
            raise MissingReferencePhotoError(
                "La foto de referencia no se encuentra en el almacenamiento. "
                "Sube nuevamente la foto desde el perfil del usuario."
            ) from exc

        previous_face_id = user.aws_face_id

        try:
            response = client.index_faces(
                CollectionId=settings.REKOGNITION_COLLECTION_ID,
                Image={"Bytes": image_bytes},
                ExternalImageId=str(user.id),
                DetectionAttributes=["DEFAULT"],
                MaxFaces=1,
                QualityFilter="AUTO",
            )
        except (BotoCoreError, ClientError) as exc:
            raise RekognitionError(f"Error AWS: {exc}") from exc

        face_records = response.get("FaceRecords", [])
        if not face_records:
            unindexed = response.get("UnindexedFaces", [])
            reason = unindexed[0].get("Reasons") if unindexed else "no detectada"
            raise NoFaceDetectedError(f"No se detectó un rostro válido en la foto. Razón: {reason}")

        face_id = face_records[0]["Face"]["FaceId"]
        user.aws_face_id = face_id
        user.face_indexed_at = timezone.now()
        user.save(update_fields=["aws_face_id", "face_indexed_at", "updated_at"])
        logger.info("Indexado usuario %s -> FaceId %s", user.id, face_id)

        # Solo ahora, con la nueva cara confirmada, borrar la vieja.
        if previous_face_id and previous_face_id != face_id:
            try:
                client.delete_faces(
                    CollectionId=settings.REKOGNITION_COLLECTION_ID,
                    FaceIds=[previous_face_id],
                )
            except ClientError as exc:
                logger.warning("No se pudo eliminar face previo %s: %s", previous_face_id, exc)

        return face_id

    @classmethod
    def remove_user_face(cls, user):
        """Elimina el rostro del usuario de la collection."""
        if not user.aws_face_id:
            return False
        client = cls._client()
        try:
            client.delete_faces(
                CollectionId=settings.REKOGNITION_COLLECTION_ID,
                FaceIds=[user.aws_face_id],
            )
        except ClientError as exc:
            logger.warning("Error eliminando face %s: %s", user.aws_face_id, exc)
            return False
        user.aws_face_id = ""
        user.face_indexed_at = None
        user.save(update_fields=["aws_face_id", "face_indexed_at", "updated_at"])
        return True

    @classmethod
    def search_face(cls, image_bytes, threshold=None):
        """
        Busca el rostro en la collection. Devuelve SearchResult.
        Si la similitud supera el threshold, busca el User asociado.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()

        if threshold is None:
            threshold = settings.REKOGNITION_MATCH_THRESHOLD

        client = cls._client()
        try:
            response = client.search_faces_by_image(
                CollectionId=settings.REKOGNITION_COLLECTION_ID,
                Image={"Bytes": image_bytes},
                MaxFaces=1,
                FaceMatchThreshold=float(threshold),
                QualityFilter="AUTO",
            )
        except client.exceptions.InvalidParameterException as exc:
            raise NoFaceDetectedError(str(exc)) from exc
        except (BotoCoreError, ClientError) as exc:
            raise RekognitionError(f"Error AWS: {exc}") from exc

        matches = response.get("FaceMatches", [])
        if not matches:
            return SearchResult(user=None, similarity=0.0, aws_face_id="", matched=False)

        best = matches[0]
        similarity = float(best["Similarity"])
        face_id = best["Face"]["FaceId"]
        external_id = best["Face"].get("ExternalImageId", "")

        user = None
        if external_id and external_id.isdigit():
            user = User.objects.filter(pk=int(external_id), is_active=True).first()
        if user is None:
            user = User.objects.filter(aws_face_id=face_id, is_active=True).first()

        return SearchResult(
            user=user,
            similarity=similarity,
            aws_face_id=face_id,
            matched=user is not None,
        )
