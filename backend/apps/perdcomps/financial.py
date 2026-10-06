"""Small, deterministic monetary rules shared by forms and imports."""
from decimal import Decimal, InvalidOperation


def money(value, *, empty=Decimal("0")):
    if value is None or str(value).strip() == "":
        return empty
    raw = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Valor monetário inválido.") from exc


def operational_balance(requested, compensated, received):
    """Business rule: requested - (compensated + received)."""
    result = money(requested) - money(compensated) - money(received)
    if result < 0:
        raise ValueError("Compensado + recebido não pode superar o valor pedido.")
    return f"{result:.2f}"
