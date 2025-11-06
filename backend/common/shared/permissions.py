from rest_framework import permissions
from common.permissions import IsAdminUser


class IsOwnerOrAdminForAnnotations(permissions.BasePermission):
    """
    Permissão personalizada para garantir que usuários só possam
    acessar/editar suas próprias anotações, exceto admins.
    """

    def has_permission(self, request, view):
        # Qualquer usuário autenticado pode listar/criar suas anotações
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Admins podem fazer tudo
        if IsAdminUser().has_permission(request, view):
            return True

        # Usuários só podem acessar suas próprias anotações
        return obj.user_id == request.user.id


class IsOwnerOrAdminForAttachedFiles(permissions.BasePermission):
    """
    Permissão personalizada para garantir que usuários só possam
    acessar/editar seus próprios arquivos, exceto admins.
    """

    def has_permission(self, request, view):
        # Qualquer usuário autenticado pode listar/criar seus arquivos
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Admins podem fazer tudo
        if IsAdminUser().has_permission(request, view):
            return True

        # Usuários só podem acessar seus próprios arquivos
        return obj.uploaded_by_id == request.user.id
