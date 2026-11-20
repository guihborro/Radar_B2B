"""Verificadores reais. NeverBounce vem implementado (API simples e estável);
ZeroBounce/Hunter ficam como stubs com o ponto exato de plugar.

Todos leem a chave do .env. Sem chave -> erro claro (nunca silenciosamente
deixa passar e-mail não validado).
"""
from __future__ import annotations

from .base import (
    STATUS_INVALID,
    STATUS_RISKY,
    STATUS_UNKNOWN,
    STATUS_VALID,
    EmailValidator,
    ValidationResult,
    sintaxe_ok,
)


class NeverBounceValidator(EmailValidator):
    """https://developers.neverbounce.com/ — endpoint /v4/single/check."""

    URL = "https://api.neverbounce.com/v4/single/check"

    def validate(self, email: str) -> ValidationResult:
        email = email.strip()
        if not sintaxe_ok(email):
            return ValidationResult(email, STATUS_INVALID, 0.0)
        chave = self.cfg.env("NEVERBOUNCE_API_KEY")
        if not chave:
            raise RuntimeError("Defina NEVERBOUNCE_API_KEY no .env.")
        import requests

        resp = requests.get(
            self.URL,
            params={"key": chave, "email": email},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        # a API responde HTTP 200 mesmo em erro (ex.: sem crédito) — cheque status
        if data.get("status") not in ("success", None):
            raise RuntimeError(f"NeverBounce: {data.get('message', data.get('status'))}")
        # NeverBounce: valid | invalid | disposable | catchall | unknown
        result = data.get("result", "unknown")
        mapa = {
            "valid": (STATUS_VALID, 0.95),
            "catchall": (STATUS_RISKY, 0.5),
            "unknown": (STATUS_UNKNOWN, 0.3),
            "disposable": (STATUS_INVALID, 0.1),
            "invalid": (STATUS_INVALID, 0.0),
        }
        status, score = mapa.get(result, (STATUS_UNKNOWN, 0.3))
        return ValidationResult(email, status, score)


class ZeroBounceValidator(EmailValidator):
    """https://www.zerobounce.net/docs/ — endpoint /v2/validate. 100 grátis/mês."""

    URL = "https://api.zerobounce.net/v2/validate"

    def validate(self, email: str) -> ValidationResult:
        email = email.strip()
        if not sintaxe_ok(email):
            return ValidationResult(email, STATUS_INVALID, 0.0)
        chave = self.cfg.env("ZEROBOUNCE_API_KEY")
        if not chave:
            raise RuntimeError("Defina ZEROBOUNCE_API_KEY no .env.")
        import requests

        resp = requests.get(
            self.URL,
            params={"api_key": chave, "email": email, "ip_address": ""},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"ZeroBounce: {data['error']}")
        # ZeroBounce: valid | invalid | catch-all | unknown | spamtrap | abuse | do_not_mail
        result = data.get("status", "unknown")
        mapa = {
            "valid": (STATUS_VALID, 0.95),
            "catch-all": (STATUS_RISKY, 0.5),
            "unknown": (STATUS_UNKNOWN, 0.3),
            "invalid": (STATUS_INVALID, 0.0),
            "spamtrap": (STATUS_INVALID, 0.0),
            "abuse": (STATUS_INVALID, 0.0),
            "do_not_mail": (STATUS_INVALID, 0.1),
        }
        status, score = mapa.get(result, (STATUS_UNKNOWN, 0.3))
        return ValidationResult(email, status, score)


class _StubValidator(EmailValidator):
    ENV_KEY = ""
    NOME = ""

    def validate(self, email: str) -> ValidationResult:
        if not self.cfg.env(self.ENV_KEY):
            raise RuntimeError(f"Defina {self.ENV_KEY} no .env.")
        raise NotImplementedError(
            f"{self.NOME} ainda não implementado. Use 'neverbounce'/'zerobounce' "
            f"ou implemente aqui a chamada à API."
        )


class HunterValidator(_StubValidator):
    ENV_KEY = "HUNTER_API_KEY"
    NOME = "Hunter"
