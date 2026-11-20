"""Enriquecimento: deriva candidatos de contato (e-mail) a partir de
nome + domínio. O gargalo do pipeline é o e-mail do decisor certo (§4.2)."""

from .email_patterns import gerar_candidatos_email, enriquecer_lead

__all__ = ["gerar_candidatos_email", "enriquecer_lead"]
