from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from rest_framework.parsers import JSONParser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from .throttling import (
    AuthLoginThrottle,
    AuthRegisterThrottle,
    AuthRefreshThrottle,
    SensitiveActionThrottle,
    FailedLoginAttemptThrottle,
)
from django_otp.oath import TOTP
from django_otp.util import random_hex
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from django.utils import timezone
from .models import TOTPDevice, SensibleDataChangeRequest
from common.audit.models import AuditLog
from api.schemas.spectacular import ERROR_RESPONSES, SUCCESS_RESPONSES
from .permissions import IsAdmin, IsEmployeeOrAdmin, IsOwnerOrAdmin
from .serializers import (
    LogoutSerializer,
    RBACSerializer,
    TOTPEnrollSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    AuthThrottleSerializer,
    UserRegistrationSerializer,
    UserDeleteSerializer,
    SensibleDataChangeRequestSerializer,
    EmailChangeRequestSerializer,
    ReviewChangeRequestSerializer,
    CustomTokenObtainPairSerializer,
)
from .exceptions import (
    InvalidPasswordError,
    PasswordValidationError,
    ChangeRequestNotFoundError,
    InvalidTokenError,
)


class PingView(APIView):
    """
    Endpoint simples para verificação de saúde da API.
    Não requer autenticação.
    """

    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=["Autenticação"],
        summary="Verificação de saúde da API",
        description="Endpoint simples para verificar se a API está funcionando. Não requer autenticação.",
        responses={
            200: OpenApiResponse(
                description="API funcionando corretamente",
                examples=[OpenApiExample("Sucesso", value={"ok": True})],
            )
        },
    )
    def get(self, request):
        return Response({"ok": True})


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Endpoint de autenticação com JWT.
    Suporta throttling agressivo contra ataques de força bruta.
    """

    throttle_classes = [AuthLoginThrottle, FailedLoginAttemptThrottle]
    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(
        tags=["Autenticação"],
        summary="Autenticação de usuário",
        description="""
        Realiza login do usuário e retorna tokens JWT (access e refresh).
        
        **Características:**
        - Throttling agressivo contra ataques de força bruta
        - Verifica status de aprovação da conta
        - Retorna mensagens de erro específicas
        - Suporta blacklist de tokens
        
        **Validações:**
        - Conta deve estar ativa
        - Conta deve estar aprovada (não pendente ou rejeitada)
        - Credenciais válidas
        """,
        request=CustomTokenObtainPairSerializer,
        responses={
            200: SUCCESS_RESPONSES["login_success"],
            400: ERROR_RESPONSES[400],
            401: OpenApiResponse(
                description="Credenciais inválidas ou conta com problema",
                examples=[
                    OpenApiExample(
                        "Credenciais inválidas",
                        value={
                            "error": {
                                "code": "authentication_failed",
                                "message": "Nome de usuário ou senha inválidos",
                                "details": {},
                            }
                        },
                    ),
                    OpenApiExample(
                        "Conta pendente",
                        value={"detail": "Sua conta está pendente de aprovação."},
                    ),
                    OpenApiExample(
                        "Conta rejeitada",
                        value={
                            "detail": "Sua conta foi rejeitada. Entre em contato com o suporte."
                        },
                    ),
                    OpenApiExample(
                        "Conta inativa",
                        value={
                            "detail": "Esta conta está inativa. Entre em contato com o suporte."
                        },
                    ),
                ],
            ),
            429: ERROR_RESPONSES[429],
            500: ERROR_RESPONSES[500],
        },
    )
    def post(self, request, *args, **kwargs):
        # Use our custom serializer which already handles user validation
        return super().post(request, *args, **kwargs)


class CustomTokenRefreshView(TokenRefreshView):
    """
    Endpoint para renovação de tokens JWT.
    Utiliza o refresh token para gerar novo access token.
    """

    throttle_classes = [AuthRefreshThrottle]

    @extend_schema(
        tags=["Autenticação"],
        summary="Renovação de token JWT",
        description="""
        Renova o access token utilizando um refresh token válido.
        
        **Características:**
        - Rotation automática de refresh tokens (opcional)
        - Blacklist de tokens antigos
        - Throttling moderado
        
        **Segurança:**
        - Refresh tokens são de uso único (quando rotation habilitada)
        - Tokens inválidos são rejeitados
        - Rate limiting aplicado
        """,
        responses={
            200: OpenApiResponse(
                description="Token renovado com sucesso",
                examples=[
                    OpenApiExample(
                        "Renovação bem-sucedida",
                        value={
                            "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                            "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Refresh token inválido ou expirado",
                examples=[
                    OpenApiExample(
                        "Token inválido",
                        value={
                            "detail": "Token is invalid or expired",
                            "code": "token_not_valid",
                        },
                    )
                ],
            ),
            429: ERROR_RESPONSES[429],
            500: ERROR_RESPONSES[500],
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """
    Endpoint para logout do usuário.
    Adiciona o refresh token à blacklist para invalidá-lo.
    """

    serializer_class = LogoutSerializer
    throttle_classes = [UserRateThrottle]  # Standard user throttling for logout

    @extend_schema(
        tags=["Autenticação"],
        summary="Logout do usuário",
        description="""
        Realiza logout do usuário adicionando o refresh token à blacklist.
        
        **Características:**
        - Invalida o refresh token fornecido
        - Impede reutilização do token
        - Rate limiting padrão
        
        **Segurança:**
        - Token vai para blacklist permanente
        - Não afeta outros tokens ativos do usuário
        - Operação idempotente
        """,
        request=LogoutSerializer,
        responses={
            205: SUCCESS_RESPONSES["logout_success"],
            400: OpenApiResponse(
                description="Token de refresh inválido ou já blacklisted",
                examples=[
                    OpenApiExample(
                        "Token inválido",
                        value={
                            "error": "O token de refresh fornecido é inválido ou já foi invalidado."
                        },
                    )
                ],
            ),
            429: ERROR_RESPONSES[429],
            500: ERROR_RESPONSES[500],
        },
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data["refresh"]
        try:
            token = RefreshToken(refresh_token)

            # Get user from token before blacklisting
            user_id = token.payload.get("user_id")
            user = None
            if user_id:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    user = None

            # Blacklist the token
            token.blacklist()

            # Log logout action
            if user:
                from common.audit.services import AuditService

                # Get request metadata for IP address
                metadata = {}
                ip_address = request.META.get("REMOTE_ADDR")
                if ip_address:
                    metadata["ip"] = ip_address
                metadata["logout_type"] = "api"

                AuditService.log_action(
                    action="LOGOUT", content_object=user, user=user, metadata=metadata
                )

        except Exception:
            raise InvalidTokenError()
        return Response(status=status.HTTP_205_RESET_CONTENT)


class RBACView(APIView):
    """
    Endpoint para verificação de permissões do usuário autenticado.
    Retorna as capacidades baseadas no role do usuário.
    """

    serializer_class = RBACSerializer
    permission_classes = [IsEmployeeOrAdmin]  # Employee or Admin can check permissions

    @extend_schema(
        tags=["Autenticação"],
        summary="Verificação de permissões RBAC",
        description="""
        Retorna as permissões e capacidades do usuário autenticado baseadas em seu role.
        
        **Roles disponíveis:**
        - **ADMIN**: Acesso completo ao sistema
        - **EMPLOYEE**: Acesso a operações de negócio
        - **GUEST**: Acesso apenas de leitura
        
        **Informações retornadas:**
        - Dados básicos do usuário
        - Role atual
        - Status de aprovação
        - Mapa completo de permissões
        """,
        responses={
            200: OpenApiResponse(
                description="Informações de permissões do usuário",
                examples=[
                    OpenApiExample(
                        "Permissões de Employee",
                        value={
                            "user_id": "uuid-do-usuario",
                            "username": "employee_user",
                            "role": "employee",
                            "approval_status": "approved",
                            "permissions": {
                                "can_view_all_clients": True,
                                "can_edit_clients": True,
                                "can_view_all_perdcomps": True,
                                "can_edit_perdcomps": True,
                                "can_view_all_logs": False,
                                "can_view_own_logs": True,
                                "can_approve_requests": False,
                                "can_change_sensible_data": False,
                                "is_read_only": False,
                            },
                        },
                    ),
                    OpenApiExample(
                        "Permissões de Admin",
                        value={
                            "user_id": "uuid-do-admin",
                            "username": "admin_user",
                            "role": "admin",
                            "approval_status": "approved",
                            "permissions": {
                                "can_view_all_clients": True,
                                "can_edit_clients": True,
                                "can_view_all_perdcomps": True,
                                "can_edit_perdcomps": True,
                                "can_view_all_logs": True,
                                "can_view_own_logs": True,
                                "can_approve_requests": True,
                                "can_change_sensible_data": True,
                                "is_read_only": False,
                            },
                        },
                    ),
                ],
            ),
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
            500: ERROR_RESPONSES[500],
        },
    )
    def get(self, request):
        user = request.user
        return Response(
            {
                "user_id": user.public_id,
                "username": user.username,
                "role": user.role,
                "approval_status": user.approval_status,
                "permissions": {
                    "can_view_all_clients": user.role
                    in [user.UserRole.EMPLOYEE, user.UserRole.ADMIN],
                    "can_edit_clients": user.role
                    in [user.UserRole.EMPLOYEE, user.UserRole.ADMIN],
                    "can_view_all_perdcomps": user.role
                    in [user.UserRole.EMPLOYEE, user.UserRole.ADMIN],
                    "can_edit_perdcomps": user.role
                    in [user.UserRole.EMPLOYEE, user.UserRole.ADMIN],
                    "can_view_all_logs": user.role == user.UserRole.ADMIN,
                    "can_view_own_logs": user.role == user.UserRole.EMPLOYEE,
                    "can_approve_requests": user.role == user.UserRole.ADMIN,
                    "can_change_sensible_data": user.role == user.UserRole.ADMIN,
                    "is_read_only": user.role == user.UserRole.GUEST,
                },
            }
        )


class UserProfileView(APIView):
    """
    Endpoint para visualização e edição do perfil do usuário.
    Usuários podem editar seu próprio perfil, admins podem editar qualquer perfil.
    """

    serializer_class = UserProfileSerializer
    permission_classes = [
        IsOwnerOrAdmin
    ]  # Users can view/edit own profile, admins can edit any

    @extend_schema(
        tags=["Usuários"],
        summary="Visualizar perfil do usuário",
        description="""
        Retorna os dados do perfil do usuário autenticado.
        
        **Campos retornados:**
        - Username
        - Nome completo (first_name, last_name)
        - Email
        - Data de registro (date_joined)
        - Dados públicos do perfil
        """,
        responses={
            200: OpenApiResponse(
                description="Dados do perfil do usuário",
                examples=[
                    OpenApiExample(
                        "Perfil do usuário",
                        value={
                            "username": "usuario_exemplo",
                            "first_name": "João",
                            "last_name": "Silva",
                            "email": "joao.silva@exemplo.com",
                            "date_joined": "2025-01-15T10:30:00Z",
                        },
                    )
                ],
            ),
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
            500: ERROR_RESPONSES[500],
        },
    )
    def get(self, request):
        user = request.user
        serializer = self.serializer_class(user)
        return Response(serializer.data)

    @extend_schema(
        tags=["Usuários"],
        summary="Atualizar perfil do usuário",
        description="""
        Atualiza os dados do perfil do usuário autenticado.
        
        **Campos editáveis:**
        - first_name: Primeiro nome
        - last_name: Sobrenome
        
        **Campos somente leitura:**
        - username: Nome de usuário (imutável)
        - email: Email (requer processo de change request separado)
        - date_joined: Data de registro (imutável)
        
        **Restrições:**
        - Email requer processo de change request
        - Username não pode ser alterado
        - Dados sensíveis requerem aprovação admin
        """,
        request=UserProfileSerializer,
        responses={
            200: OpenApiResponse(
                description="Perfil atualizado com sucesso",
                examples=[
                    OpenApiExample(
                        "Perfil atualizado",
                        value={
                            "username": "usuario_exemplo",
                            "first_name": "João Carlos",
                            "last_name": "Silva Santos",
                            "email": "joao.silva@exemplo.com",
                            "date_joined": "2025-01-15T10:30:00Z",
                        },
                    )
                ],
            ),
            400: ERROR_RESPONSES[400],
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
            500: ERROR_RESPONSES[500],
        },
    )
    def patch(self, request, *args, **kwargs):
        user = request.user

        # Capture old data for audit logging
        from common.audit.services import AuditService

        old_data = AuditService._serialize_object(user)
        old_data = AuditService._filter_relevant_data(old_data)

        serializer = UserProfileSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            # Temporarily disable automatic audit for this save
            user.__audit__ = False
            serializer.save()
            # Re-enable audit for future operations
            user.__audit__ = True

            # Log the profile update with explicit audit
            AuditService.log_update(
                content_object=user,
                old_data=old_data,
                user=user,
                metadata={
                    "type": "profile_update",
                    "ip": request.META.get("REMOTE_ADDR"),
                },
            )

            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    Endpoint para alteração de senha do usuário.
    Requer senha atual para confirmação e aplica políticas de senha forte.
    """

    serializer_class = ChangePasswordSerializer
    permission_classes = [
        IsOwnerOrAdmin
    ]  # Users can change own password, admins can change any
    parser_classes = [JSONParser]

    @extend_schema(
        tags=["Usuários"],
        summary="Alterar senha do usuário",
        description="""
        Permite que o usuário altere sua senha fornecendo a senha atual e a nova senha.
        
        **Validações aplicadas:**
        - Senha atual deve estar correta
        - Nova senha deve seguir política de segurança
        - Confirmação de nova senha
        
        **Política de senha:**
        - Mínimo 8 caracteres
        - Mistura de letras, números e símbolos
        - Não pode ser muito comum
        - Não pode ser muito similar aos dados pessoais
        
        **Segurança:**
        - Invalidação de tokens existentes (opcional)
        - Log de auditoria da alteração
        - Notificação por email (opcional)
        """,
        request=ChangePasswordSerializer,
        responses={
            200: SUCCESS_RESPONSES["password_changed"],
            400: OpenApiResponse(
                description="Dados inválidos ou política de senha não atendida",
                examples=[
                    OpenApiExample(
                        "Senha atual inválida",
                        value={
                            "error": {
                                "code": "invalid_password",
                                "message": "A senha atual está incorreta.",
                                "details": {},
                            }
                        },
                    ),
                    OpenApiExample(
                        "Nova senha fraca",
                        value={
                            "error": {
                                "code": "password_validation_error",
                                "message": "A nova senha não atende aos critérios de segurança.",
                                "details": {
                                    "password": [
                                        "Esta senha é muito comum.",
                                        "A senha deve ter pelo menos 8 caracteres.",
                                    ]
                                },
                            }
                        },
                    ),
                ],
            ),
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
        },
    )
    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        if not request.user.check_password(old_password):
            raise InvalidPasswordError()

        try:
            validate_password(new_password, request.user)
        except ValidationError as e:
            raise PasswordValidationError()

        # Capture old data for audit logging (without password)
        from common.audit.services import AuditService

        # Capture when password was last changed (if ever)
        # We can use date_joined as proxy for first password set, or look for previous password change logs
        last_password_change = None

        # Try to find the last password change from audit logs
        from common.audit.models import AuditLog

        try:
            last_change_log = (
                AuditLog.objects.filter(
                    user=request.user, action="UPDATE", metadata__type="password_change"
                )
                .order_by("-timestamp")
                .first()
            )

            if last_change_log and last_change_log.new_data:
                last_password_change = last_change_log.new_data.get("changed_at")
            else:
                # If no previous password change, use date_joined (account creation)
                last_password_change = (
                    request.user.date_joined.isoformat()
                    if request.user.date_joined
                    else None
                )
        except:
            # Fallback to date_joined if audit query fails
            last_password_change = (
                request.user.date_joined.isoformat()
                if request.user.date_joined
                else None
            )

        # Temporarily disable automatic audit for this save
        request.user.__audit__ = False
        request.user.set_password(new_password)
        request.user.save()
        # Re-enable audit for future operations
        request.user.__audit__ = True

        # Log password change with historical context
        AuditService.log_action(
            action="UPDATE",
            content_object=request.user,
            old_data={"action": "password_change", "changed_at": last_password_change},
            new_data={
                "action": "password_changed",
                "changed_at": timezone.now().isoformat(),
            },
            user=request.user,
            metadata={
                "type": "password_change",
                "ip": request.META.get("REMOTE_ADDR"),
            },
        )

        return Response({"message": "Password updated successfully."})


class AuthThrottleView(APIView):
    """
    Endpoint de teste para verificação de throttling.
    Usado para testes de rate limiting em desenvolvimento.
    """

    serializer_class = AuthThrottleSerializer
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    @extend_schema(
        tags=["Autenticação"],
        summary="Teste de throttling",
        description="""
        Endpoint de teste para verificar o funcionamento do rate limiting.
        
        **Uso em desenvolvimento:**
        - Testar configurações de throttling
        - Verificar limites de taxa
        - Debug de políticas de rate limiting
        
        **Throttling aplicado:**
        - AnonRateThrottle: Para usuários não autenticados
        - UserRateThrottle: Para usuários autenticados
        """,
        responses={
            200: OpenApiResponse(
                description="Throttling funcionando corretamente",
                examples=[
                    OpenApiExample(
                        "Resposta de teste",
                        value={"message": "Throttling applied to this endpoint."},
                    )
                ],
            ),
            429: ERROR_RESPONSES[429],
        },
    )
    def get(self, request):
        return Response({"message": "Throttling applied to this endpoint."})


class TOTPEnrollView(APIView):
    """
    Endpoint para inscrição em autenticação de dois fatores (2FA) TOTP.
    Permite que usuários configurem autenticação adicional via aplicativos como Google Authenticator.
    """

    serializer_class = TOTPEnrollSerializer
    permission_classes = [IsEmployeeOrAdmin]  # Employee or Admin can enroll TOTP
    throttle_classes = [SensitiveActionThrottle]  # Sensitive action throttling

    @extend_schema(
        tags=["Autenticação"],
        summary="Inscrição em 2FA TOTP",
        description="""
        Configura autenticação de dois fatores (2FA) baseada em TOTP para o usuário.
        
        **Funcionalidades:**
        - Geração de chave secreta TOTP
        - QR Code para configuração em apps
        - Validação de códigos de teste
        
        **Apps compatíveis:**
        - Google Authenticator
        - Microsoft Authenticator
        - Authy
        - Outros apps TOTP padrão
        
        **Segurança:**
        - Throttling para ações sensíveis
        - Chaves únicas por usuário
        - Backup codes opcionais
        """,
        request=TOTPEnrollSerializer,
        responses={
            201: OpenApiResponse(
                description="2FA configurado com sucesso",
                examples=[
                    OpenApiExample(
                        "Configuração TOTP",
                        value={
                            "message": "TOTP configurado com sucesso",
                            "secret_key": "JBSWY3DPEHPK3PXP",
                            "qr_code_url": "otpauth://totp/MieleSystem:user@exemplo.com?secret=JBSWY3DPEHPK3PXP&issuer=MieleSystem",
                        },
                    )
                ],
            ),
            400: ERROR_RESPONSES[400],
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
            429: ERROR_RESPONSES[429],
        },
    )
    def post(self, request):
        user = request.user
        key = random_hex(20)
        totp = TOTP(key, step=30, digits=6)
        totp.time = totp.time()

        TOTPDevice.objects.create(
            user=user,
            key=key,
            step=30,
            digits=6,
            tolerance=1,
            drift=0,
        )

        return Response(
            {
                "message": "TOTP device enrolled successfully.",
                "key": key,
            }
        )


class UserRegistrationView(APIView):
    """
    Endpoint para registro de novos usuários no sistema.
    Aplica throttling restritivo e requer aprovação administrativa.
    """

    serializer_class = UserRegistrationSerializer
    throttle_classes = [AuthRegisterThrottle]  # Restrictive throttling for registration

    @extend_schema(
        tags=["Autenticação"],
        summary="Registro de novo usuário",
        description="""
        Registra um novo usuário no sistema. O usuário ficará com status "pendente" até aprovação administrativa.
        
        **Processo de registro:**
        1. Validação dos dados de entrada
        2. Verificação de unicidade (username/email)
        3. Criação da conta com status "pending"
        4. Notificação para aprovação administrativa
        
        **Validações aplicadas:**
        - Username único
        - Email único e válido
        - Senha forte (política definida)
        - Confirmação de senha
        - Throttling contra spam
        
        **Status pós-registro:**
        - approval_status: "pending"
        - is_active: False (até aprovação)
        - role: "guest" (padrão)
        """,
        request=UserRegistrationSerializer,
        responses={
            201: SUCCESS_RESPONSES["registration_success"],
            400: OpenApiResponse(
                description="Dados de registro inválidos",
                examples=[
                    OpenApiExample(
                        "Username já existe",
                        value={
                            "error": {
                                "code": "validation_error",
                                "message": "Dados de entrada inválidos",
                                "details": {
                                    "username": ["Um usuário com este nome já existe."]
                                },
                            }
                        },
                    ),
                    OpenApiExample(
                        "Email já existe",
                        value={
                            "error": {
                                "code": "validation_error",
                                "message": "Dados de entrada inválidos",
                                "details": {
                                    "email": ["Um usuário com este email já existe."]
                                },
                            }
                        },
                    ),
                    OpenApiExample(
                        "Senhas não coincidem",
                        value={
                            "error": {
                                "code": "validation_error",
                                "message": "Dados de entrada inválidos",
                                "details": {
                                    "confirm_password": ["As senhas não coincidem."]
                                },
                            }
                        },
                    ),
                ],
            ),
            429: ERROR_RESPONSES[429],
            500: ERROR_RESPONSES[500],
        },
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "User registered successfully.",
                "username": user.username,
                "email": user.email,
                "approval_status": user.approval_status,
            },
            status=status.HTTP_201_CREATED,
        )


class UserDeactivateView(APIView):
    permission_classes = [
        IsOwnerOrAdmin
    ]  # Users can deactivate own account, admins can deactivate any

    @extend_schema(
        tags=["Usuários"],
        request=UserDeleteSerializer,
        responses={
            200: OpenApiResponse(description="User account deactivated successfully"),
            400: OpenApiResponse(description="Invalid password or bad request"),
        },
        description="Deactivate the authenticated user's account (soft delete)",
        summary="Deactivate user account",
    )
    def patch(self, request):
        serializer = UserDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        password = serializer.validated_data["password"]
        user = request.user

        if not user.check_password(password):
            raise InvalidPasswordError()

        # Capture old data for audit logging
        from common.audit.services import AuditService

        old_data = {
            "is_active": user.is_active,
            "deleted_at": user.deleted_at,
        }

        # Temporarily disable automatic audit for this save
        user.__audit__ = False
        user.is_active = False
        user.deleted_at = timezone.now()
        user.save()
        # Re-enable audit for future operations
        user.__audit__ = True

        # Log account deactivation
        # Use log_action directly to control both old_data and new_data
        new_data = {
            "is_active": user.is_active,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        }

        AuditService.log_action(
            action=AuditLog.AuditAction.UPDATE,
            content_object=user,
            old_data=old_data,
            new_data=new_data,
            user=user,
            metadata={
                "type": "account_deactivation",
                "ip": request.META.get("REMOTE_ADDR"),
                "self_initiated": True,
            },
        )

        return Response(
            {"message": "User account deactivated successfully"},
            status=status.HTTP_200_OK,
        )


class EmailChangeRequestView(APIView):
    permission_classes = [
        IsEmployeeOrAdmin
    ]  # Employee or Admin can request email changes
    throttle_classes = [SensitiveActionThrottle]  # Sensitive action throttling

    @extend_schema(
        tags=["Usuários"],
        request=EmailChangeRequestSerializer,
        responses={
            201: OpenApiResponse(
                description="Email change request created successfully"
            ),
            400: OpenApiResponse(description="Invalid data"),
        },
        description="Request an email change (requires admin approval)",
        summary="Request email change",
    )
    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_email = serializer.validated_data["new_email"]
        justification = serializer.validated_data["justification"]

        # Create the change request
        change_request = SensibleDataChangeRequest.objects.create(
            user=request.user,
            request_type=SensibleDataChangeRequest.RequestType.EMAIL_CHANGE,
            requested_changes={"new_email": new_email},
            justification=justification,
        )

        return Response(
            {
                "message": "Email change request submitted successfully",
                "request_id": change_request.id,
                "status": change_request.status,
            },
            status=status.HTTP_201_CREATED,
        )


class SensibleDataChangeRequestListView(APIView):
    """
    Endpoint administrativo para listar todas as solicitações de alteração de dados sensíveis.
    Apenas administradores podem acessar este endpoint.
    """

    permission_classes = [IsAdmin]  # Only admins can view all change requests
    serializer_class = SensibleDataChangeRequestSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Listar todas as solicitações de alteração (Admin)",
        description="""
        Lista todas as solicitações de alteração de dados sensíveis no sistema.
        
        **Acesso:** Apenas administradores
        
        **Tipos de solicitações:**
        - Alteração de email
        - Alteração de dados pessoais sensíveis
        - Outras mudanças que requerem aprovação
        
        **Status possíveis:**
        - pending: Aguardando revisão
        - approved: Aprovada e aplicada
        - rejected: Rejeitada pelo admin
        
        **Informações retornadas:**
        - ID da solicitação
        - Usuário solicitante
        - Tipo de alteração
        - Dados antigos vs novos
        - Status atual
        - Timestamps de criação/revisão
        - Justificativa (se rejeitada)
        """,
        responses={
            200: OpenApiResponse(
                description="Lista de todas as solicitações de alteração",
                examples=[
                    OpenApiExample(
                        "Lista de solicitações",
                        value=[
                            {
                                "id": "uuid-solicitacao-1",
                                "user": "usuario1@exemplo.com",
                                "request_type": "email_change",
                                "old_data": {"email": "antigo@exemplo.com"},
                                "new_data": {"email": "novo@exemplo.com"},
                                "status": "pending",
                                "created_at": "2025-01-15T10:30:00Z",
                                "reviewed_at": None,
                                "justification": None,
                            },
                            {
                                "id": "uuid-solicitacao-2",
                                "user": "usuario2@exemplo.com",
                                "request_type": "profile_change",
                                "old_data": {"first_name": "João"},
                                "new_data": {"first_name": "João Carlos"},
                                "status": "approved",
                                "created_at": "2025-01-14T14:15:00Z",
                                "reviewed_at": "2025-01-14T16:20:00Z",
                                "justification": None,
                            },
                        ],
                    )
                ],
            ),
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
            500: ERROR_RESPONSES[500],
        },
    )
    def get(self, request):
        # Admins can see all requests
        requests = SensibleDataChangeRequest.objects.all()
        serializer = SensibleDataChangeRequestSerializer(requests, many=True)
        return Response(serializer.data)


class MyChangeRequestsView(APIView):
    """
    Endpoint para usuários visualizarem suas próprias solicitações de alteração.
    Employees e admins podem acessar suas solicitações.
    """

    permission_classes = [IsEmployeeOrAdmin]  # Employees can view their own requests
    serializer_class = SensibleDataChangeRequestSerializer

    @extend_schema(
        tags=["Usuários"],
        summary="Listar minhas solicitações de alteração",
        description="""
        Lista as solicitações de alteração de dados sensíveis do usuário autenticado.
        
        **Acesso:** Employees e Admins
        
        **Funcionalidade:**
        - Usuários veem apenas suas próprias solicitações
        - Histórico completo de solicitações
        - Status atual de cada solicitação
        
        **Casos de uso:**
        - Acompanhar status de alteração de email
        - Verificar histórico de mudanças solicitadas
        - Confirmar se solicitação foi processada
        
        **Informações retornadas:**
        - Apenas solicitações do usuário autenticado
        - Status atualizado
        - Justificativas (se rejeitada)
        - Timestamps relevantes
        """,
        responses={
            200: OpenApiResponse(
                description="Lista das solicitações do usuário",
                examples=[
                    OpenApiExample(
                        "Solicitações do usuário",
                        value=[
                            {
                                "id": "uuid-minha-solicitacao",
                                "request_type": "email_change",
                                "old_data": {"email": "meu.email.antigo@exemplo.com"},
                                "new_data": {"email": "meu.novo.email@exemplo.com"},
                                "status": "pending",
                                "created_at": "2025-01-15T11:00:00Z",
                                "reviewed_at": None,
                                "justification": None,
                            }
                        ],
                    )
                ],
            ),
            401: ERROR_RESPONSES[401],
            403: ERROR_RESPONSES[403],
            500: ERROR_RESPONSES[500],
        },
    )
    def get(self, request):
        # Users can only see their own requests
        requests = SensibleDataChangeRequest.objects.filter(user=request.user)
        serializer = SensibleDataChangeRequestSerializer(requests, many=True)
        return Response(serializer.data)


class ReviewChangeRequestView(APIView):
    permission_classes = [IsAdmin]  # Only admins can review requests

    @extend_schema(
        tags=["Admin"],
        request=ReviewChangeRequestSerializer,
        responses={
            200: OpenApiResponse(description="Request reviewed successfully"),
            404: OpenApiResponse(description="Request not found"),
        },
        description="Approve or reject a sensible data change request",
        summary="Review change request",
    )
    def patch(self, request, request_id):
        try:
            change_request = SensibleDataChangeRequest.objects.get(id=request_id)
        except SensibleDataChangeRequest.DoesNotExist:
            raise ChangeRequestNotFoundError()

        serializer = ReviewChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["review_action"]
        review_notes = serializer.validated_data.get("review_notes", "")

        # Import AuditService para uso em múltiplos pontos
        from common.audit.services import AuditService

        if action == "approve":
            change_request.status = SensibleDataChangeRequest.RequestStatus.APPROVED

            # Apply the changes if it's an email change
            if (
                change_request.request_type
                == SensibleDataChangeRequest.RequestType.EMAIL_CHANGE
            ):
                new_email = change_request.requested_changes.get("new_email")
                if new_email:
                    old_email = change_request.user.email
                    change_request.user.email = new_email

                    # Desabilitar auditoria temporariamente para evitar log automático
                    change_request.user.__audit__ = False
                    change_request.user.save()
                    # Reabilitar auditoria
                    change_request.user.__audit__ = True

                    # Log manual da aprovação de mudança de email pelo admin
                    # Use log_action directly to control both old_data and new_data
                    AuditService.log_action(
                        action=AuditLog.AuditAction.UPDATE,
                        content_object=change_request.user,
                        user=request.user,  # Admin que aprovou
                        old_data={"email": old_email},
                        new_data={"email": new_email},
                        metadata={
                            "change_request_id": str(change_request.id),
                            "approved_by_admin": request.user.email,
                            "original_user": change_request.user.email,
                            "justification": change_request.justification,
                        },
                    )

            # Apply other types of sensible data changes
            elif (
                change_request.request_type
                == SensibleDataChangeRequest.RequestType.ROLE_CHANGE
            ):
                new_role = change_request.requested_changes.get("new_role")
                if new_role:
                    old_role = change_request.user.role
                    change_request.user.role = new_role

                    # Desabilitar auditoria temporariamente para evitar log automático
                    change_request.user.__audit__ = False
                    change_request.user.save()
                    # Reabilitar auditoria
                    change_request.user.__audit__ = True

                    # Log manual da aprovação de mudança de role pelo admin
                    # Use log_action directly to control both old_data and new_data
                    AuditService.log_action(
                        action=AuditLog.AuditAction.UPDATE,
                        content_object=change_request.user,
                        user=request.user,  # Admin que aprovou
                        old_data={"role": old_role},
                        new_data={"role": new_role},
                        metadata={
                            "change_request_id": str(change_request.id),
                            "approved_by_admin": request.user.email,
                            "original_user": change_request.user.email,
                            "justification": change_request.justification,
                        },
                    )

            # Apply other profile changes
            elif (
                change_request.request_type
                == SensibleDataChangeRequest.RequestType.SENSITIVE_PROFILE_CHANGE
            ):
                requested_changes = change_request.requested_changes
                old_data = {}
                new_data = {}

                # Capturar dados antigos e aplicar novos
                for field, new_value in requested_changes.items():
                    if hasattr(change_request.user, field):
                        old_data[field] = getattr(change_request.user, field)
                        setattr(change_request.user, field, new_value)
                        new_data[field] = new_value

                if old_data and new_data:
                    # Desabilitar auditoria temporariamente para evitar log automático
                    change_request.user.__audit__ = False
                    change_request.user.save()
                    # Reabilitar auditoria
                    change_request.user.__audit__ = True

                    # Log manual da aprovação de mudanças de perfil pelo admin
                    # Use log_action directly to control both old_data and new_data
                    AuditService.log_action(
                        action=AuditLog.AuditAction.UPDATE,
                        content_object=change_request.user,
                        user=request.user,  # Admin que aprovou
                        old_data=old_data,
                        new_data=new_data,
                        metadata={
                            "change_request_id": str(change_request.id),
                            "approved_by_admin": request.user.email,
                            "original_user": change_request.user.email,
                            "justification": change_request.justification,
                        },
                    )
        else:
            change_request.status = SensibleDataChangeRequest.RequestStatus.REJECTED

        change_request.reviewed_by = request.user
        change_request.review_notes = review_notes
        change_request.reviewed_at = timezone.now()
        change_request.save()

        return Response(
            {
                "message": f"Request {action}d successfully",
                "status": change_request.status,
            }
        )
