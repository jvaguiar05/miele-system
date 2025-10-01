from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """
    Permite acesso apenas para usuários admin.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class IsOwnerOrAdmin(BasePermission):
    """
    Permite acesso apenas para o dono do objeto ou admin.
    """
    def has_object_permission(self, request, view, obj):
        # Admin pode tudo
        if request.user.is_staff:
            return True
        
        # Verificar se é o dono (dependendo do modelo)
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        
        return False