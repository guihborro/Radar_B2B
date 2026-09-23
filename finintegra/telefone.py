"""Canal telefone/WhatsApp — o multicanal do passo 5 do Alfredo Soares.

E-mail sozinho tem teto. Para os leads de MAIOR valor (tier1) que já receberam
e-mail e NÃO responderam, a gente monta uma lista de ligação/WhatsApp usando os
telefones que já vêm da Receita — de graça. Você trabalha essa lista à mão.

Não dispara nada: só gera data/ligacoes.csv (abre no Excel) com empresa, decisor,
telefone, link de WhatsApp e o gancho do nicho para usar na conversa.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import Config


def _so_digitos(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def _wa_link(telefone: str) -> str:
    """+55 11 3456-7890 -> https://wa.me/551134567890 (só se parecer válido)."""
    d = _so_digitos(telefone)
    if d and not d.startswith("55"):
        d = "55" + d
    return f"https://wa.me/{d}" if 12 <= len(d) <= 13 else ""


def gerar_lista(cfg: Config, so_completos: bool = False) -> list[dict]:
    """tier1 já contatado por e-mail, SEM resposta e com telefone.

    so_completos=True: só os que já passaram por toda a cadência de e-mail (o
    momento ideal para ligar). False: todos os tier1 contatados sem resposta,
    mostrando em que etapa da cadência estão.
    """
    from .followup import _config, _historico, _indice_fila

    n_etapas = min(len(_config(cfg).get("cadencia_dias") or []),
                   len(_config(cfg).get("etapas") or []))
    idx = _indice_fila(cfg)
    agora = datetime.now(timezone.utc)

    linhas: list[dict] = []
    for h in _historico(cfg).values():
        if h["encerrado"] or h["primeiro_envio"] is None:
            continue                                    # respondeu/bounce/optout
        lead = idx.get(h["email"])
        if lead is None or lead.tier != "tier1":
            continue                                    # só o topo do ICP
        telefone = lead.contato.telefone.strip()
        if not telefone:
            continue
        if so_completos and h["n_followups"] < n_etapas:
            continue
        tpl = cfg.template(cfg.template_key_for_cnae(lead.empresa.cnae))
        linhas.append({
            "empresa": lead.empresa.nome,
            "decisor": lead.contato.nome or "",
            "telefone": telefone,
            "whatsapp": _wa_link(telefone),
            "cidade_uf": lead.empresa.uf,
            "nicho": tpl.get("nome_exibicao", "indústria"),
            "gancho": " ".join((tpl.get("gancho") or "").split()),
            "etapas_email": h["n_followups"] + 1,       # 1 (só 1º) .. n_etapas+1
            "dias_desde_1o": (agora - h["primeiro_envio"]).days,
        })

    # mais quentes primeiro: quem recebeu mais e-mails sem responder
    linhas.sort(key=lambda d: (-d["etapas_email"], -d["dias_desde_1o"]))
    return linhas


def salvar_csv(cfg: Config, linhas: list[dict]) -> Path:
    p = cfg.root / "data" / "ligacoes.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    campos = ["empresa", "decisor", "telefone", "whatsapp", "cidade_uf",
              "nicho", "etapas_email", "dias_desde_1o", "gancho"]
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    return p
