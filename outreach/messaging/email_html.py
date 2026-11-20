"""Renderiza a Mensagem como um e-mail HTML LIMPO — só o conteúdo que o cliente
recebe (sem De/Para/CC, sem ficha de dados). É o que vai no corpo do envio e o
que o comando `html` salva.

Layout em tabela + estilos inline: é o padrão que sobrevive a clientes de
e-mail restritivos (Outlook desktop, Gmail) — divs/flex/grid não são confiáveis
em e-mail.
"""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

from ..config import Config
from ..storage.models import Mensagem

_FONTE = "Arial, Helvetica, sans-serif"
LOGO_CID = "logo-empresa"      # Content-ID usado no envio SMTP


def logo_path(cfg: Config | None) -> Path | None:
    """Caminho da logo, lido de `negocio.logo_path` no config (opcional).

    Vazio por padrão: sem logo, o e-mail sai com o nome da empresa em texto.
    Caminhos relativos são resolvidos a partir da raiz do projeto.
    """
    if not cfg:
        return None
    rel = str(cfg.get("negocio", "logo_path", default="") or "").strip()
    if not rel:
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = cfg.root / p
    return p if p.is_file() else None


def logo_data_uri(cfg: Config | None) -> str:
    """Logo embutida em base64 (para o arquivo HTML abrir no navegador)."""
    p = logo_path(cfg)
    if not p:
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _blocos(corpo: str) -> list[str]:
    return [b.strip() for b in corpo.strip().split("\n\n") if b.strip()]


def _e_optout(bloco: str) -> bool:
    l = bloco.lower()
    return l.startswith("se ") and any(k in l for k in ("avis", "sentido", "insist"))


def _e_assinatura(linhas: list[str]) -> bool:
    return any(l.lower().startswith(("atenciosamente", "abraço", "abraco")) for l in linhas)


def _paragrafos_html(blocos: list[str], cor: str, tamanho: str = "15.5px",
                     entrelinha: str = "1.7") -> str:
    partes = []
    for bloco in blocos:
        linhas = [l.strip() for l in bloco.split("\n") if l.strip()]
        if not linhas:
            continue
        if _e_assinatura(linhas):
            conteudo = "<br>".join(html.escape(l) for l in linhas)
        else:
            conteudo = html.escape(" ".join(linhas))
        partes.append(
            f'<p style="margin:0 0 16px 0;font-family:{_FONTE};font-size:{tamanho};'
            f'line-height:{entrelinha};color:{cor};">{conteudo}</p>'
        )
    if partes:
        # remove a margem inferior do último parágrafo do bloco
        partes[-1] = partes[-1].replace("margin:0 0 16px 0;", "margin:0;", 1)
    return "\n              ".join(partes)


def _preheader(blocos: list[str]) -> str:
    for bloco in blocos:
        texto = re.sub(r"\s+", " ", bloco).strip()
        if texto:
            return html.escape(texto[:110])
    return ""


def email_para_html(msg: Mensagem, cfg: Config | None = None,
                    logo_src: str | None = None) -> str:
    """E-mail completo e limpo (o que o destinatário vê), layout profissional.

    logo_src: URL/data-URI/cid da logo. Se None, tenta embutir a logo configurada
    em `negocio.logo_path` como data URI (para o arquivo de preview). No envio
    SMTP, passe "cid:...". String vazia = sem logo.
    """
    marca = (cfg.get("negocio", "empresa", default="Sua Empresa") if cfg else "Sua Empresa") or "Sua Empresa"
    tagline = str(cfg.get("negocio", "tagline", default="") or "").strip() if cfg else ""
    if logo_src is None:
        logo_src = logo_data_uri(cfg)

    if logo_src:
        marca_html = (
            f'<img src="{logo_src}" alt="{html.escape(marca)}" width="176" '
            f'style="display:block;border:0;outline:none;text-decoration:none;'
            f'width:176px;max-width:60%;height:auto;">'
        )
    else:
        marca_html = (
            f'<span style="font-family:{_FONTE};font-size:15px;font-weight:bold;'
            f'letter-spacing:.06em;color:#173b32;">{html.escape(marca)}</span>'
        )

    todos = _blocos(msg.corpo)
    optout = [b for b in todos if _e_optout(b)]
    principais = [b for b in todos if not _e_optout(b)]

    corpo_html = _paragrafos_html(principais, "#2a3239")
    rodape_tr = ""
    if optout:
        rodape_html = _paragrafos_html(optout, "#98a2ac", tamanho="12.5px", entrelinha="1.6")
        rodape_tr = f"""
          <tr>
            <td style="padding:16px 36px 26px 36px;border-top:1px solid #eef0f3;">
              {rodape_html}
            </td>
          </tr>"""

    preheader = _preheader(todos)
    tagline_html = (
        f'\n              <div style="margin-top:9px;font-family:{_FONTE};font-size:12px;'
        f'color:#8a97a3;letter-spacing:.02em;">{html.escape(tagline)}</div>'
        if tagline else ""
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>{html.escape(msg.assunto)}</title>
</head>
<body style="margin:0;padding:0;background-color:#eef1f4;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">
    {preheader}
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#eef1f4;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               style="width:600px;max-width:100%;background-color:#ffffff;border-radius:10px;border:1px solid #e2e6ea;">
          <tr>
            <td style="padding:24px 36px 20px 36px;border-bottom:1px solid #eef0f3;">
              {marca_html}{tagline_html}
            </td>
          </tr>
          <tr>
            <td style="padding:28px 36px;">
              {corpo_html}
            </td>
          </tr>{rodape_tr}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
