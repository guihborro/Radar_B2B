"""Gera padrões de e-mail prováveis a partir de nome + domínio.

Ordem dos padrões reflete frequência em PMEs BR (mais comuns primeiro). O
verificador (camada de validação) é quem decide qual candidato é real.
"""
from __future__ import annotations

import unicodedata

from ..storage.models import Lead


def _slug(texto: str) -> str:
    """Remove acentos e baixa caixa; mantém só letras."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.lower() if c.isalpha())


def gerar_candidatos_email(nome: str, dominio: str) -> list[str]:
    """Retorna candidatos ordenados do mais provável ao menos provável."""
    dominio = dominio.strip().lower()
    if not dominio or not nome.strip():
        return []
    partes = [p for p in nome.split() if p]
    first = _slug(partes[0]) if partes else ""
    last = _slug(partes[-1]) if len(partes) > 1 else ""
    if not first:
        return []

    padroes: list[str] = []
    if last:
        padroes += [
            f"{first}.{last}",      # carlos.silva  (mais comum)
            f"{first}{last}",       # carlossilva
            f"{first[0]}{last}",    # csilva
            f"{first}.{last[0]}",   # carlos.s
            f"{first}_{last}",      # carlos_silva
            f"{last}.{first}",      # silva.carlos
        ]
    padroes += [first]              # carlos  (fallback)

    # genéricos: úteis como último recurso, mas marcados como fracos (§4.2).
    genericos = ["contato", "comercial", "financeiro"]

    locais: list[str] = []
    for p in padroes + genericos:
        if p and p not in locais:
            locais.append(p)
    return [f"{loc}@{dominio}" for loc in locais]


def enriquecer_lead(lead: Lead) -> Lead:
    """Preenche email_candidatos se ainda não houver e-mail definido."""
    c = lead.contato
    if c.email:  # provedor já trouxe e-mail: mantém, mas guarda como candidato
        if c.email not in c.email_candidatos:
            c.email_candidatos.insert(0, c.email)
        return lead
    gerados = gerar_candidatos_email(c.nome, lead.empresa.dominio)
    # preserva candidatos pré-existentes (ex.: e-mail institucional vindo da
    # Receita) como FALLBACK, depois dos gerados a partir do nome do decisor.
    fallback = [e for e in c.email_candidatos if e not in gerados]
    c.email_candidatos = gerados + fallback
    return lead
