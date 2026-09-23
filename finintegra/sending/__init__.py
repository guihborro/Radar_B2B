"""Envio de e-mail. Default 'dry_run' nunca envia de verdade (modo seguro)."""
from __future__ import annotations

from ..config import Config
from .base import EmailSender, SendResult
from .dry_run import DryRunSender
from .smtp import SMTPSender
from .providers import InstantlySender, SendGridSender, SmartleadSender

__all__ = ["EmailSender", "SendResult", "get_sender"]

_REGISTRY = {
    "dry_run": DryRunSender,
    "smtp": SMTPSender,
    "instantly": InstantlySender,
    "smartlead": SmartleadSender,
    "sendgrid": SendGridSender,
}


def get_sender(cfg: Config) -> EmailSender:
    nome = cfg.get("ferramentas", "envio", default="dry_run")
    # Há e-mail de teste configurado? Então TUDO vai para o seu endereço — é
    # seguro enviar de verdade mesmo com modo_seguro ligado.
    em_teste = bool(str(cfg.get("operacao", "email_teste", default="") or "").strip())
    # Trava global: modo_seguro força dry_run, EXCETO em modo de teste.
    if cfg.modo_seguro and nome != "dry_run" and not em_teste:
        print(f"[modo_seguro] envio='{nome}' ignorado — usando dry_run. "
              f"Defina operacao.email_teste para testar, ou modo_seguro=false p/ produção.")
        nome = "dry_run"
    if nome not in _REGISTRY:
        raise ValueError(f"envio '{nome}' desconhecido. Opções: {sorted(_REGISTRY)}")
    return _REGISTRY[nome](cfg)
