"""Carregamento e acesso à configuração.

Lê config/config.yaml, config/cnaes.yaml e os templates de config/templates/.
Carrega segredos do .env (via python-dotenv, se instalado). Nada aqui é
hardcoded de negócio — só a mecânica de leitura.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:  # python-dotenv é opcional; sem ele, lemos só o ambiente do SO
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _project_root() -> Path:
    # finintegra/config.py -> raiz do projeto é o diretório-pai do pacote
    return Path(__file__).resolve().parent.parent


@dataclass
class Config:
    """Acesso tipado e conveniente ao conteúdo de config/."""

    raw: dict[str, Any]
    cnaes: dict[str, Any]
    templates: dict[str, dict[str, Any]]
    root: Path

    # --- atalhos de leitura ---------------------------------------------------
    def get(self, *keys: str, default: Any = None) -> Any:
        """Acesso aninhado seguro: cfg.get('ferramentas', 'envio')."""
        node: Any = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def env(self, name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, default)

    # --- domínio --------------------------------------------------------------
    @property
    def db_path(self) -> Path:
        rel = self.get("storage", "db_path", default="data/finintegra.sqlite")
        return self.root / rel

    @property
    def modo_seguro(self) -> bool:
        return bool(self.get("operacao", "modo_seguro", default=True))

    @property
    def bounce_rate_max(self) -> float:
        return float(self.get("operacao", "bounce_rate_max", default=0.04))

    def cnae_tier(self, cnae: str) -> str | None:
        """Retorna o tier ('tier1'...) de um CNAE por correspondência de prefixo."""
        cnae_norm = _norm_cnae(cnae)
        for tier, entradas in self.cnaes.get("tiers", {}).items():
            for e in entradas:
                if cnae_norm.startswith(_norm_cnae(str(e["codigo"]))):
                    return tier
        return None

    def template_key_for_cnae(self, cnae: str) -> str:
        """Mapa CNAE -> nome do template (com fallback genérico)."""
        cnae_norm = _norm_cnae(cnae)
        mapa = self.cnaes.get("template_por_cnae", {})
        # casa pelo prefixo mais longo definido
        melhor = ""
        escolhido = self.cnaes.get("default_template", "industria_generico")
        for prefixo, nome in mapa.items():
            pnorm = _norm_cnae(prefixo)
            if cnae_norm.startswith(pnorm) and len(pnorm) > len(melhor):
                melhor, escolhido = pnorm, nome
        return escolhido

    def template(self, key: str) -> dict[str, Any]:
        if key not in self.templates:
            raise KeyError(
                f"Template '{key}' não encontrado em config/templates/. "
                f"Disponíveis: {sorted(self.templates)}"
            )
        return self.templates[key]


def _norm_cnae(c: str) -> str:
    """Mantém só dígitos para comparar prefixos (ignora pontuação 0000-0/00)."""
    return "".join(ch for ch in str(c) if ch.isdigit())


def load_config(root: Path | None = None) -> Config:
    root = root or _project_root()
    if load_dotenv is not None:
        load_dotenv(root / ".env")

    cfg_path = root / "config" / "config.yaml"
    cnaes_path = root / "config" / "cnaes.yaml"
    tpl_dir = root / "config" / "templates"

    raw = _read_yaml(cfg_path)
    cnaes = _read_yaml(cnaes_path)

    templates: dict[str, dict[str, Any]] = {}
    if tpl_dir.is_dir():
        for f in sorted(tpl_dir.glob("*.yaml")):
            data = _read_yaml(f)
            nome = data.get("nicho") or f.stem
            templates[nome] = data

    return Config(raw=raw, cnaes=cnaes, templates=templates, root=root)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Config ausente: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
