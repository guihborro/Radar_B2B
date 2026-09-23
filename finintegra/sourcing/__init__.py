"""Sourcing de empresas-alvo a partir do ICP.

Interface abstrata `SourcingProvider` para trocar de provedor sem reescrever o
pipeline (§4.1). `get_provider(cfg)` é a fábrica que lê config/config.yaml.
"""
from __future__ import annotations

from ..config import Config
from .base import ICPFilter, SourcingProvider
from .mock import MockProvider
from .csv_import import CSVProvider
from .receita import ReceitaFederalProvider
from .template_provider import TemplateProvider
from .providers import DataStoneProvider, EconodataProvider, SpeedioProvider

__all__ = ["ICPFilter", "SourcingProvider", "get_provider"]

_REGISTRY = {
    "mock": MockProvider,
    "csv": CSVProvider,
    "receita": ReceitaFederalProvider,   # gratuito, open data local
    "template": TemplateProvider,         # base para o próximo provedor
    "econodata": EconodataProvider,
    "speedio": SpeedioProvider,
    "datastone": DataStoneProvider,
}


def get_provider(cfg: Config) -> SourcingProvider:
    nome = cfg.get("ferramentas", "provedor_dados", default="mock")
    if nome not in _REGISTRY:
        raise ValueError(
            f"provedor_dados '{nome}' desconhecido. Opções: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[nome](cfg)
