"""Geração de saída por lead:
  - o E-MAIL HTML LIMPO (só o conteúdo que vai ao cliente) -> arquivo NN_empresa.html
  - a FICHA de dados coletados (referência do operador) -> arquivo NN_empresa_dados.html

`selecionar_leads` é reusado pelo envio de teste (cli enviar-teste).
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .config import Config
from .enrichment import enriquecer_lead
from .messaging import email_para_html, personalizar, preencher_exemplos_se_vazio, render_mensagem
from .routing import escolher_canal
from .sourcing import get_provider
from .sourcing.base import ICPFilter
from .storage.models import Channel, Lead
from .validation import get_validator
from .validation.mock import MockValidator


def _preparar_lead(lead: Lead, cfg: Config, usar_llm: bool) -> Lead:
    lead.tier = cfg.cnae_tier(lead.empresa.cnae) or ""
    enriquecer_lead(lead)
    # seleção usa validação RÁPIDA (heurística) — a validação REAL (API paga)
    # roda só nos finalistas, antes do envio (ver validar_reais).
    melhor = MockValidator(cfg).melhor(lead.contato.email_candidatos)
    if melhor is not None:
        lead.contato.email = melhor.email
        lead.contato.email_status = melhor.status
        lead.contato.email_score = melhor.score
    lead.canal = escolher_canal(lead, cfg) or Channel.EMAIL.value
    base = render_mensagem(lead, cfg)
    lead.mensagem = personalizar(lead, base, cfg) if usar_llm else base
    return lead


_MX_CACHE: dict[str, bool] = {}

# Quantas reprovações de MX seguidas antes de assumir que o problema é o DNS
# local, e não os domínios (ver o disjuntor em validar_reais).
_MX_FALHAS_SEGUIDAS_MAX = 15


def _tem_mx(dom: str) -> bool:
    """O domínio consegue receber e-mail? (checa registro MX; grátis, via DNS).
    Em caso de erro de rede, não reprova (retorna True) para não falso-negativar."""
    dom = (dom or "").strip().lower()
    if dom in _MX_CACHE:
        return _MX_CACHE[dom]
    try:
        import dns.resolver
        try:
            resp = dns.resolver.resolve(dom, "MX")
            ok = len(resp) > 0
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            ok = False          # domínio não existe / sem servidor de e-mail
        except Exception:
            # timeout, rede fora, NoNameservers ("nenhum DNS respondeu"): NÃO
            # reprova. NoNameservers já derrubou a fila inteira uma vez: a tarefa
            # agendada rodou logo após o PC acordar, com a rede ainda subindo, e
            # 498 leads bons foram para a supressão, que é irreversível.
            ok = True
    except ImportError:
        ok = True               # sem dnspython: pula a checagem
    _MX_CACHE[dom] = ok
    return ok


def validar_reais(cfg: Config, leads: list[Lead], n: int) -> tuple[list[Lead], list[Lead]]:
    """Valida DE VERDADE o e-mail escolhido de cada lead, até juntar `n` aprovados.
    Econômico em crédito: checa o MX (grátis) ANTES de gastar 1 crédito de API, e
    valida só o melhor e-mail do lead (não todos os candidatos). Retorna
    (aprovados, reprovados) — os reprovados vão para a supressão."""
    val = get_validator(cfg)   # real se ferramentas.verificador_email != "mock"
    aprovados: list[Lead] = []
    reprovados: list[Lead] = []
    mx_seguidos = 0
    for lead in leads:
        email = (lead.contato.email or "").strip()
        dom = email.split("@", 1)[1] if "@" in email else ""
        if not dom or not _tem_mx(dom):       # domínio morto -> reprova de graça
            reprovados.append(lead)
            mx_seguidos += 1
            # DISJUNTOR: dezenas de domínios seguidos sem MX não é coincidência,
            # é o DNS fora do ar. Reprovar vai para a supressão e é irreversível,
            # então na dúvida aborta a rodada SEM marcar ninguém como inválido.
            if mx_seguidos >= _MX_FALHAS_SEGUIDAS_MAX:
                print(f"[erro] {mx_seguidos} domínios seguidos sem MX — o DNS "
                      f"provavelmente está fora do ar. Rodada abortada, nenhum "
                      f"lead foi marcado como inválido. Tente de novo mais tarde.")
                return aprovados, []
            continue
        mx_seguidos = 0
        try:
            res = val.validate(email)         # 1 crédito
        except Exception as e:                # ex.: sem crédito -> para e envia o que passou
            print(f"[aviso] validação interrompida ({e}). Enviando o que já foi aprovado.")
            break
        if res.enviavel:
            lead.contato.email_status = "valid"
            lead.contato.email_score = res.score
            aprovados.append(lead)
        else:
            reprovados.append(lead)
        if len(aprovados) >= n:
            break
    return aprovados, reprovados


def selecionar_leads(cfg: Config, n: int, usar_llm: bool = False,
                     tiers: list[str] | None = None, fator: int = 6,
                     so_dominio_proprio: bool = True,
                     excluir_contatados: bool = True) -> tuple[list[Lead], list[str]]:
    """Sourcing + processamento + ranking. Retorna (melhores leads roteados para
    e-mail, campos preenchidos com exemplo). Reusado por `exportar`, envio de
    teste e envio real. `tiers` restringe os setores (ex.: só industrial).
    `so_dominio_proprio`: True = só e-mail no domínio da empresa; False = só os
    de gmail/contador (domínio não-próprio).
    `excluir_contatados`: True remove quem já está em enviados.csv (envio direto).
    False mantém (a FILA precisa deles para a lista de ligação; o `rodar` filtra
    os contatados na hora de enviar, então não há risco de reenvio)."""
    exemplos = preencher_exemplos_se_vazio(cfg)
    provider = get_provider(cfg)
    f = ICPFilter.from_config(cfg, alvo_final=max(n * fator, 30), tiers=tiers)

    # exclui empresas já contatadas (não reenviar)
    from .supressao import carregar_suprimidos, ja_enviado
    cnpjs_env, emails_env = carregar_suprimidos(cfg)

    candidatos: list[Lead] = []
    for lead in provider.search(f):
        _preparar_lead(lead, cfg, usar_llm)
        if lead.canal != Channel.EMAIL.value:
            continue
        if not _nome_valido(lead):          # sem razão social -> corpo sairia quebrado
            continue
        if _em_dificuldade(lead.empresa.nome):   # recuperação judicial/falência: sem caixa
            continue
        if not _email_ok(lead.contato.email):   # formato de e-mail inválido
            continue
        # próprio = domínio da empresa; invertemos conforme o pedido
        if _email_da_empresa(lead) != so_dominio_proprio:
            continue
        if excluir_contatados and ja_enviado(lead, cnpjs_env, emails_env):
            continue
        candidatos.append(lead)

    # ordena pelos que MAIS se encaixam no ICP e têm maior chance de virar cliente
    candidatos.sort(key=_score_icp, reverse=True)
    return candidatos[:n], exemplos


# pesos do ranking: quanto maior, mais cedo a empresa é contatada
_PESO_TIER = {"tier1": 6, "tier2": 4, "tier3": 2}


def _score_icp(l: Lead) -> int:
    """Ranqueia por encaixe no ICP + probabilidade de fechar (melhor = primeiro)."""
    e = l.empresa
    s = _PESO_TIER.get(l.tier, 0)                 # setor de melhor encaixe primeiro
    # porte / capital social (quem tem músculo para pagar)
    if e.porte == "Demais":
        s += 3
    elif e.porte == "EPP":
        s += 1
    cap = e.capital_social or 0
    s += 4 if cap >= 1_000_000 else 3 if cap >= 300_000 else 2 if cap >= 100_000 else 0
    # qualidade do contato
    if _nome_no_dominio(e.nome, (e.dominio or "").lower()):
        s += 3                                    # domínio claramente da empresa
    if l.contato.nome:
        s += 2                                    # sabemos quem é o decisor (sócio)
    if l.contato.telefone:
        s += 1                                    # alcançável também por telefone
    return s


def exportar(cfg: Config, n: int = 1, usar_llm: bool = False) -> list[Path]:
    """Gera, por lead: o e-mail limpo (NN_empresa.html) + a ficha (NN_empresa_dados.html)."""
    leads, exemplos = selecionar_leads(cfg, n, usar_llm)
    out_dir = cfg.root / "data" / "emails"
    out_dir.mkdir(parents=True, exist_ok=True)
    gerados: list[Path] = []
    for idx, lead in enumerate(leads, start=1):
        slug = _slug(lead.empresa.nome)
        email_path = out_dir / f"{idx:02d}_{slug}.html"
        email_path.write_text(email_para_html(lead.mensagem, cfg), encoding="utf-8")  # LIMPO
        ficha_path = out_dir / f"{idx:02d}_{slug}_dados.html"
        ficha_path.write_text(_ficha_doc(lead, exemplos), encoding="utf-8")
        gerados.append(email_path)
    return gerados


# -----------------------------------------------------------------------------
# Ficha de dados (arquivo separado do e-mail; referência do operador)
# -----------------------------------------------------------------------------
def _ficha_doc(lead: Lead, exemplos: list[str]) -> str:
    msg = lead.mensagem
    assert msg is not None
    aviso = ""
    if exemplos:
        campos = ", ".join(exemplos)
        aviso = (
            f'<div class="aviso">⚠ No e-mail, os campos <code>{html.escape(campos)}'
            f'</code> estão vazios no config e foram preenchidos com <b>exemplo</b>.</div>'
        )
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dados — {html.escape(lead.empresa.nome)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         background:#f4f5f7; color:#1f2328; margin:0; padding:24px; line-height:1.6; }}
  .wrap {{ max-width:720px; margin:0 auto; }}
  h1 {{ font-size:16px; font-weight:600; margin:0 0 12px; color:#3a3f45;
       text-transform:uppercase; letter-spacing:.04em; }}
  .aviso {{ background:#fff8e1; border:1px solid #f0d27a; color:#6b5300;
           padding:10px 14px; border-radius:8px; font-size:13px; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:12px;
          overflow:hidden; border:1px solid #e3e6ea; font-size:13.5px; margin-bottom:12px; }}
  caption {{ text-align:left; font-weight:600; color:#5b6168; padding:12px 14px 4px;
            background:#fafbfc; }}
  td {{ padding:8px 14px; border-top:1px solid #eef0f2; vertical-align:top; }}
  td.k {{ color:#8a9099; width:190px; white-space:nowrap; }}
  td.v {{ color:#2b2f36; word-break:break-word; }}
  .pill {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; }}
  .ok {{ background:#e3f5e9; color:#1c7a3f; }}
  .warn {{ background:#fdeaea; color:#b3261e; }}
  code {{ background:#eef0f2; padding:1px 5px; border-radius:4px; font-size:12px; }}
</style></head>
<body><div class="wrap">
  <h1>Dados coletados — {html.escape(lead.empresa.nome)}</h1>
  {aviso}
  {_tabela_empresa(lead)}
  {_tabela_contato(lead)}
  {_tabela_pipeline(lead, msg)}
</div></body></html>"""


def _linha(k: str, v) -> str:
    if v is None or v == "":
        v = "—"
    return f'<tr><td class="k">{html.escape(k)}</td><td class="v">{v}</td></tr>'


def _esc(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else "—"


def _tabela_empresa(lead: Lead) -> str:
    e = lead.empresa
    tier = lead.tier or "—"
    return f"""<table><caption>Empresa</caption>
    {_linha("Razão social", _esc(e.nome))}
    {_linha("CNPJ", _esc(e.cnpj))}
    {_linha("CNAE", _esc(e.cnae))}
    {_linha("Tier (encaixe ICP)", _esc(tier))}
    {_linha("Domínio", _esc(e.dominio))}
    {_linha("Funcionários", _esc(e.funcionarios))}
    {_linha("Capital social", _fmt_capital(e.capital_social))}
    {_linha("Porte", _esc(e.porte))}
    {_linha("Cidade / UF", f"{_esc(e.cidade)} / {_esc(e.uf)}")}
    {_linha("Região", _esc(e.regiao))}
    </table>"""


def _tabela_contato(lead: Lead) -> str:
    c = lead.contato
    status_cls = "ok" if c.email_status == "valid" else "warn"
    status = f'<span class="pill {status_cls}">{_esc(c.email_status)}</span>'
    score = f"{c.email_score:.2f}" if c.email_score is not None else "—"
    cands = ", ".join(c.email_candidatos) or "—"
    return f"""<table><caption>Contato / decisor</caption>
    {_linha("Nome", _esc(c.nome))}
    {_linha("Cargo", _esc(c.cargo))}
    {_linha("E-mail escolhido", _esc(c.email))}
    {_linha("Status de validação", f"{status} (score {score})")}
    {_linha("Candidatos de e-mail", html.escape(cands))}
    {_linha("Telefone", _esc(c.telefone))}
    {_linha("LinkedIn", _esc(c.linkedin_url))}
    </table>"""


def _tabela_pipeline(lead: Lead, msg) -> str:
    llm = "sim" if msg.personalizada_por_llm else "não (template)"
    return f"""<table><caption>Roteamento e mensagem</caption>
    {_linha("Status no pipeline", _esc(lead.status))}
    {_linha("Canal escolhido", _esc(lead.canal))}
    {_linha("Template de nicho", _esc(msg.template_key))}
    {_linha("Variante de copy", _esc(msg.variante))}
    {_linha("Personalizado por LLM", _esc(llm))}
    {_linha("Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M"))}
    </table>"""


# webmail pessoal e sinais de e-mail de contador (não são domínio da empresa)
_WEBMAIL = {
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br",
    "bol.com.br", "uol.com.br", "terra.com.br", "terra.com", "ig.com.br",
    "live.com", "icloud.com", "msn.com", "globo.com", "maismei.com.br",
    "net11.com.br", "superig.com.br", "bewnet.com.br", "mko.com.br",
}
_CONTADOR_SINAIS = ("contab", "assessor", "escritorio", "cont.")
# palavras genéricas que NÃO valem como "combinação" nome<->domínio
_STOP = {
    "industria", "comercio", "comercial", "industrial", "ltda", "eireli", "sa",
    "brasil", "servicos", "servico", "produtos", "produto", "distribuidora",
    "distribuicao", "importacao", "exportacao", "representacoes", "solucoes",
    "tecnologia", "nacional", "grupo", "companhia", "sociedade", "auto", "filial",
    "pneus", "santa", "clara", "nova", "central", "acos", "metais",
}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# domínios descartáveis/temporários (e-mail "de mentira")
_DESCARTAVEL = {
    "mailinator.com", "tempmail.com", "temp-mail.org", "guerrillamail.com",
    "10minutemail.com", "yopmail.com", "trashmail.com", "getnada.com",
    "sharklasers.com", "throwawaymail.com", "maildrop.cc", "mailnesia.com",
    "dispostable.com", "fakeinbox.com", "mvrht.com", "spam4.me",
}
# typos comuns de provedores (domínio quase certo que não existe)
_TYPO = {
    "gmailcom", "gmail.con", "gmail.co", "gmai.com", "gnail.com", "gmial.com",
    "hotmailcom", "hotmail.con", "hotmial.com", "outlok.com", "outlookcom",
    "yahoocom", "yaho.com", "terra.combr", "bol.combr",
}


def _sem_acento(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _email_ok(email: str) -> bool:
    """Formato válido + não descartável/temporário + sem typo óbvio de provedor."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return False
    dom = email.split("@", 1)[1]
    if dom in _DESCARTAVEL or dom in _TYPO:
        return False
    if ".." in dom or not dom.split(".")[-1].isalpha() or len(dom.split(".")[-1]) < 2:
        return False
    return True


def _dominio_proprio(dom: str) -> bool:
    if not dom or dom in _WEBMAIL:
        return False
    return not any(sig in dom for sig in _CONTADOR_SINAIS)


def _nome_no_dominio(nome: str, dom: str) -> bool:
    """True se um token distintivo do nome da empresa aparece no domínio."""
    base = _sem_acento(dom.split(".")[0]).lower()
    for tok in _sem_acento(nome).lower().split():
        tok = "".join(c for c in tok if c.isalnum())
        if len(tok) >= 4 and tok not in _STOP and tok in base:
            return True
    return False


def _nome_valido(lead: Lead) -> bool:
    nome = (lead.empresa.nome or "").strip().lower()
    return bool(nome) and nome != "(sem nome)"


# empresas em crise não têm caixa para contratar consultoria — fora do ICP
_DIFICULDADE = ("recuperacao judicial", "recuperacao extrajudicial",
                "massa falida", "em liquidacao", "em falencia")


def _em_dificuldade(nome: str) -> bool:
    n = _sem_acento(nome or "").lower()
    return any(s in n for s in _DIFICULDADE)


def _email_da_empresa(lead: Lead) -> bool:
    """Aceita só e-mail com formato válido, domínio próprio (não webmail/contador)
    E cujo domínio combine com o nome da empresa (exclui e-mail de terceiro)."""
    email = (lead.contato.email or "").strip().lower()
    if not _email_ok(email):
        return False
    dom = email.split("@", 1)[1]
    return _dominio_proprio(dom) and _nome_no_dominio(lead.empresa.nome, dom)


def _fmt_capital(v) -> str:
    if v in (None, "", 0):
        return "—"
    return f"R$ {v:,.0f}".replace(",", ".")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower())[:30]
