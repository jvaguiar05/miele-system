from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.identity.permissions import IsEmployeeOrAdmin
from apps.perdcomps.models import PerDcomp
from .models import Client, ClientContract


def money(value):
    raw = str(value or "0").strip().replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except (InvalidOperation, TypeError):
        return Decimal("0")


def decimal_string(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ContractInput(serializers.Serializer):
    percentage = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0001"), max_value=Decimal("100"))
    starts_on = serializers.DateField()
    ends_on = serializers.DateField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    billing_evolution_requested = serializers.BooleanField(required=False)

    def validate(self, attrs):
        start = attrs.get("starts_on", getattr(self.instance, "starts_on", None))
        end = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if end and end < start:
            raise serializers.ValidationError({"ends_on": "O fim da vigência não pode ser anterior ao início."})
        client = self.context["client"]
        overlapping = ClientContract.objects.filter(client=client).filter(
            Q(ends_on__isnull=True) | Q(ends_on__gte=start),
            starts_on__lte=end or "9999-12-31",
        )
        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)
        if overlapping.exists():
            raise serializers.ValidationError("A vigência se sobrepõe a outro contrato deste cliente.")
        return attrs


def contract_data(contract, processes):
    applicable = [p for p in processes if p.data_transmissao >= contract.starts_on and (contract.ends_on is None or p.data_transmissao <= contract.ends_on)]
    rate = contract.percentage / Decimal("100")
    totals = {}
    for field, name in [("valor_pedido", "requested"), ("valor_compensado", "compensated"), ("valor_recebido", "received")]:
        base = sum((money(getattr(p, field)) for p in applicable), Decimal("0"))
        totals[name] = {"base": decimal_string(base), "calculated": decimal_string(base * rate)}
    return {
        "id": str(contract.public_id), "percentage": str(contract.percentage),
        "starts_on": contract.starts_on.isoformat(), "ends_on": contract.ends_on.isoformat() if contract.ends_on else None,
        "reference": contract.reference, "notes": contract.notes,
        "billing_evolution_requested": contract.billing_evolution_requested,
        "mode": "informational", "process_count": len(applicable), "totals": totals,
    }


def ensure_admin(request):
    return request.user.role == "admin"


@api_view(["GET", "POST"])
@permission_classes([IsEmployeeOrAdmin])
def client_contracts(request, client_id):
    client = get_object_or_404(Client, public_id=client_id, deleted_at__isnull=True)
    if request.method == "POST":
        if not ensure_admin(request):
            return Response({"detail": "Somente administradores podem alterar contratos."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ContractInput(data=request.data, context={"client": client})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            contract = ClientContract.objects.create(client=client, created_by=request.user, **serializer.validated_data)
        return Response(contract_data(contract, []), status=status.HTTP_201_CREATED)
    processes = list(PerDcomp.objects.filter(client_id=client.id, deleted_at__isnull=True, is_active=True))
    contracts = list(ClientContract.objects.filter(client=client))
    covered = {p.id for c in contracts for p in processes if p.data_transmissao >= c.starts_on and (c.ends_on is None or p.data_transmissao <= c.ends_on)}
    return Response({
        "client": {"id": str(client.public_id), "name": client.razao_social},
        "mode": "informational", "contracts": [contract_data(c, processes) for c in contracts],
        "uncovered_processes": len([p for p in processes if p.id not in covered]),
        "notice": "Simulação informativa; não gera honorários, cobrança ou obrigação financeira.",
    })


@api_view(["PATCH"])
@permission_classes([IsEmployeeOrAdmin])
def client_contract_detail(request, client_id, contract_id):
    if not ensure_admin(request):
        return Response({"detail": "Somente administradores podem alterar contratos."}, status=status.HTTP_403_FORBIDDEN)
    client = get_object_or_404(Client, public_id=client_id, deleted_at__isnull=True)
    contract = get_object_or_404(ClientContract, public_id=contract_id, client=client)
    serializer = ContractInput(contract, data=request.data, partial=True, context={"client": client})
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        for field, value in serializer.validated_data.items():
            setattr(contract, field, value)
        contract.save()
    processes = list(PerDcomp.objects.filter(client_id=client.id, deleted_at__isnull=True, is_active=True))
    return Response(contract_data(contract, processes))
