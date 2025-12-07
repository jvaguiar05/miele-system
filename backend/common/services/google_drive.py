import logging
import io
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """
    Serviço de Infraestrutura para Google Drive (Proxy Pattern).
    Gerencia apenas a comunicação I/O com a API.
    """

    def __init__(self):
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.credentials_file = getattr(settings, "GDRIVE_SERVICE_ACCOUNT_FILE", None)
        self.service = None

        # Mapping de pastas (definido no settings)
        self.folder_map = {
            "client": getattr(settings, "GDRIVE_CLIENTS_FOLDER_ID", None),
            "perdcomp": getattr(settings, "GDRIVE_PERDCOMPS_FOLDER_ID", None),
        }

    def _get_service(self):
        if not self.service:
            if not self.credentials_file:
                raise Exception("GDRIVE_SERVICE_ACCOUNT_FILE não configurado.")

            creds = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=self.scopes
            )
            self.service = build("drive", "v3", credentials=creds)
        return self.service

    def upload_stream(
        self, file_obj, filename: str, entity_type: str, mime_type: str
    ) -> str:
        """
        Recebe um arquivo em memória (InMemoryUploadedFile) e envia para o Drive.
        Retorna o ID do arquivo no Drive.
        """
        service = self._get_service()

        # Determinar pasta destino
        parent_id = self.folder_map.get(entity_type)
        if not parent_id:
            logger.warning(f"Pasta não configurada para {entity_type}, usando raiz.")
            # Se não tiver pasta configurada, vai para a raiz do Drive do robô
            parent_id = None

        file_metadata = {"name": filename}
        if parent_id:
            file_metadata["parents"] = [parent_id]

        # Configura o upload via stream usando o mime_type passado explicitamente
        media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)

        try:
            file = (
                service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )

            return file.get("id")
        except HttpError as e:
            logger.error(f"Erro de I/O no Google Drive: {e}")
            raise

    def download_stream(self, file_id: str) -> io.BytesIO:
        """
        Baixa o arquivo do Drive para um buffer em memória.
        """
        service = self._get_service()
        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            fh.seek(0)
            return fh
        except HttpError as e:
            logger.error(f"Erro ao baixar arquivo {file_id}: {e}")
            raise

    def delete_file(self, file_id: str):
        """Remove o arquivo do Drive."""
        service = self._get_service()
        try:
            service.files().delete(fileId=file_id).execute()
        except HttpError as e:
            if e.resp.status == 404:
                return  # Já não existe, tudo bem
            raise


drive_service = GoogleDriveService()
