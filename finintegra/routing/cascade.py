"""Cascata de canal: define o canal de cada lead como 'alcançável por pelo menos
um canal' (§5), na ordem configurada — ajustável por tier.

Importante (§5.1): para dono de indústria pequena, telefone/WhatsApp às vezes
converte mais que e-mail. A ordem é configurável por tier justamente por isso —
telefone não é 'plano C'.
"""
from __future__ import annotations

from ..config import Config
from ..storage.models import Channel, Lead


def _email_validado(lead: Lead) -> bool:
    return bool(lead.contato.email) and lead.contato.email_status == "valid"


def _disponivel(lead: Lead, canal: str) -> bool:
    if canal == Channel.EMAIL.value:
        return _email_validado(lead)          # e-mail só conta se VALIDADO (§3/§9)
    if canal == Channel.LINKEDIN.value:
        return bool(lead.contato.linkedin_url)
    if canal == Channel.PHONE.value:
        return bool(lead.contato.telefone)
    return False


def escolher_canal(lead: Lead, cfg: Config) -> str | None:
    """Retorna o canal escolhido, ou None se o lead não é alcançável."""
    por_tier = cfg.get("canais", "ordem_cascata_por_tier", default={}) or {}
    ordem = por_tier.get(lead.tier) or cfg.get(
        "canais", "ordem_cascata_padrao", default=["email", "linkedin", "telefone"]
    )
    for canal in ordem:
        if _disponivel(lead, canal):
            return canal
    return None
