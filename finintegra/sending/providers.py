"""Stubs de ferramentas de cold email (Instantly/Smartlead/SendGrid).

Implementar a chamada à API mantendo a guarda de base.py (warmup, validado-only,
bounce). Antes de produção: domínio SEPARADO + aquecimento gradual (§9).
"""
from __future__ import annotations

from .base import EmailSender, SendResult
from ..storage.models import Lead


class _StubSender(EmailSender):
    ENV_KEY = ""
    NOME = ""

    def _do_send(self, lead: Lead) -> SendResult:
        if not self.cfg.env(self.ENV_KEY):
            raise RuntimeError(f"Defina {self.ENV_KEY} no .env.")
        raise NotImplementedError(
            f"Envio via {self.NOME} ainda não implementado.\n"
            f"Plugue aqui a API e garanta: domínio de outbound separado, warmup "
            f"gradual e monitoramento de bounce (bounce_rate_max no config)."
        )


class InstantlySender(_StubSender):
    ENV_KEY = "INSTANTLY_API_KEY"
    NOME = "Instantly"


class SmartleadSender(_StubSender):
    ENV_KEY = "SMARTLEAD_API_KEY"
    NOME = "Smartlead"


class SendGridSender(_StubSender):
    ENV_KEY = "SENDGRID_API_KEY"
    NOME = "SendGrid"
