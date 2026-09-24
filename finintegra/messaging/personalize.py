"""Personalização por LLM (Claude API) — §6.3.

Recebe a mensagem já renderizada do nicho e pede ao Claude para adaptá-la a
ESTE lead, mantendo: curto, sem jargão, assinatura real e a linha de opt-out
(LGPD). É o que transforma 'disparo idêntico' em 'parece escrito à mão'.

Degradação graciosa: sem ANTHROPIC_API_KEY ou sem o SDK instalado, retorna a
mensagem renderizada inalterada (personalizada_por_llm=False). O pipeline segue.
"""
from __future__ import annotations

from ..config import Config
from ..storage.models import Lead, Mensagem

_SYSTEM = (
    "Você é redator de cold e-mail B2B de uma consultoria de modelagem "
    "financeira e pricing. Adapte o e-mail recebido para o destinatário "
    "específico. REGRAS RÍGIDAS: (1) abra pela dor do prospect, não pela bio; "
    "(2) NÃO invente fatos, números ou elogios — use só o que for fornecido; "
    "(3) mantenha curto, skimmável em 15s; (4) sem jargão de método "
    "(elasticidade, posicionamento); (5) mantenha o resultado do case se houver; "
    "(6) PRESERVE a assinatura e a linha final de opt-out; (7) responda APENAS no "
    "formato:\nASSUNTO: <linha>\nCORPO:\n<corpo>"
)


def personalizar(lead: Lead, base: Mensagem, cfg: Config) -> Mensagem:
    chave = cfg.env("ANTHROPIC_API_KEY")
    if not chave:
        return base  # fallback: template renderizado, sem LLM
    try:
        import anthropic
    except ImportError:
        return base

    modelo = cfg.get("ferramentas", "modelo_llm", default="claude-sonnet-4-6")
    contexto = (
        f"Empresa: {lead.empresa.nome}\n"
        f"Setor (CNAE {lead.empresa.cnae}): {base.template_key}\n"
        f"Cargo do contato: {lead.contato.cargo or 'desconhecido'}\n"
        f"Nome do contato: {lead.contato.nome or 'desconhecido'}\n"
        f"Cidade/UF: {lead.empresa.cidade}/{lead.empresa.uf}\n"
        f"Detalhe observado: (nenhum fornecido — NÃO invente)\n\n"
        f"E-MAIL BASE A ADAPTAR:\nASSUNTO: {base.assunto}\nCORPO:\n{base.corpo}"
    )

    try:
        client = anthropic.Anthropic(api_key=chave)
        resp = client.messages.create(
            model=modelo,
            max_tokens=800,
            system=_SYSTEM,
            messages=[{"role": "user", "content": contexto}],
        )
        texto = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
    except Exception:
        return base  # qualquer falha de API -> usa o template renderizado

    assunto, corpo = _parse(texto, base)
    return Mensagem(
        canal=base.canal,
        assunto=assunto,
        corpo=corpo,
        variante=base.variante,
        template_key=base.template_key,
        personalizada_por_llm=True,
    )


def _parse(texto: str, base: Mensagem) -> tuple[str, str]:
    """Extrai ASSUNTO/CORPO do retorno; se não casar, mantém o base."""
    assunto, corpo = base.assunto, base.corpo
    if "CORPO:" in texto:
        cabeca, _, resto = texto.partition("CORPO:")
        corpo = resto.strip()
        for linha in cabeca.splitlines():
            if linha.strip().upper().startswith("ASSUNTO:"):
                assunto = linha.split(":", 1)[1].strip()
                break
    return assunto or base.assunto, corpo or base.corpo
