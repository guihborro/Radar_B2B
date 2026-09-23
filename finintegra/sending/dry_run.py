"""DryRunSender — escreve a mensagem em data/outbox/ em vez de enviar.

Permite revisar exatamente o que SERIA enviado, com a guarda de compliance já
aplicada. É o default e o que roda sem domínio/infra de envio.
"""
from __future__ import annotations

from datetime import datetime

from .base import EmailSender, SendResult
from ..storage.models import Lead


class DryRunSender(EmailSender):
    def _do_send(self, lead: Lead) -> SendResult:
        outbox = self.cfg.root / "data" / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        msg = lead.mensagem
        assert msg is not None
        nome = f"{lead.id or 'x'}_{_slug(lead.empresa.nome)}.txt"
        conteudo = (
            f"# DRY-RUN — não enviado ({datetime.now().isoformat(timespec='seconds')})\n"
            f"Para: {lead.contato.nome} <{self.destino(lead)}>\n"
            f"Empresa: {lead.empresa.nome} (CNAE {lead.empresa.cnae}, {lead.tier})\n"
            f"Canal: {lead.canal} | variante: {msg.variante} | "
            f"template: {msg.template_key} | LLM: {msg.personalizada_por_llm}\n"
            f"Assunto: {msg.assunto}\n"
            f"{'-' * 60}\n{msg.corpo}\n"
        )
        (outbox / nome).write_text(conteudo, encoding="utf-8")
        return SendResult(True, "email", f"dry-run -> data/outbox/{nome}")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower())[:30]
