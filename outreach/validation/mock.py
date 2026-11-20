"""Validador MOCK — sem rede, determinístico. Default do config.

Heurística: sintaxe válida + e-mail "pessoal" (first.last) tende a 'valid';
genéricos (contato@, comercial@) viram 'risky'; sintaxe ruim -> 'invalid'.
Serve para exercitar a regra "só envia validado" sem gastar crédito.
NÃO substitui um verificador real antes de produção.
"""
from __future__ import annotations

import hashlib

from .base import (
    STATUS_INVALID,
    STATUS_RISKY,
    STATUS_VALID,
    EmailValidator,
    ValidationResult,
    sintaxe_ok,
)

_GENERICOS = {"contato", "comercial", "financeiro", "vendas", "sac", "info"}


class MockValidator(EmailValidator):
    def validate(self, email: str) -> ValidationResult:
        email = email.strip().lower()
        if not sintaxe_ok(email):
            return ValidationResult(email, STATUS_INVALID, 0.0)
        local = email.split("@", 1)[0]
        if local in _GENERICOS:
            return ValidationResult(email, STATUS_RISKY, 0.4)
        # pseudo-aleatório estável por e-mail: ~75% valid, ~25% invalid
        h = int(hashlib.md5(email.encode()).hexdigest(), 16) % 100
        if h < 75:
            return ValidationResult(email, STATUS_VALID, 0.8 + (h % 20) / 100)
        return ValidationResult(email, STATUS_INVALID, 0.2)
