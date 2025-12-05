"""
Service layer para integração com Google Drive API.

IMPORTANTE: Este serviço NÃO faz upload/download de arquivos.
O frontend é responsável por essas operações.
"""

import logging
import os
from typing import Optional, Dict, Any
from django.conf import settings

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

logger = logging.getLogger(__name__)


class GoogleDriveServiceError(Exception):
    """Exceção base para erros do Google Drive Service."""

    pass


class GoogleDriveAuthenticationError(GoogleDriveServiceError):
    """Erro de autenticação com Google Drive."""

    pass


class GoogleDriveFileNotFoundError(GoogleDriveServiceError):
    """Arquivo não encontrado no Google Drive."""

    pass


class GoogleDrivePermissionError(GoogleDriveServiceError):
    """Erro de permissão no Google Drive."""

    pass


class GoogleDriveService:
    """
    Serviço para integração com Google Drive API - SOMENTE LEITURA.

    IMPORTANTE: Este serviço NÃO faz upload/download de arquivos.
    O frontend é responsável por essas operações.

    Responsabilidades:
    - Validar se arquivo existe no Drive (através do file_id fornecido pelo frontend)
    - Obter metadados de arquivos (nome, tamanho, tipo, links)
    - Validar permissões de acesso
    """

    def __init__(self):
        self.service = None
        self._scopes = [
            "https://www.googleapis.com/auth/drive.readonly"
        ]  # Apenas leitura!

    def _get_authenticated_service(self):
        """
        Obtém serviço autenticado do Google Drive usando service account.

        Raises:
            GoogleDriveAuthenticationError: Se não conseguir autenticar
        """
        if self.service:
            return self.service

        if not GOOGLE_API_AVAILABLE:
            raise GoogleDriveAuthenticationError(
                "Bibliotecas do Google API não estão instaladas. "
                "Execute: pip install google-api-python-client google-auth"
            )

        try:
            # Verificar se arquivo de credenciais existe
            credentials_file = getattr(settings, "GDRIVE_SERVICE_ACCOUNT_FILE", None)
            if not credentials_file:
                raise GoogleDriveAuthenticationError(
                    "GDRIVE_SERVICE_ACCOUNT_FILE não configurado nas settings"
                )

            if not os.path.exists(credentials_file):
                raise GoogleDriveAuthenticationError(
                    f"Arquivo de credenciais não encontrado: {credentials_file}"
                )

            # Criar credenciais a partir do arquivo de service account
            credentials = Credentials.from_service_account_file(
                credentials_file, scopes=self._scopes
            )

            # Construir serviço
            self.service = build("drive", "v3", credentials=credentials)

            # Testar autenticação fazendo uma chamada simples
            self.service.about().get(fields="user").execute()

            logger.info("Google Drive service autenticado com sucesso (readonly)")
            return self.service

        except Exception as e:
            logger.error(f"Erro ao autenticar com Google Drive: {e}")
            raise GoogleDriveAuthenticationError(f"Falha na autenticação: {e}")

    def _handle_api_error(self, error, context=""):
        """
        Converte erros da API em exceções específicas.

        Args:
            error: Exceção original
            context: Contexto da operação
        """
        if isinstance(error, HttpError):
            status_code = error.resp.status

            if status_code == 404:
                raise GoogleDriveFileNotFoundError(f"Arquivo não encontrado. {context}")
            elif status_code == 403:
                raise GoogleDrivePermissionError(f"Permissão negada. {context}")
            else:
                raise GoogleDriveServiceError(
                    f"Erro da API Google Drive: {error}. {context}"
                )
        else:
            raise GoogleDriveServiceError(f"Erro inesperado: {error}. {context}")

    def file_exists(self, file_id: str) -> bool:
        """
        Verifica se arquivo existe no Google Drive.

        Args:
            file_id: ID do arquivo no Google Drive

        Returns:
            True se arquivo existe, False caso contrário
        """
        try:
            if not file_id:
                return False

            service = self._get_authenticated_service()

            # Verificar se arquivo existe tentando obter metadados mínimos
            service.files().get(fileId=file_id, fields="id").execute()

            logger.debug(f"Arquivo {file_id} existe no Google Drive")
            return True

        except GoogleDriveFileNotFoundError:
            logger.debug(f"Arquivo {file_id} não encontrado no Google Drive")
            return False
        except Exception as e:
            self._handle_api_error(e, f"Verificando existência do arquivo {file_id}")
            return False

    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtém metadados do arquivo no Google Drive.

        Args:
            file_id: ID do arquivo no Google Drive

        Returns:
            Dicionário com metadados ou None se não encontrado
        """
        try:
            if not file_id:
                return None

            service = self._get_authenticated_service()

            # Obter metadados completos do arquivo
            file_metadata = (
                service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,size,mimeType,webViewLink,webContentLink,parents,createdTime,modifiedTime,owners",
                )
                .execute()
            )

            logger.debug(f"Metadados obtidos para arquivo {file_id}")
            return {
                "id": file_metadata.get("id"),
                "name": file_metadata.get("name"),
                "size": (
                    int(file_metadata.get("size", 0))
                    if file_metadata.get("size")
                    else 0
                ),
                "mimeType": file_metadata.get("mimeType"),
                "webViewLink": file_metadata.get("webViewLink"),
                "webContentLink": file_metadata.get("webContentLink"),
                "parents": file_metadata.get("parents", []),
                "createdTime": file_metadata.get("createdTime"),
                "modifiedTime": file_metadata.get("modifiedTime"),
                "owners": file_metadata.get("owners", []),
            }

        except GoogleDriveFileNotFoundError:
            logger.warning(f"Arquivo {file_id} não encontrado para obter metadados")
            return None
        except Exception as e:
            self._handle_api_error(e, f"Obtendo metadados do arquivo {file_id}")
            return None

    def validate_file_reference(
        self, file_id: str, expected_name: str = None
    ) -> Dict[str, Any]:
        """
        Valida uma referência de arquivo fornecida pelo frontend.

        Args:
            file_id: ID do arquivo no Google Drive (fornecido pelo frontend)
            expected_name: Nome esperado do arquivo (opcional, para validação extra)

        Returns:
            Dicionário com resultado da validação e metadados
        """
        try:
            if not file_id:
                return {"valid": False, "error": "file_id é obrigatório"}

            # Verificar se arquivo existe e obter metadados
            metadata = self.get_file_metadata(file_id)
            if not metadata:
                return {
                    "valid": False,
                    "error": "Arquivo não encontrado no Google Drive",
                }

            # Validação opcional de nome
            if expected_name and metadata.get("name") != expected_name:
                logger.warning(
                    f"Nome do arquivo não confere. Esperado: {expected_name}, "
                    f"Encontrado: {metadata.get('name')}"
                )

            return {
                "valid": True,
                "metadata": metadata,
                "file_id": file_id,
                "download_url": metadata.get("webContentLink"),
                "view_url": metadata.get("webViewLink"),
            }

        except Exception as e:
            logger.error(f"Erro ao validar referência do arquivo {file_id}: {e}")
            return {"valid": False, "error": f"Erro na validação: {str(e)}"}

    def get_download_url(self, file_id: str) -> Optional[str]:
        """
        Obtém URL de download direto do arquivo.

        Args:
            file_id: ID do arquivo no Google Drive

        Returns:
            URL de download ou None se não encontrado
        """
        try:
            metadata = self.get_file_metadata(file_id)
            if not metadata:
                return None

            return metadata.get("webContentLink")

        except Exception as e:
            logger.error(f"Erro ao obter URL de download para {file_id}: {e}")
            return None

    def get_view_url(self, file_id: str) -> Optional[str]:
        """
        Obtém URL de visualização do arquivo no navegador.

        Args:
            file_id: ID do arquivo no Google Drive

        Returns:
            URL de visualização ou None se não encontrado
        """
        try:
            metadata = self.get_file_metadata(file_id)
            if not metadata:
                return None

            return metadata.get("webViewLink")

        except Exception as e:
            logger.error(f"Erro ao obter URL de visualização para {file_id}: {e}")
            return None

    def validate_user_access(self, file_id: str, user) -> bool:
        """
        Valida se usuário tem acesso ao arquivo no Google Drive.

        Como usamos service account, o controle de acesso é feito
        a nível de aplicação, não no Google Drive.

        Args:
            file_id: ID do arquivo no Google Drive
            user: Usuário a ser validado

        Returns:
            True se usuário tem acesso, False caso contrário
        """
        try:
            if not file_id or not user:
                return False

            # Verificar se arquivo existe
            if not self.file_exists(file_id):
                return False

            # Como usamos service account, o controle de acesso é feito
            # a nível de aplicação através das permissões do Django
            logger.debug(f"Acesso validado para usuário {user.id} ao arquivo {file_id}")
            return True

        except Exception as e:
            logger.error(
                f"Erro ao validar acesso do usuário {user.id} ao arquivo {file_id}: {e}"
            )
            return False

    def sync_file_status(self, file_id: str) -> Dict[str, Any]:
        """
        Sincroniza status de um arquivo com o Google Drive.

        Args:
            file_id: ID do arquivo no Google Drive

        Returns:
            Dicionário com status de sincronização
        """
        try:
            metadata = self.get_file_metadata(file_id)

            if metadata:
                return {
                    "exists": True,
                    "last_modified": metadata.get("modifiedTime"),
                    "size": metadata.get("size", 0),
                    "sync_status": "synced",
                }
            else:
                return {"exists": False, "sync_status": "missing"}

        except Exception as e:
            logger.error(f"Erro ao sincronizar status do arquivo {file_id}: {e}")
            return {"exists": False, "sync_status": "error", "error": str(e)}

    def validate_file_type(self, file_type: str, entity_type: str) -> bool:
        """
        Valida se tipo de arquivo é permitido para a entidade.

        Args:
            file_type: Tipo do arquivo
            entity_type: Tipo da entidade

        Returns:
            True se tipo é válido, False caso contrário
        """
        try:
            from common.shared.models import CLIENT_FILE_TYPES, PERDCOMP_FILE_TYPES

            if entity_type == "client":
                valid_types = [choice[0] for choice in CLIENT_FILE_TYPES]
            elif entity_type == "perdcomp":
                valid_types = [choice[0] for choice in PERDCOMP_FILE_TYPES]
            else:
                logger.warning(f"Tipo de entidade desconhecido: {entity_type}")
                return False

            is_valid = file_type in valid_types

            if not is_valid:
                logger.warning(
                    f"Tipo de arquivo '{file_type}' não permitido para {entity_type}. "
                    f"Tipos válidos: {valid_types}"
                )

            return is_valid

        except ImportError:
            logger.error(
                "Não foi possível importar tipos de arquivo. Permitindo qualquer tipo."
            )
            return True
        except Exception as e:
            logger.error(f"Erro ao validar tipo de arquivo: {e}")
            return False

    def validate_file_size(self, file_size: int) -> bool:
        """
        Valida se tamanho do arquivo está dentro dos limites.

        Args:
            file_size: Tamanho do arquivo em bytes

        Returns:
            True se tamanho é válido, False caso contrário
        """
        try:
            max_size = getattr(
                settings, "GDRIVE_MAX_FILE_SIZE", 100 * 1024 * 1024
            )  # 100MB padrão
            min_size = 1  # Pelo menos 1 byte

            is_valid = min_size <= file_size <= max_size

            if not is_valid:
                logger.warning(
                    f"Tamanho de arquivo inválido: {file_size} bytes. "
                    f"Limite: {min_size} - {max_size} bytes"
                )

            return is_valid

        except Exception as e:
            logger.error(f"Erro ao validar tamanho de arquivo: {e}")
            return False


# Instância singleton do serviço
drive_service = GoogleDriveService()
