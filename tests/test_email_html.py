"""Testes do e-mail HTML: a logo é opcional e vem do config."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outreach.config import load_config
from outreach.messaging.email_html import email_para_html, logo_path
from outreach.storage.models import Mensagem

_MSG = Mensagem(assunto="Teste", corpo="Olá, tudo bem?\n\nAtenciosamente,\nSeu Nome")


def test_sem_logo_por_padrao():
    cfg = load_config()
    cfg.raw.setdefault("negocio", {})["logo_path"] = ""
    assert logo_path(cfg) is None
    html = email_para_html(_MSG, cfg)
    assert "<img" not in html
    assert "Sua Empresa" in html or str(cfg.get("negocio", "empresa")) in html


def test_logo_configurada_inexistente_vira_none():
    cfg = load_config()
    cfg.raw.setdefault("negocio", {})["logo_path"] = "assets/nao_existe.png"
    assert logo_path(cfg) is None
    assert "<img" not in email_para_html(_MSG, cfg)


def test_logo_configurada_entra_no_html(tmp_path):
    png = tmp_path / "logo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")  # o conteúdo não importa para o teste
    cfg = load_config()
    cfg.raw.setdefault("negocio", {})["logo_path"] = str(png)
    assert logo_path(cfg) == png
    html = email_para_html(_MSG, cfg)
    assert '<img src="data:image/png;base64,' in html
