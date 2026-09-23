"""Seleciona o template do nicho (por CNAE) e preenche os placeholders.

Esta é a base determinística. A personalização por LLM (personalize.py) opera
em cima do que sai daqui.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from ..config import Config
from ..storage.models import Channel, Lead, Mensagem

# Idade mínima para citar "X anos de mercado" (só elogia empresa consolidada).
_IDADE_MIN = 10


def _aplicar(texto: str, valores: dict[str, str]) -> str:
    for chave, val in valores.items():
        texto = texto.replace("{{" + chave + "}}", val)
    return texto


def render_mensagem(lead: Lead, cfg: Config, variante: str | None = None) -> Mensagem:
    """Monta a Mensagem (assunto + corpo) para o lead, sem LLM."""
    template_key = cfg.template_key_for_cnae(lead.empresa.cnae)
    tpl = cfg.template(template_key)
    variante = variante or cfg.get("copy", "variante_padrao",
                                   default="prova_social_diagnostico")
    variantes = tpl.get("variantes", {})
    if variante not in variantes:
        variante = next(iter(variantes))  # fallback: primeira disponível
    bloco = variantes[variante]

    valores = _valores(lead, cfg, tpl)

    # assunto: A/B igualitário (50/50) se configurado; senão o do template
    assuntos_ab = cfg.get("copy", "assuntos_ab", default=None) or []
    if len(assuntos_ab) >= 2:
        chave = lead.empresa.cnpj or lead.empresa.nome or ""
        modelo_assunto = assuntos_ab[sum(map(ord, chave)) % len(assuntos_ab)]
    else:
        modelo_assunto = bloco.get("assunto", "")

    assunto = _aplicar(modelo_assunto, valores)
    assunto = assunto[:1].upper() + assunto[1:]     # 1ª letra maiúscula
    corpo = _saudacao_ok(_aplicar(bloco.get("corpo", ""), valores))
    corpo = _personalizar(corpo, lead, com_tempo_de_mercado=True)
    return Mensagem(
        canal=lead.canal or Channel.EMAIL.value,
        assunto=assunto,
        corpo=corpo,
        variante=variante,
        template_key=template_key,
        personalizada_por_llm=False,
    )


def _personalizar(corpo: str, lead: Lead, com_tempo_de_mercado: bool) -> str:
    """Personalização determinística com dado REAL da Receita (sem inventar):
      1) nome do decisor na saudação, quando temos (só ~15% dos leads);
      2) "X anos de mercado", quando a empresa é consolidada (só no 1º e-mail).
    Cada peça só entra se o dado existir — nunca deixa placeholder vazio/estranho.
    """
    nome = _primeiro_nome(lead.contato.nome)
    if nome and _nome_de_pessoa(nome):
        if corpo.startswith("Olá!"):
            corpo = corpo.replace("Olá!", f"Olá, {nome}!", 1)
        elif corpo.startswith("Oi!"):
            corpo = corpo.replace("Oi!", f"Oi, {nome}!", 1)
        elif corpo.startswith("Pergunta direta:"):
            corpo = f"Olá, {nome}! " + corpo

    if com_tempo_de_mercado and lead.empresa.fundacao_ano and "Sou o " in corpo:
        idade = date.today().year - lead.empresa.fundacao_ano
        if _IDADE_MIN <= idade <= 150:
            empresa = _empresa_exibicao(lead.empresa.nome)
            detalhe = f"Vi que a {empresa} já tem {idade} anos de mercado. "
            corpo = corpo.replace("Sou o ", detalhe + "Sou o ", 1)
    return corpo


def _nome_de_pessoa(primeiro: str) -> bool:
    """Evita saudar com lixo: só nomes alfabéticos plausíveis (não sigla/razão)."""
    p = primeiro.strip()
    return len(p) >= 3 and p.replace("-", "").isalpha()


def _valores(lead: Lead, cfg: Config, tpl: dict) -> dict[str, str]:
    """Placeholders comuns ao 1º e-mail e aos follow-ups."""
    nome_rem = cfg.get("negocio", "nome_remetente", default="")
    contato = cfg.get("negocio", "contato", default="")
    return {
        "NOME": _primeiro_nome(lead.contato.nome),
        "EMPRESA": _empresa_exibicao(lead.empresa.nome),
        "NICHO": tpl.get("nome_exibicao", "indústria"),
        "NOME_REMETENTE": nome_rem,
        "CONTATO": contato,
        "ASSINATURA": _assinatura(cfg, nome_rem, contato),
        "DETALHE": "",  # preenchido pela personalização, se houver
    }


def _assinatura(cfg: Config, nome_rem: str, contato: str) -> str:
    """Assinatura de texto com marca (dá identidade sem logo):
        Seu Nome
        Sua Empresa · Sua tagline
        (11) 99999-9999
    Cada linha só entra se existir (nunca gera linha vazia)."""
    empresa = str(cfg.get("negocio", "empresa", default="")).strip()
    tagline = str(cfg.get("negocio", "tagline", default="")).strip()
    marca = f"{empresa} · {tagline}" if (empresa and tagline) else (empresa or "")
    linhas = [x for x in (nome_rem, marca, contato) if x]
    return "\n".join(linhas)


def render_followup(lead: Lead, cfg: Config, bloco: dict, etapa: int) -> Mensagem:
    """Monta a mensagem de follow-up da etapa N (1-based).

    O assunto NÃO vem do bloco: reusa o assunto do 1º e-mail com "Re:" na
    frente. Como o rodízio A/B é determinístico por empresa, o assunto original
    é reconstruído exatamente igual, e a mensagem cai na mesma conversa.
    """
    template_key = cfg.template_key_for_cnae(lead.empresa.cnae)
    tpl = cfg.template(template_key)
    valores = _valores(lead, cfg, tpl)
    assunto = render_mensagem(lead, cfg).assunto
    if not assunto.lower().startswith("re:"):
        assunto = f"Re: {assunto}"
    corpo = _saudacao_ok(_aplicar(bloco.get("corpo", ""), valores))
    corpo = _personalizar(corpo, lead, com_tempo_de_mercado=False)
    return Mensagem(
        canal=lead.canal or Channel.EMAIL.value,
        assunto=assunto,
        corpo=corpo,
        variante=f"followup{etapa}",
        template_key=template_key,
        personalizada_por_llm=False,
    )


def _saudacao_ok(texto: str) -> str:
    """Conserta a abertura quando não há nome do decisor (NOME vazio)."""
    texto = texto.replace("Olá , ", "Olá, ").replace("Olá ,", "Olá,")
    if texto.startswith(", "):                 # variante "{{NOME}}, pergunta..."
        texto = texto[2:]
        texto = texto[:1].upper() + texto[1:]
    return texto


def _primeiro_nome(nome: str) -> str:
    return nome.split()[0] if nome.strip() else ""


def _sem_acento(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# status societário que polui o nome (não faz parte da marca) — removido do fim
_STATUS_SUFIXOS = ("em recuperacao judicial", "em recuperacao extrajudicial",
                   "em recuperacao", "massa falida", "em liquidacao", "em falencia")

# formas jurídicas (removidas do fim) e termos genéricos (cortam o nome)
_LEGAL = {"ltda", "sa", "eireli", "epp", "me", "mei", "cia"}
_CORTA = {"industria", "comercio", "comercial", "industrial", "distribuidora",
          "distribuicao", "importacao", "exportacao", "representacoes", "solucoes"}
_PEQ = {"de", "da", "do", "das", "dos", "e"}


def _empresa_exibicao(nome: str) -> str:
    """Razão social crua -> nome curto e title-case p/ assunto e corpo.
    Ex.: 'SABO INDUSTRIA E COMERCIO DE AUTOPECAS' -> 'Sabo';
         'DECIO VAREJO LTDA' -> 'Decio Varejo'."""
    nome = (nome or "").strip()
    if not nome or nome == "(sem nome)":
        return "sua empresa"
    # tira status de falência/recuperação do fim (não é a marca; poluía o assunto)
    low = _sem_acento(nome).lower()
    for s in _STATUS_SUFIXOS:
        if low.endswith(s):
            nome = nome[: len(nome) - len(s)].rstrip(" -,.")
            break
    tokens = nome.split()
    # remove formas jurídicas do fim
    while tokens:
        t = _sem_acento(tokens[-1]).lower().replace(".", "").replace("/", "")
        if t in _LEGAL:
            tokens.pop()
        else:
            break
    # corta no primeiro termo genérico (mantém só o que vem antes)
    mantidos: list[str] = []
    for t in tokens:
        if _sem_acento(t).lower().strip(".,") in _CORTA and mantidos:
            break
        mantidos.append(t)
    tokens = mantidos or tokens
    # title-case com conectivos em minúscula
    out = []
    for i, t in enumerate(tokens):
        low = t.lower()
        out.append(low if (i > 0 and low in _PEQ) else low.capitalize())
    return " ".join(out) or nome


# valor de exemplo para preview/teste quando a assinatura ainda está pendente
_EXEMPLO_CONTATO = "(11) 99999-9999"


def preencher_exemplos_se_vazio(cfg: Config) -> list[str]:
    """Preenche a assinatura (contato) com EXEMPLO se vazia. Retorna os campos
    que foram supostos (para avisar). Usado em preview e em envio de teste."""
    exemplos: list[str] = []
    negocio = cfg.raw.setdefault("negocio", {})
    if not str(negocio.get("contato", "")).strip():
        negocio["contato"] = _EXEMPLO_CONTATO
        exemplos.append("negocio.contato")
    return exemplos
