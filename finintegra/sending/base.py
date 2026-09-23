"""Contrato de um remetente de e-mail + guarda de compliance/deliverability."""
from __future__ import annotations

import abc
from dataclasses import dataclass

from ..config import Config
from ..storage.models import Lead


@dataclass
class SendResult:
    enviado: bool
    canal: str = "email"
    detalhe: str = ""


class EmailSender(abc.ABC):
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def email_teste(self) -> str:
        return str(self.cfg.get("operacao", "email_teste", default="") or "").strip()

    def modo_teste(self) -> bool:
        return bool(self.email_teste())

    def destino(self, lead: Lead) -> str:
        """E-mail de teste (se configurado) tem prioridade sobre o e-mail do lead."""
        return self.email_teste() or lead.contato.email

    def pode_enviar(self, lead: Lead) -> tuple[bool, str]:
        """Guarda obrigatória antes de QUALQUER envio (§9)."""
        if not lead.mensagem:
            return False, "sem mensagem"
        # Em modo de teste tudo vai para o SEU e-mail — as travas de produção
        # (validação, prova, opt-out do lead) não se aplicam.
        if self.modo_teste():
            return True, ""
        if lead.opt_out:
            return False, "opt-out registrado"
        if lead.canal != "email":
            return False, f"canal {lead.canal} não é e-mail (envio manual)"
        if lead.contato.email_status != "valid":
            return False, "e-mail não validado (nunca enviar não-validado)"
        if not self.cfg.get("negocio", "contato", default="").strip():
            return False, "assinatura sem contato: preencha negocio.contato"
        return True, ""

    @abc.abstractmethod
    def _do_send(self, lead: Lead) -> SendResult:
        ...

    def send(self, lead: Lead) -> SendResult:
        ok, motivo = self.pode_enviar(lead)
        if not ok:
            return SendResult(False, lead.canal, f"bloqueado: {motivo}")
        return self._do_send(lead)

    def enviar_lote(self, leads: list[Lead], pausa: float = 0.0) -> list[SendResult]:
        """Envia vários leads. Senders com conexão persistente (SMTP) sobrescrevem
        para reusar a conexão."""
        return [self.send(l) for l in leads]
