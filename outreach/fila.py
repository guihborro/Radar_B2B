"""Fila de leads pré-construída (ranqueada), para o envio diário ser RÁPIDO.

Em vez de varrer os 3,3 GB da Receita a cada dia (lento e frágil no Modern
Standby), a gente escaneia UMA vez, ranqueia e salva em data/fila_leads.jsonl.
O `rodar` diário só lê a fila (instantâneo), pula os já enviados e manda os N
melhores. Reconstrua com `cli preparar-fila` quando quiser dados/filtros novos.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import Config
from .storage.models import Contato, Empresa, Lead


def _arquivo(cfg: Config) -> Path:
    return cfg.root / "data" / "fila_leads.jsonl"


def existe_fila(cfg: Config) -> bool:
    return _arquivo(cfg).is_file()


def construir_fila(cfg: Config, tiers: list[str], n: int = 500) -> int:
    """Escaneia a Receita, filtra/ranqueia e salva a fila. Retorna o total."""
    from .export_html import selecionar_leads
    # mantém os já-contatados na fila (a lista de ligação precisa do telefone/tier
    # deles); o `rodar` filtra os contatados na hora de enviar, sem risco de reenvio.
    leads, _ = selecionar_leads(cfg, n=n, tiers=tiers, fator=12,
                                so_dominio_proprio=True, excluir_contatados=False)
    p = _arquivo(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for l in leads:
            fh.write(json.dumps({
                "empresa": asdict(l.empresa),
                "contato": asdict(l.contato),
                "tier": l.tier,
            }, ensure_ascii=False) + "\n")
    return len(leads)


def ler_fila(cfg: Config) -> list[Lead]:
    """Lê a fila salva e reconstrói os Leads (ordem = ranking já feito)."""
    p = _arquivo(cfg)
    if not p.is_file():
        return []
    leads: list[Lead] = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            leads.append(Lead(
                empresa=Empresa(**d["empresa"]),
                contato=Contato(**d["contato"]),
                tier=d.get("tier", ""),
                canal="email",
            ))
    return leads
