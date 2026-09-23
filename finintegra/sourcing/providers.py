"""Stubs dos provedores BR baseados na Receita (§4.1).

Cada um já lê a chave do .env e tem o ponto exato onde plugar a chamada HTTP.
Enquanto não escolhido (§11), levantam NotImplementedError com instrução clara —
de propósito, para você não disparar contra um provedor não auditado (§4.3).
"""
from __future__ import annotations

from .base import ICPFilter, SourcingProvider


class _ProvedorAPIBase(SourcingProvider):
    #: nome da variável de ambiente com a chave
    ENV_KEY: str = ""
    #: URL base da API (preencher ao implementar)
    BASE_URL: str = ""
    NOME: str = ""

    def search(self, f: ICPFilter) -> list[Lead]:  # type: ignore[name-defined]
        chave = self.cfg.env(self.ENV_KEY)
        if not chave:
            raise RuntimeError(
                f"{self.NOME}: defina {self.ENV_KEY} no .env antes de usar."
            )
        raise NotImplementedError(
            f"Integração {self.NOME} ainda não implementada.\n"
            f"Implemente aqui a chamada a {self.BASE_URL} mapeando os filtros de "
            f"ICP (CNAEs={f.cnaes[:3]}..., funcionários "
            f"{f.funcionarios_min}-{f.funcionarios_max}, regiões={f.regioes}) "
            f"para os parâmetros da API e converta a resposta em Lead.\n"
            f"ANTES de comprar plano, rode a auditoria de §4.3: "
            f"python -m finintegra.cli auditar"
        )


class EconodataProvider(_ProvedorAPIBase):
    ENV_KEY = "ECONODATA_API_KEY"
    BASE_URL = "https://api.econodata.com.br/"  # ajustar à doc real
    NOME = "Econodata"


class SpeedioProvider(_ProvedorAPIBase):
    ENV_KEY = "SPEEDIO_API_KEY"
    BASE_URL = "https://api.speedio.com.br/"   # ajustar à doc real
    NOME = "Speedio"


class DataStoneProvider(_ProvedorAPIBase):
    ENV_KEY = "DATASTONE_API_KEY"
    BASE_URL = "https://api.datastone.com.br/"  # ajustar à doc real
    NOME = "Data Stone"
