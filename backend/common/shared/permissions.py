from rest_framework import permissions
from common.permissions import IsAdminUser


class IsOwnerOrAdminForAnnotations(permissions.BasePermission):
    """
    Permissão personalizada para anotações:
    - Todos usuários autenticados podem ver todas as anotações
    - Apenas o dono ou admin pode editar/deletar anotações
    """

    def has_permission(self, request, view):
        # Qualquer usuário autenticado pode listar/criar anotações
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Admins podem fazer tudo
        if IsAdminUser().has_permission(request, view):
            return True

        # Para operações de leitura (GET, HEAD, OPTIONS), permitir acesso a todas as anotações
        if request.method in permissions.SAFE_METHODS:
            return True

        # Para operações de escrita (PUT, PATCH, DELETE), apenas o dono pode fazer
        return obj.user_id == request.user.id
