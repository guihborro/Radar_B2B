"""Montagem da mensagem: render do template de nicho + personalização por LLM."""
from __future__ import annotations

from .render import render_mensagem, render_followup, preencher_exemplos_se_vazio
from .personalize import personalizar
from .email_html import email_para_html

__all__ = [
    "render_mensagem",
    "render_followup",
    "preencher_exemplos_se_vazio",
    "personalizar",
    "email_para_html",
]
