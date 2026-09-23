"""Tabelas de lookup da Receita (arquivos pequenos do mesmo Open Data).

Traduzem os CÓDIGOS que vêm nas empresas para nomes legíveis:
  - Municípios: código -> nome da cidade (destrava filtro/exibição por cidade);
  - Cnaes: código -> descrição da atividade.

Os arquivos ficam em data/receita/ (F.K03200$Z.*.MUNICCSV, *.CNAECSV). Se não
existirem, as funções devolvem {} e o resto do sistema segue sem cidade.
"""
from __future__ import annotations

import csv
import functools

from finintegra.config import load_config


def _pasta():
    cfg = load_config()
    return cfg.root / cfg.get("receita", "pasta", default="data/receita")


def _ler(glob: str) -> dict[str, str]:
    pasta = _pasta()
    if not pasta.is_dir():
        return {}
    arquivos = list(pasta.glob(glob))
    if not arquivos:
        return {}
    d: dict[str, str] = {}
    with arquivos[0].open(encoding="latin-1", newline="") as fh:
        for row in csv.reader(fh, delimiter=";", quotechar='"'):
            if len(row) >= 2 and row[0].strip():
                d[row[0].strip()] = row[1].strip()
    return d


@functools.lru_cache(maxsize=1)
def municipios() -> dict[str, str]:
    """código do município (Receita) -> nome da cidade (CAIXA ALTA, sem acento)."""
    return _ler("*MUNICCSV")


@functools.lru_cache(maxsize=1)
def cnaes() -> dict[str, str]:
    """código CNAE (7 díg) -> descrição da atividade."""
    return _ler("*CNAECSV")


def tem_cidades() -> bool:
    return bool(municipios())
