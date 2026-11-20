"""Provedor MOCK — empresas industriais sintéticas para rodar o pipeline
ponta a ponta sem nenhum serviço pago. É o default do config.

Gera dados plausíveis (CNAE dos tiers, porte na faixa, regiões-alvo) e contatos
COM e SEM e-mail/telefone/LinkedIn, justamente para exercitar a cascata
multicanal e a perda por camada.
"""
from __future__ import annotations

import random
import unicodedata

from .base import ICPFilter, SourcingProvider
from ..storage.models import Contato, Empresa, Lead


def _dominio_slug(nome: str) -> str:
    """Nome da empresa -> slug de domínio sem acentos (ex.: 'Precisão' -> 'precisao')."""
    nfkd = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.lower() if c.isalnum())[:18]


_NOMES_EMPRESA = [
    "Usimetal", "Plastibras", "AutoPeças Bandeirantes", "Ferramentaria Vale",
    "Injeplast", "MecânicaFina", "Componentes RS", "Indústria Catarinense",
    "Forjaria Minas", "Termoplásticos Sul", "Precisão Usinagem", "RodaPeças",
]
_SOBRENOMES = ["Silva", "Souza", "Oliveira", "Pereira", "Costa", "Almeida"]
_NOMES = ["Carlos", "Marcos", "Ana", "Roberto", "Patrícia", "João", "Luiz"]
_CARGOS = ["Sócio-Proprietário", "Diretor Financeiro", "Controller", "Diretor Comercial"]
_UFS = {"SP-interior": ("SP", "Campinas"), "RS": ("RS", "Caxias do Sul"),
        "SC": ("SC", "Joinville"), "MG": ("MG", "Contagem")}


class MockProvider(SourcingProvider):
    def search(self, f: ICPFilter) -> list[Lead]:
        rng = random.Random(42)  # determinístico p/ testes/demos
        cnaes = f.cnaes or ["25", "22", "29"]
        regioes = f.regioes or list(_UFS)
        leads: list[Lead] = []
        for i in range(f.limite):
            nome_emp = f"{rng.choice(_NOMES_EMPRESA)} {rng.randint(1, 999)}"
            slug = _dominio_slug(nome_emp)
            regiao = rng.choice(regioes)
            uf, cidade = _UFS.get(regiao, ("SP", "São Paulo"))
            fmin = f.funcionarios_min or 30
            fmax = f.funcionarios_max or 500
            empresa = Empresa(
                nome=nome_emp,
                cnae=rng.choice(cnaes),
                dominio=f"{slug}.com.br",
                funcionarios=rng.randint(fmin, fmax),
                regiao=regiao, uf=uf, cidade=cidade,
                cnpj=f"{rng.randint(10,99)}.{rng.randint(100,999)}.{rng.randint(100,999)}/0001-{rng.randint(10,99)}",
            )
            primeiro = rng.choice(_NOMES)
            ultimo = rng.choice(_SOBRENOMES)
            # Simula a perda por camada: nem todo contato tem cada canal.
            tem_linkedin = rng.random() < 0.5
            tem_tel = rng.random() < 0.7
            contato = Contato(
                nome=f"{primeiro} {ultimo}",
                cargo=rng.choice(_CARGOS),
                # e-mail NÃO vem pronto: o enrichment é que gera candidatos.
                telefone=f"+55 11 9{rng.randint(1000,9999)}-{rng.randint(1000,9999)}" if tem_tel else "",
                linkedin_url=f"https://linkedin.com/in/{primeiro.lower()}-{ultimo.lower()}" if tem_linkedin else "",
            )
            leads.append(Lead(empresa=empresa, contato=contato))
        return leads
