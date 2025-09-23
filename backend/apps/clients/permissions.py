from rest_framework.permissions import BasePermission


class ClientPermissions(BasePermission):
    """
    Permissões personalizadas para clientes.
    """

    def has_permission(self, request, view):
        """
        Verificar permissões no nível da view.
        """
        if not request.user.is_authenticated:
            return False

        # Ações de leitura - qualquer usuário autenticado
        if view.action in ["list", "retrieve", "pending_approvals"]:
            return True

        # Ações de escrita - usuários com permissões específicas
        if view.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
            "activate",
            "deactivate",
            "soft_delete",
        ]:
            return request.user.has_perm("clients.change_client")

        return False

    def has_object_permission(self, request, view, obj):
        """
        Verificar permissões no nível do objeto.
        """
        # Para este exemplo, permitir acesso a todos os objetos
        # Em um sistema real, poderia haver regras mais específicas
        return self.has_permission(request, view)
