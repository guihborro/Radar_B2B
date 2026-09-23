"""Provedor CSV — importa um export de qualquer provedor (Econodata, Speedio...).

Mapeie as colunas do seu export para os campos esperados no dicionário
`COLMAP`. É a forma provedor-agnóstica de alimentar o pipeline sem API.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .base import ICPFilter, SourcingProvider
from ..storage.models import Contato, Empresa, Lead


# Mapa flexível: nome lógico -> possíveis nomes de coluna no CSV (case-insensitive).
COLMAP = {
    "empresa": ["empresa", "razao_social", "razão social", "nome_fantasia", "nome"],
    "cnae": ["cnae", "cnae_principal", "cnae fiscal"],
    "dominio": ["dominio", "domínio", "site", "website", "url"],
    "funcionarios": ["funcionarios", "funcionários", "qtd_funcionarios", "porte_func"],
    "regiao": ["regiao", "região", "uf", "estado"],
    "uf": ["uf", "estado"],
    "cidade": ["cidade", "municipio", "município"],
    "cnpj": ["cnpj"],
    "contato_nome": ["contato", "nome_contato", "decisor", "socio", "sócio"],
    "cargo": ["cargo", "funcao", "função"],
    "email": ["email", "e-mail", "email_contato"],
    "telefone": ["telefone", "fone", "celular", "whatsapp"],
    "linkedin": ["linkedin", "linkedin_url"],
}


def _pick(row: dict[str, str], logical: str) -> str:
    lower = {k.lower().strip(): v for k, v in row.items()}
    for cand in COLMAP.get(logical, []):
        if cand in lower and lower[cand]:
            return lower[cand].strip()
    return ""


class CSVProvider(SourcingProvider):
    def search(self, f: ICPFilter) -> list[Lead]:
        caminho = self.cfg.get("csv_import", "caminho", default="data/import.csv")
        path = self.cfg.root / caminho
        if not path.is_file():
            raise FileNotFoundError(
                f"CSV de import não encontrado: {path}\n"
                f"Aponte 'csv_import.caminho' no config para o export do provedor."
            )
        leads: list[Lead] = []
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                func = _pick(row, "funcionarios")
                empresa = Empresa(
                    nome=_pick(row, "empresa"),
                    cnae=_pick(row, "cnae"),
                    dominio=_norm_dominio(_pick(row, "dominio")),
                    funcionarios=int(func) if func.isdigit() else None,
                    regiao=_pick(row, "regiao"),
                    uf=_pick(row, "uf"),
                    cidade=_pick(row, "cidade"),
                    cnpj=_pick(row, "cnpj"),
                )
                contato = Contato(
                    nome=_pick(row, "contato_nome"),
                    cargo=_pick(row, "cargo"),
                    email=_pick(row, "email"),
                    telefone=_pick(row, "telefone"),
                    linkedin_url=_pick(row, "linkedin"),
                )
                if empresa.nome:
                    leads.append(Lead(empresa=empresa, contato=contato))
                if len(leads) >= f.limite:
                    break
        return leads


def _norm_dominio(v: str) -> str:
    v = v.strip().lower()
    for pref in ("https://", "http://", "www."):
        if v.startswith(pref):
            v = v[len(pref):]
    return v.split("/")[0]
