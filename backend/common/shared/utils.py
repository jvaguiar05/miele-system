from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist


def resolve_entity(public_id):
    """
    Tenta encontrar a entidade pelo UUID em Clients ou Perdcomps.
    Retorna: (instancia_entidade, string_tipo)

    Usa apps.get_model para evitar Circular Imports, já que este utilitário
    reside em 'shared' e é usado por models/serializers.
    """

    # 1. Tenta Cliente
    try:
        # Carrega o model dinamicamente apenas na hora da execução
        Client = apps.get_model("clients", "Client")
        client = Client.objects.get(public_id=public_id)
        return client, "client"
    except (LookupError, ObjectDoesNotExist):
        # LookupError acontece se o app 'clients' não estiver instalado/carregado
        pass

    # 2. Tenta Perdcomp
    try:
        PerDcomp = apps.get_model("perdcomps", "PerDcomp")
        perdcomp = PerDcomp.objects.get(public_id=public_id)
        return perdcomp, "perdcomp"
    except (LookupError, ObjectDoesNotExist):
        pass

    return None, None
