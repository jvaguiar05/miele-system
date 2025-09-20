# Componentes e schemas customizados para documentação API

from drf_spectacular.utils import OpenApiResponse, OpenApiExample
from drf_spectacular.openapi import AutoSchema
from rest_framework import status


# Respostas de erro padrão
ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=None,
        description="Requisição inválida - dados malformados ou validação falhou",
        examples=[
            OpenApiExample(
                "Erro de validação",
                value={
                    "error": {
                        "code": "validation_error",
                        "message": "Dados de entrada inválidos",
                        "details": {"field": ["Este campo é obrigatório"]},
                        "correlation_id": "uuid-exemplo"
                    }
                }
            )
        ]
    ),
    401: OpenApiResponse(
        response=None,
        description="Não autorizado - token inválido ou ausente",
        examples=[
            OpenApiExample(
                "Token inválido",
                value={
                    "error": {
                        "code": "authentication_failed",
                        "message": "Token de autenticação inválido",
                        "details": {},
                        "correlation_id": "uuid-exemplo"
                    }
                }
            )
        ]
    ),
    403: OpenApiResponse(
        response=None,
        description="Proibido - usuário não tem permissão para acessar este recurso",
        examples=[
            OpenApiExample(
                "Sem permissão",
                value={
                    "error": {
                        "code": "permission_denied",
                        "message": "Você não tem permissão para executar esta ação",
                        "details": {},
                        "correlation_id": "uuid-exemplo"
                    }
                }
            )
        ]
    ),
    404: OpenApiResponse(
        response=None,
        description="Não encontrado - recurso solicitado não existe",
        examples=[
            OpenApiExample(
                "Recurso não encontrado",
                value={
                    "error": {
                        "code": "not_found",
                        "message": "O recurso solicitado não foi encontrado",
                        "details": {},
                        "correlation_id": "uuid-exemplo"
                    }
                }
            )
        ]
    ),
    429: OpenApiResponse(
        response=None,
        description="Muitas requisições - limite de rate limiting excedido",
        examples=[
            OpenApiExample(
                "Rate limit excedido",
                value={
                    "error": {
                        "code": "throttled",
                        "message": "Taxa de requisições excedida. Tente novamente em alguns minutos.",
                        "details": {"available_in": "60 seconds"},
                        "correlation_id": "uuid-exemplo"
                    }
                }
            )
        ]
    ),
    500: OpenApiResponse(
        response=None,
        description="Erro interno do servidor",
        examples=[
            OpenApiExample(
                "Erro interno",
                value={
                    "error": {
                        "code": "internal_error",
                        "message": "Ocorreu um erro inesperado. Tente novamente mais tarde.",
                        "details": {},
                        "correlation_id": "uuid-exemplo"
                    }
                }
            )
        ]
    ),
}

# Respostas de sucesso comuns
SUCCESS_RESPONSES = {
    "login_success": OpenApiResponse(
        response=None,
        description="Login realizado com sucesso",
        examples=[
            OpenApiExample(
                "Login bem-sucedido",
                value={
                    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
                }
            )
        ]
    ),
    "logout_success": OpenApiResponse(
        response=None,
        description="Logout realizado com sucesso"
    ),
    "registration_success": OpenApiResponse(
        response=None,
        description="Usuário registrado com sucesso",
        examples=[
            OpenApiExample(
                "Registro bem-sucedido",
                value={
                    "message": "Usuário registrado com sucesso.",
                    "username": "novo_usuario",
                    "email": "usuario@exemplo.com",
                    "approval_status": "pending"
                }
            )
        ]
    ),
    "password_changed": OpenApiResponse(
        response=None,
        description="Senha alterada com sucesso",
        examples=[
            OpenApiExample(
                "Senha alterada",
                value={
                    "message": "Senha alterada com sucesso."
                }
            )
        ]
    ),
    "account_deactivated": OpenApiResponse(
        response=None,
        description="Conta desativada com sucesso",
        examples=[
            OpenApiExample(
                "Conta desativada",
                value={
                    "message": "Conta do usuário desativada com sucesso."
                }
            )
        ]
    ),
    "request_created": OpenApiResponse(
        response=None,
        description="Solicitação criada com sucesso",
        examples=[
            OpenApiExample(
                "Solicitação criada",
                value={
                    "message": "Solicitação de alteração criada com sucesso.",
                    "request_id": "uuid-da-solicitacao"
                }
            )
        ]
    ),
    "request_reviewed": OpenApiResponse(
        response=None,
        description="Solicitação revisada com sucesso",
        examples=[
            OpenApiExample(
                "Solicitação aprovada",
                value={
                    "message": "Solicitação aprovada com sucesso.",
                    "request_id": "uuid-da-solicitacao",
                    "action": "approved"
                }
            )
        ]
    )
}
