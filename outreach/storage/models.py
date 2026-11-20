"""Modelos de domínio do pipeline.

Um `Lead` carrega a empresa-alvo (Empresa) e o contato/decisor (Contato), e
percorre o ciclo de status NEW -> ... -> SENT/REPLIED/MEETING. Usamos
dataclasses simples; a persistência fica em db.py.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


class LeadStatus(str, enum.Enum):
    NEW = "new"                 # recém-sourced
    ENRICHED = "enriched"       # candidatos de e-mail/telefone gerados
    VALIDATED = "validated"     # e-mail verificado, ok para enviar
    REJECTED = "rejected"       # sem canal alcançável / fora do ICP
    ROUTED = "routed"           # canal escolhido pela cascata
    PERSONALIZED = "personalized"  # mensagem pronta
    QUEUED = "queued"           # na fila de envio
    SENT = "sent"
    REPLIED = "replied"
    BOUNCED = "bounced"
    MEETING = "meeting"         # reunião marcada (objetivo final)


class Channel(str, enum.Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    PHONE = "telefone"


@dataclass
class Empresa:
    nome: str
    cnae: str = ""
    dominio: str = ""               # ex.: "acme.com.br"
    funcionarios: int | None = None
    faturamento: float | None = None
    capital_social: float | None = None   # Receita (proxy fraco de porte)
    porte: str = ""                 # Receita: "ME" | "EPP" | "Demais" (não é headcount)
    natureza: str = ""              # código da natureza jurídica (ex.: 2062=LTDA)
    regiao: str = ""
    uf: str = ""
    cidade: str = ""
    municipio_cod: str = ""           # código do município na Receita (lookup p/ cidade)
    cnpj: str = ""
    fundacao_ano: int | None = None   # ano de abertura (Receita) — p/ "X anos de mercado"
    matriz: bool = True               # True=matriz, False=filial (Receita)


@dataclass
class Contato:
    nome: str = ""
    cargo: str = ""
    email: str = ""                 # melhor e-mail (após validação)
    email_status: str = "unknown"   # valid | invalid | risky | unknown
    email_score: float | None = None
    email_candidatos: list[str] = field(default_factory=list)
    telefone: str = ""
    linkedin_url: str = ""


@dataclass
class Mensagem:
    canal: str = Channel.EMAIL.value
    assunto: str = ""
    corpo: str = ""
    variante: str = ""
    template_key: str = ""
    personalizada_por_llm: bool = False


@dataclass
class Lead:
    empresa: Empresa
    contato: Contato = field(default_factory=Contato)
    status: str = LeadStatus.NEW.value
    tier: str = ""
    canal: str = ""                 # canal escolhido pela cascata
    mensagem: Mensagem | None = None
    motivo_rejeicao: str = ""
    opt_out: bool = False
    id: int | None = None
    criado_em: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_row(self) -> dict[str, Any]:
        """Achata para uma linha de tabela (JSON nos campos compostos)."""
        return {
            "id": self.id,
            "status": self.status,
            "tier": self.tier,
            "canal": self.canal,
            "motivo_rejeicao": self.motivo_rejeicao,
            "opt_out": int(self.opt_out),
            "criado_em": self.criado_em,
            "empresa": _json(self.empresa),
            "contato": _json(self.contato),
            "mensagem": _json(self.mensagem) if self.mensagem else None,
        }


def _json(obj: Any) -> str:
    import json

    return json.dumps(asdict(obj), ensure_ascii=False)
