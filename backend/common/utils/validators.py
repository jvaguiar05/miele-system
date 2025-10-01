import re
from typing import Any, Optional
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


def validate_cnpj(value: str) -> None:
    """
    Valida CNPJ brasileiro.

    Args:
        value: CNPJ para validar

    Raises:
        ValidationError: Se CNPJ inválido
    """
    # Remove formatação
    cnpj = re.sub(r"[^0-9]", "", str(value))

    # Verifica se tem 14 dígitos
    if len(cnpj) != 14:
        raise ValidationError(_("CNPJ deve ter 14 dígitos"))

    # Verifica se não são todos iguais
    if cnpj == cnpj[0] * 14:
        raise ValidationError(_("CNPJ inválido"))

    # Cálculo dos dígitos verificadores
    def calc_digit(cnpj_partial: str, weights: list) -> int:
        sum_result = sum(
            int(digit) * weight for digit, weight in zip(cnpj_partial, weights)
        )
        remainder = sum_result % 11
        return 0 if remainder < 2 else 11 - remainder

    # Primeiro dígito
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digit1 = calc_digit(cnpj[:12], weights1)

    # Segundo dígito
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digit2 = calc_digit(cnpj[:13], weights2)

    # Verifica dígitos
    if int(cnpj[12]) != digit1 or int(cnpj[13]) != digit2:
        raise ValidationError(_("CNPJ inválido"))


def validate_cpf(value: str) -> None:
    """
    Valida CPF brasileiro.

    Args:
        value: CPF para validar

    Raises:
        ValidationError: Se CPF inválido
    """
    # Remove formatação
    cpf = re.sub(r"[^0-9]", "", str(value))

    # Verifica se tem 11 dígitos
    if len(cpf) != 11:
        raise ValidationError(_("CPF deve ter 11 dígitos"))

    # Verifica se não são todos iguais
    if cpf == cpf[0] * 11:
        raise ValidationError(_("CPF inválido"))

    # Cálculo dos dígitos verificadores
    def calc_digit(cpf_partial: str, weights: list) -> int:
        sum_result = sum(
            int(digit) * weight for digit, weight in zip(cpf_partial, weights)
        )
        remainder = sum_result % 11
        return 0 if remainder < 2 else 11 - remainder

    # Primeiro dígito
    weights1 = list(range(10, 1, -1))
    digit1 = calc_digit(cpf[:9], weights1)

    # Segundo dígito
    weights2 = list(range(11, 1, -1))
    digit2 = calc_digit(cpf[:10], weights2)

    # Verifica dígitos
    if int(cpf[9]) != digit1 or int(cpf[10]) != digit2:
        raise ValidationError(_("CPF inválido"))


def validate_phone(value: str) -> None:
    """
    Valida telefone brasileiro.

    Args:
        value: Telefone para validar

    Raises:
        ValidationError: Se telefone inválido
    """
    # Remove formatação
    phone = re.sub(r"[^0-9]", "", str(value))

    # Verifica se tem 10 ou 11 dígitos (com DDD)
    if len(phone) not in [10, 11]:
        raise ValidationError(_("Telefone deve ter 10 ou 11 dígitos (com DDD)"))

    # Verifica se o DDD é válido (11 a 99)
    ddd = int(phone[:2])
    if ddd < 11 or ddd > 99:
        raise ValidationError(_("DDD inválido"))


def validate_cep(value: str) -> None:
    """
    Valida CEP brasileiro.

    Args:
        value: CEP para validar

    Raises:
        ValidationError: Se CEP inválido
    """
    # Remove formatação
    cep = re.sub(r"[^0-9]", "", str(value))

    # Verifica se tem 8 dígitos
    if len(cep) != 8:
        raise ValidationError(_("CEP deve ter 8 dígitos"))

    # Verifica se não é sequência inválida
    if cep == "00000000":
        raise ValidationError(_("CEP inválido"))


# Validadores para uso em modelos
cnpj_validator = RegexValidator(
    regex=r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$|^\d{14}$",
    message=_("CNPJ deve estar no formato XX.XXX.XXX/XXXX-XX ou XXXXXXXXXXXXXX"),
)

cpf_validator = RegexValidator(
    regex=r"^\d{3}\.\d{3}\.\d{3}-\d{2}$|^\d{11}$",
    message=_("CPF deve estar no formato XXX.XXX.XXX-XX ou XXXXXXXXXXX"),
)

phone_validator = RegexValidator(
    regex=r"^\(\d{2}\)\s\d{4,5}-\d{4}$|^\d{10,11}$",
    message=_("Telefone deve estar no formato (XX) XXXXX-XXXX ou XXXXXXXXXXX"),
)

cep_validator = RegexValidator(
    regex=r"^\d{5}-\d{3}$|^\d{8}$",
    message=_("CEP deve estar no formato XXXXX-XXX ou XXXXXXXX"),
)
