import logging
import re
from typing import Any, Iterable

from django.conf import settings
from rest_framework.exceptions import ValidationError
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BRASILAPI_CNPJ_BASE_URL = getattr(
    settings,
    "BRASILAPI_CNPJ_BASE_URL",
    "https://brasilapi.com.br/api/cnpj/v1",
)
BRASILAPI_TIMEOUT = getattr(settings, "BRASILAPI_TIMEOUT", 10)


def _normalize_cnpj(cnpj: str) -> str:
    return re.sub(r"[^\d]", "", str(cnpj or ""))


def _normalize_cep(cep: str) -> str:
    cep_digits = re.sub(r"[^\d]", "", str(cep or ""))
    if len(cep_digits) == 8:
        return f"{cep_digits[:5]}-{cep_digits[5:]}"
    return cep


def _requests_session() -> requests.Session:
    retry_strategy = Retry(
        total=2,
        connect=1,
        read=1,
        status=1,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_cnpj_data(cnpj: str) -> dict[str, Any]:
    cnpj_digits = _normalize_cnpj(cnpj)
    if len(cnpj_digits) != 14:
        raise ValidationError(
            {"cnpj": "CNPJ inválido para consulta BrasilAPI. Use 14 dígitos."}
        )

    url = f"{BRASILAPI_CNPJ_BASE_URL}/{cnpj_digits}"
    try:
        response = _requests_session().get(url, timeout=BRASILAPI_TIMEOUT)
    except RequestException as exc:
        logger.exception("Erro ao consultar BrasilAPI para CNPJ %s", cnpj_digits)
        raise ValidationError(
            {
                "cnpj": (
                    "Não foi possível consultar os dados do CNPJ. "
                    "Verifique a conexão e tente novamente."
                )
            }
        ) from exc

    if response.status_code == 404:
        raise ValidationError({"cnpj": "CNPJ não encontrado na BrasilAPI."})
    if response.status_code != 200:
        logger.error(
            "BrasilAPI retornou status %s para CNPJ %s", response.status_code, cnpj_digits
        )
        raise ValidationError(
            {
                "cnpj": (
                    "Falha ao consultar o CNPJ. "
                    "O serviço externo retornou um erro."
                )
            }
        )

    try:
        return response.json()
    except ValueError as exc:
        logger.exception("Resposta inválida da BrasilAPI para CNPJ %s", cnpj_digits)
        raise ValidationError(
            {"cnpj": "Resposta inválida ao consultar o serviço de CNPJ."}
        ) from exc


def _normalize_activity(activity: Any) -> dict[str, str]:
    if isinstance(activity, dict):
        return {
            "cnae": str(
                activity.get("cnae")
                or activity.get("code")
                or activity.get("codigo")
                or activity.get("cnae_fiscal")
                or ""
            ).strip(),
            "descricao": str(
                activity.get("text")
                or activity.get("descricao")
                or activity.get("cnae_fiscal_descricao")
                or ""
            ).strip(),
        }

    return {"cnae": "", "descricao": ""}


def _activities_from_api(data: dict[str, Any]) -> list[dict[str, str]]:
    activities: list[dict[str, str]] = []
    primary = data.get("atividade_principal") or {}
    if not primary and data.get("cnae_fiscal"):
        primary = {
            "cnae": data.get("cnae_fiscal"),
            "descricao": data.get("cnae_fiscal_descricao"),
        }
    if primary:
        if isinstance(primary, list):
            activities.extend(_normalize_activity(item) for item in primary)
        else:
            activities.append(_normalize_activity(primary))

    secondary = data.get("atividades_secundarias") or data.get("cnaes_secundarios") or []
    if isinstance(secondary, list):
        activities.extend(_normalize_activity(item) for item in secondary)

    return [activity for activity in activities if activity.get("cnae") or activity.get("descricao")]


def _should_fetch_data(validated_data: dict[str, Any]) -> bool:
    fields_to_fill = [
        "razao_social",
        "nome_fantasia",
        "tipo_empresa",
        "atividades",
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "municipio",
        "uf",
        "cep",
    ]
    return any(not validated_data.get(field) for field in fields_to_fill)


def enrich_client_data_with_cnpj(validated_data: dict[str, Any]) -> dict[str, Any]:
    if not validated_data.get("cnpj"):
        return validated_data

    if not _should_fetch_data(validated_data):
        return validated_data

    api_data = fetch_cnpj_data(validated_data["cnpj"])

    if not validated_data.get("razao_social") and api_data.get("razao_social"):
        validated_data["razao_social"] = api_data["razao_social"]
    elif not validated_data.get("razao_social") and api_data.get("nome"):
        validated_data["razao_social"] = api_data["nome"]

    if not validated_data.get("nome_fantasia") and api_data.get("nome_fantasia"):
        validated_data["nome_fantasia"] = api_data["nome_fantasia"]
    elif not validated_data.get("nome_fantasia") and api_data.get("fantasia"):
        validated_data["nome_fantasia"] = api_data["fantasia"]

    if not validated_data.get("tipo_empresa"):
        validated_data["tipo_empresa"] = api_data.get("tipo") or api_data.get("natureza_juridica")

    if not validated_data.get("atividades"):
        activities = _activities_from_api(api_data)
        if activities:
            validated_data["atividades"] = activities

    address_fields = [
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "municipio",
        "uf",
        "cep",
    ]
    for field in address_fields:
        api_value = api_data.get(field)
        if api_value and not validated_data.get(field):
            validated_data[field] = _normalize_cep(api_value) if field == "cep" else api_value

    return validated_data


def lookup_cnpj_data(cnpj: str) -> dict[str, Any]:
    """
    Busca dados de CNPJ na BrasilAPI e retorna formatado para o frontend.
    
    Args:
        cnpj: CNPJ a buscar (com ou sem formatação)
    
    Returns:
        Dicionário com dados do CNPJ formatados para o frontend
        
    Raises:
        ValidationError: Se o CNPJ for inválido ou não encontrado
    """
    api_data = fetch_cnpj_data(cnpj)
    
    # Mapear dados da API para campos do frontend
    activities = _activities_from_api(api_data)
    
    # Mapear dados de sócios - filtrar os com dados válidos
    qsa = []
    if api_data.get("qsa"):
        qsa = [
            {
                "nome": (socio.get("nome") or socio.get("nome_socio") or "").strip(),
                "cargo": (socio.get("qual") or socio.get("qualificacao_socio") or "").strip(),
            }
            for socio in api_data.get("qsa", [])
            if (socio.get("nome") or socio.get("nome_socio") or "").strip() or (
                socio.get("qual") or socio.get("qualificacao_socio") or ""
            ).strip()
        ]
    
    nome = api_data.get("nome") or api_data.get("razao_social")
    fantasia = api_data.get("fantasia") or api_data.get("nome_fantasia")
    telefone = api_data.get("telefone") or api_data.get("ddd_telefone_1")
    tipo_empresa = api_data.get("tipo") or api_data.get("natureza_juridica")
    primary_activity = activities[0] if activities else None

    return {
        "nome": nome,
        "razao_social": api_data.get("razao_social") or nome,
        "fantasia": fantasia,
        "nome_fantasia": api_data.get("nome_fantasia") or fantasia,
        "email": api_data.get("email"),
        "telefone": str(telefone) if telefone else None,
        "natureza_juridica": api_data.get("natureza_juridica"),
        "tipo_empresa": tipo_empresa,
        "logradouro": api_data.get("logradouro"),
        "numero": api_data.get("numero"),
        "complemento": api_data.get("complemento"),
        "bairro": api_data.get("bairro"),
        "municipio": api_data.get("municipio"),
        "uf": api_data.get("uf"),
        "cep": api_data.get("cep"),
        "atividade_principal": primary_activity,
        "atividades_secundarias": api_data.get("atividades_secundarias") or api_data.get("cnaes_secundarios"),
        "atividades": activities,
        "qsa": qsa,
        "ultima_atualizacao": api_data.get("ultima_atualizacao"),
    }
