"""Contrato de um provedor de dados de empresas."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

from ..config import Config
from ..storage.models import Lead


@dataclass
class ICPFilter:
    """Filtros de ICP montados a partir do config (CNAE, porte, região)."""

    cnaes: list[str] = field(default_factory=list)
    funcionarios_min: int | None = None
    funcionarios_max: int | None = None
    regioes: list[str] = field(default_factory=list)
    limite: int = 50                # quantas empresas puxar (já com multiplicador)

    @classmethod
    def from_config(cls, cfg: Config, alvo_final: int,
                    tiers: list[str] | None = None) -> "ICPFilter":
        tiers_dict = cfg.cnaes.get("tiers", {})
        if tiers:  # restringe a setores específicos (ex.: só industrial, sem agro)
            tiers_dict = {k: v for k, v in tiers_dict.items() if k in tiers}
        cnaes = [str(e["codigo"]) for t in tiers_dict.values() for e in t]
        mult = int(cfg.get("operacao", "multiplicador_lista", default=3))
        return cls(
            cnaes=cnaes,
            funcionarios_min=cfg.get("icp", "faixa_funcionarios", "min"),
            funcionarios_max=cfg.get("icp", "faixa_funcionarios", "max"),
            regioes=cfg.get("icp", "regioes", default=[]) or [],
            limite=alvo_final * mult,
        )


class SourcingProvider(abc.ABC):
    """Implemente isto para cada provedor (Econodata, Speedio, ...)."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    @abc.abstractmethod
    def search(self, f: ICPFilter) -> list[Lead]:
        """Retorna leads (empresa + contato bruto) que batem com o filtro."""

    def name(self) -> str:
        return self.__class__.__name__
