"""
Exemplos de uso do sistema de auditoria e aprovações.

Este arquivo demonstra como usar o sistema de auditoria e aprovações
implementado no Dia 3 do plano de desenvolvimento.
"""

from django.contrib.auth import get_user_model
from common.utils import ApprovalHelper
from common.approvals.models import ApprovalRequest
from common.approvals.services import ApprovalService
from common.audit.services import AuditService

User = get_user_model()


def exemplo_workflow_completo():
    """
    Exemplo de workflow completo: criação de request → aprovação → execução → auditoria
    """

    # 1. Obter usuários (em cenário real, seriam obtidos via request)
    usuario_solicitante = User.objects.filter(role="employee").first()
    admin_aprovador = User.objects.filter(role="admin").first()
    usuario_alvo = User.objects.filter(is_active=False).first()

    if not all([usuario_solicitante, admin_aprovador, usuario_alvo]):
        print("Usuários necessários não encontrados")
        return

    print("=== WORKFLOW COMPLETO DE APROVAÇÃO ===")

    # 2. Criar solicitação de aprovação usando helper
    approval_request = ApprovalHelper.request_user_activation(
        user_id=str(usuario_alvo.pk),
        requested_by=usuario_solicitante,
        reason="Usuário precisa acessar o sistema para novo projeto",
    )

    print(f"✓ Solicitação criada: {approval_request.subject}")
    print(f"  Status: {approval_request.get_status_display()}")
    print(f"  ID: {approval_request.id}")

    # 3. Simular aprovação pelo admin
    success = ApprovalService.approve_request(
        approval_request=approval_request,
        approved_by=admin_aprovador,
        notes="Aprovado após verificação da necessidade do projeto.",
    )

    if success:
        print(f"✓ Solicitação aprovada e executada")
        approval_request.refresh_from_db()
        print(f"  Novo status: {approval_request.get_status_display()}")
        print(f"  Executado em: {approval_request.executed_at}")

        # 4. Verificar se o usuário foi ativado
        usuario_alvo.refresh_from_db()
        print(f"  Usuário ativo: {usuario_alvo.is_active}")
    else:
        print("✗ Erro ao processar aprovação")


def exemplo_auditoria_manual():
    """
    Exemplo de uso manual do sistema de auditoria
    """
    print("\n=== AUDITORIA MANUAL ===")

    # Obter um usuário para exemplo
    user = User.objects.first()
    if not user:
        print("Nenhum usuário encontrado")
        return

    # 1. Log manual de uma ação personalizada
    audit_log = AuditService.log_action(
        action="CUSTOM_ACTION",
        content_object=user,
        metadata={
            "type": "manual_example",
            "description": "Exemplo de log manual",
            "custom_field": "valor_personalizado",
        },
    )

    print(f"✓ Log de auditoria criado: {audit_log.id}")
    print(f"  Ação: {audit_log.action}")
    print(f"  Recurso: {audit_log.resource_type}")
    print(f"  Correlation ID: {audit_log.correlation_id}")


def exemplo_approval_personalizada():
    """
    Exemplo de criação de aprovação personalizada
    """
    print("\n=== APROVAÇÃO PERSONALIZADA ===")

    # Obter usuários
    solicitante = User.objects.filter(role="employee").first()
    if not solicitante:
        print("Usuário solicitante não encontrado")
        return

    # Criar aprovação personalizada para mudança de configuração
    approval_request = ApprovalHelper.request_custom_action(
        subject="Alterar configuração crítica do sistema",
        resource_type="core.Configuration",
        resource_id="system_config",
        payload_diff={
            "old_data": {"max_login_attempts": 3},
            "new_data": {"max_login_attempts": 5},
        },
        requested_by=solicitante,
        reason="Muitos usuários estão sendo bloqueados com 3 tentativas",
        metadata={
            "type": "configuration_change",
            "impact": "medium",
            "affected_users": "all",
        },
    )

    print(f"✓ Aprovação personalizada criada: {approval_request.subject}")
    print(f"  ID: {approval_request.id}")
    print(f"  Tipo de recurso: {approval_request.resource_type}")


def exemplo_consulta_auditorias():
    """
    Exemplo de consulta aos logs de auditoria
    """
    print("\n=== CONSULTA DE AUDITORIAS ===")

    # Importar o modelo aqui para evitar problemas de importação
    from common.audit.models import AuditLog

    # Últimas 5 ações
    recent_logs = AuditLog.objects.all()[:5]

    print("📋 Últimas 5 ações auditadas:")
    for log in recent_logs:
        print(f"  • {log.action} em {log.resource_type} por {log.user}")
        print(f"    {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    # Ações de um usuário específico
    user = User.objects.first()
    if user:
        user_logs = AuditLog.objects.filter(user=user)[:3]
        print(f"\n👤 Últimas ações do usuário {user.username}:")
        for log in user_logs:
            print(f"  • {log.action} em {log.resource_type}")


def exemplo_consulta_approvals():
    """
    Exemplo de consulta às solicitações de aprovação
    """
    print("\n=== CONSULTA DE APROVAÇÕES ===")

    # Aprovações pendentes
    pending = ApprovalRequest.objects.filter(status=ApprovalRequest.Status.PENDING)
    print(f"📋 Aprovações pendentes: {pending.count()}")

    for approval in pending[:3]:
        print(f"  • {approval.subject}")
        print(f"    Solicitado por: {approval.requested_by.username}")
        print(f"    Em: {approval.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

    # Estatísticas
    total = ApprovalRequest.objects.count()
    approved = ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.APPROVED
    ).count()
    executed = ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.EXECUTED
    ).count()
    rejected = ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.REJECTED
    ).count()

    print(f"\n📊 Estatísticas:")
    print(f"  Total: {total}")
    print(f"  Aprovadas: {approved}")
    print(f"  Executadas: {executed}")
    print(f"  Rejeitadas: {rejected}")


if __name__ == "__main__":
    """
    Para executar estes exemplos, use o shell do Django:

    python manage.py shell
    >>> from docs.examples.audit_approval_examples import *
    >>> exemplo_workflow_completo()
    >>> exemplo_auditoria_manual()
    >>> exemplo_approval_personalizada()
    >>> exemplo_consulta_auditorias()
    >>> exemplo_consulta_approvals()
    """
    pass
