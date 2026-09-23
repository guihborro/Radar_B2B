"""Orquestrador do pipeline Fase 2 (ponta a ponta, supervisionado).

    sourcing -> enrichment -> validation -> routing -> messaging -> sending

Cada etapa atualiza o status do Lead e persiste no Repository. Tudo é
configurável; nada de negócio é hardcoded aqui.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .enrichment import enriquecer_lead
from .messaging import personalizar, render_mensagem
from .routing import escolher_canal
from .sending import get_sender
from .sourcing import get_provider
from .sourcing.base import ICPFilter
from .storage import LeadStatus, Repository
from .storage.models import Channel, Lead
from .validation import get_validator


@dataclass
class PipelineResult:
    total: int = 0
    rejeitados: int = 0
    validados_email: int = 0
    roteados: dict[str, int] = field(default_factory=dict)
    enviados: int = 0
    bloqueados_envio: int = 0
    notas: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        l = [
            f"Pipeline — {self.total} leads sourced",
            f"  rejeitados (sem canal/ICP) : {self.rejeitados}",
            f"  e-mail validado            : {self.validados_email}",
            f"  roteados por canal         : {self.roteados}",
            f"  enviados (dry-run/real)    : {self.enviados}",
            f"  bloqueados no envio        : {self.bloqueados_envio}",
        ]
        l += [f"  ! {n}" for n in self.notas]
        return "\n".join(l)


def run(cfg: Config, alvo_final: int = 50, enviar: bool = True) -> PipelineResult:
    repo = Repository(cfg.db_path)
    provider = get_provider(cfg)
    validator = get_validator(cfg)
    sender = get_sender(cfg)
    res = PipelineResult()

    # avisos de pré-condição (não bloqueiam o pipeline, só o envio real)
    if not cfg.get("copy", "resultado_case", default="").strip():
        res.notas.append("resultado_case vazio: envios serão BLOQUEADOS (preencha a prova).")
    if not cfg.get("negocio", "contato", default="").strip():
        res.notas.append("negocio.contato vazio: envios serão BLOQUEADOS (assinatura).")

    # 1) SOURCING
    f = ICPFilter.from_config(cfg, alvo_final=alvo_final)
    leads = provider.search(f)
    res.total = len(leads)

    for lead in leads:
        _classificar_tier(lead, cfg)

        # 2) ENRICHMENT
        enriquecer_lead(lead)

        # 3) VALIDATION (e-mail) — nunca enviar não-validado
        candidatos = lead.contato.email_candidatos
        if candidatos:
            melhor = validator.melhor(candidatos)
            if melhor is not None:
                lead.contato.email = melhor.email
                lead.contato.email_status = melhor.status
                lead.contato.email_score = melhor.score
                if melhor.enviavel:
                    res.validados_email += 1
                    lead.status = LeadStatus.VALIDATED.value

        # 4) ROUTING (cascata multicanal)
        canal = escolher_canal(lead, cfg)
        if canal is None:
            lead.status = LeadStatus.REJECTED.value
            lead.motivo_rejeicao = "sem canal alcançável"
            res.rejeitados += 1
            repo.upsert(lead)
            continue
        lead.canal = canal
        lead.status = LeadStatus.ROUTED.value
        res.roteados[canal] = res.roteados.get(canal, 0) + 1

        # 5) MESSAGING (só e-mail é automatizado; LinkedIn/telefone = manual)
        if canal == Channel.EMAIL.value:
            base = render_mensagem(lead, cfg)
            lead.mensagem = personalizar(lead, base, cfg)
            lead.status = LeadStatus.PERSONALIZED.value

            # 6) SENDING
            if enviar:
                r = sender.send(lead)
                if r.enviado:
                    lead.status = LeadStatus.SENT.value
                    res.enviados += 1
                else:
                    res.bloqueados_envio += 1
                    lead.motivo_rejeicao = r.detalhe
        else:
            # canais manuais ficam prontos para o operador agir (§5.2)
            lead.motivo_rejeicao = f"ação manual: {canal}"

        repo.upsert(lead)

    repo.close()
    return res


def _classificar_tier(lead: Lead, cfg: Config) -> None:
    lead.tier = cfg.cnae_tier(lead.empresa.cnae) or ""
