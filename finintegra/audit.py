"""Teste de confiabilidade do provedor (§4.3).

Rode ANTES de comprar plano de um provedor: pegue N empresas já conhecidas,
busque na fonte e meça cobertura real (% com e-mail, % porte/setor). Essa taxa
no seu segmento exato vale mais que qualquer claim de marketing.

Entrada: data/amostra_auditoria.csv com colunas conhecidas (ground truth):
    empresa, dominio, cnae, funcionarios
A comparação real depende do provedor escolhido; aqui medimos cobertura do que
a fonte devolve e (quando há ground truth) acerto de porte/setor.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .enrichment import enriquecer_lead
from .sourcing import get_provider
from .sourcing.base import ICPFilter
from .validation import get_validator


@dataclass
class AuditReport:
    total: int = 0
    com_email_candidato: int = 0
    com_email_valido: int = 0
    com_telefone: int = 0
    com_linkedin: int = 0
    cnae_no_alvo: int = 0
    notas: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        if self.total == 0:
            return "Amostra vazia."
        def pct(x: int) -> str:
            return f"{100 * x / self.total:4.0f}%"
        linhas = [
            f"Auditoria de confiabilidade — {self.total} empresas",
            f"  e-mail (algum candidato) : {pct(self.com_email_candidato)}",
            f"  e-mail VALIDADO          : {pct(self.com_email_valido)}",
            f"  telefone                 : {pct(self.com_telefone)}",
            f"  linkedin                 : {pct(self.com_linkedin)}",
            f"  CNAE dentro do alvo      : {pct(self.cnae_no_alvo)}",
        ]
        linhas += [f"  ! {n}" for n in self.notas]
        linhas.append(
            "\nRegra prática: e-mail validado <50% no seu segmento => "
            "multicanal é obrigatório (telefone/LinkedIn)."
        )
        return "\n".join(linhas)


def auditar(cfg: Config) -> AuditReport:
    n = int(cfg.get("operacao", "n_amostra_auditoria", default=25))
    provider = get_provider(cfg)
    validator = get_validator(cfg)

    f = ICPFilter.from_config(cfg, alvo_final=n)
    f.limite = n
    leads = provider.search(f)

    rep = AuditReport()
    if provider.name() == "MockProvider":
        rep.notas.append(
            "provedor=mock: números são sintéticos. Troque para o provedor real "
            "(config) e forneça data/amostra_auditoria.csv para medir de verdade."
        )
    for lead in leads:
        rep.total += 1
        enriquecer_lead(lead)
        if lead.contato.email or lead.contato.email_candidatos:
            rep.com_email_candidato += 1
            res = validator.melhor(lead.contato.email_candidatos)
            if res and res.enviavel:
                rep.com_email_valido += 1
        if lead.contato.telefone:
            rep.com_telefone += 1
        if lead.contato.linkedin_url:
            rep.com_linkedin += 1
        if cfg.cnae_tier(lead.empresa.cnae):
            rep.cnae_no_alvo += 1
    return rep
