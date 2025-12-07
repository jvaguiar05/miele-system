import logging
import io
from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """
    Serviço de Infraestrutura para Google Drive (Proxy Pattern).
    Usa OAuth 2.0 com Refresh Token para agir como o usuário dono (contornando cota zero).
    """

    def __init__(self):
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.service = None

        # Credenciais OAuth
        self.client_id = getattr(settings, "GDRIVE_CLIENT_ID", None)
        self.client_secret = getattr(settings, "GDRIVE_CLIENT_SECRET", None)
        self.refresh_token = getattr(settings, "GDRIVE_REFRESH_TOKEN", None)

        self.folder_map = {
            "client": getattr(settings, "GDRIVE_CLIENTS_FOLDER_ID", None),
            "perdcomp": getattr(settings, "GDRIVE_PERDCOMPS_FOLDER_ID", None),
        }

    def _get_service(self):
        """
        Constrói o serviço usando o Refresh Token para gerar Access Tokens automaticamente.
        """
        if not self.service:
            if not all([self.client_id, self.client_secret, self.refresh_token]):
                raise Exception(
                    "Credenciais OAuth (Client ID, Secret, Refresh Token) não configuradas."
                )

            # Monta as credenciais. O Access Token é None porque a lib vai
            # usar o refresh_token para buscar um novo automaticamente.
            creds = Credentials(
                None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.scopes,
            )

            self.service = build(
                "drive", "v3", credentials=creds, cache_discovery=False
            )
        return self.service

    def upload_stream(
        self, file_obj, filename: str, entity_type: str, mime_type: str
    ) -> str:
        """
        Faz upload agindo como o usuário autenticado via OAuth.
        """
        service = self._get_service()

        parent_id = self.folder_map.get(entity_type)
        if not parent_id:
            logger.warning(f"Pasta não configurada para {entity_type}, usando raiz.")
            parent_id = None

        file_metadata = {"name": filename}
        if parent_id:
            file_metadata["parents"] = [parent_id]

        media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)

        try:
            file = (
                service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
            return file.get("id")
        except HttpError as e:
            logger.error(f"Erro de I/O no Google Drive (OAuth): {e}")
            raise

    def download_stream(self, file_id: str) -> io.BytesIO:
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
        service = self._get_service()
        try:
            service.files().delete(fileId=file_id).execute()
        except HttpError as e:
            if e.resp.status == 404:
                return
            raise


drive_service = GoogleDriveService()
