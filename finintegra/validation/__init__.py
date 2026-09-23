"""Validação de e-mail. NUNCA enviar para e-mail não validado (§9)."""
from __future__ import annotations

from ..config import Config
from .base import EmailValidator, ValidationResult
from .mock import MockValidator
from .providers import HunterValidator, NeverBounceValidator, ZeroBounceValidator

__all__ = ["EmailValidator", "ValidationResult", "get_validator"]

_REGISTRY = {
    "mock": MockValidator,
    "neverbounce": NeverBounceValidator,
    "zerobounce": ZeroBounceValidator,
    "hunter": HunterValidator,
}


def get_validator(cfg: Config) -> EmailValidator:
    nome = cfg.get("ferramentas", "verificador_email", default="mock")
    if nome not in _REGISTRY:
        raise ValueError(
            f"verificador_email '{nome}' desconhecido. Opções: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[nome](cfg)
