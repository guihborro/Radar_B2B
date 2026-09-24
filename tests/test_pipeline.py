"""Testes do pipeline Outreach. Rodam 100% offline (provedor/validador mock).

    python -m pytest        (com pytest instalado)
ou  python tests/test_pipeline.py   (runner embutido, sem dependências)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finintegra.config import load_config
from finintegra.enrichment.email_patterns import gerar_candidatos_email
from finintegra.routing.cascade import escolher_canal
from finintegra.storage.models import Channel, Contato, Empresa, Lead
from finintegra.validation.mock import MockValidator
from finintegra.validation.base import STATUS_INVALID
from finintegra.messaging.render import render_mensagem
from finintegra.pipeline import run


def test_email_patterns_ordem_e_acentos():
    cands = gerar_candidatos_email("José da Silva", "Acme.com.BR")
    assert cands[0] == "jose.silva@acme.com.br"      # mais comum primeiro
    assert "jsilva@acme.com.br" in cands             # flast
    assert all("@acme.com.br" in c for c in cands)   # acento removido, domínio normalizado


def test_email_patterns_sem_dados():
    assert gerar_candidatos_email("", "acme.com") == []
    assert gerar_candidatos_email("Ana", "") == []


def test_validator_mock_sintaxe_invalida():
    cfg = load_config()
    r = MockValidator(cfg).validate("nao-eh-email")
    assert r.status == STATUS_INVALID
    assert not r.enviavel


def test_cascade_email_so_se_validado():
    cfg = load_config()
    lead = Lead(empresa=Empresa(nome="X"), contato=Contato(
        email="a@x.com", email_status="unknown", telefone="+55 11 90000-0000"))
    # e-mail não validado -> cai para telefone
    assert escolher_canal(lead, cfg) == Channel.PHONE.value
    lead.contato.email_status = "valid"
    assert escolher_canal(lead, cfg) == Channel.EMAIL.value


def test_cascade_sem_canal_retorna_none():
    cfg = load_config()
    lead = Lead(empresa=Empresa(nome="X"), contato=Contato())
    assert escolher_canal(lead, cfg) is None


def test_render_preenche_placeholders():
    cfg = load_config()
    lead = Lead(empresa=Empresa(nome="Usimetal", cnae="25"),
                contato=Contato(nome="Carlos Souza"), canal="email")
    msg = render_mensagem(lead, cfg)
    assert "Usimetal" in msg.assunto
    assert "Usimetal" in msg.corpo                    # empresa aparece no corpo (CTA)
    assert "{{" not in msg.corpo                      # nenhum placeholder solto
    assert msg.template_key == "usinagem"             # CNAE 25 -> usinagem


def test_cnae_tier_por_prefixo():
    cfg = load_config()
    assert cfg.cnae_tier("2542-0/00") == "tier1"      # casa prefixo 25
    assert cfg.cnae_tier("9999") is None


def test_pipeline_roda_ponta_a_ponta(tmp_path_factory=None):
    cfg = load_config()
    # teste de lógica do pipeline: independe do provedor/verificador do deploy
    cfg.raw["ferramentas"]["provedor_dados"] = "mock"
    cfg.raw["ferramentas"]["verificador_email"] = "mock"
    # redireciona o banco para um arquivo temporário de teste
    cfg.raw.setdefault("storage", {})["db_path"] = "data/_teste_pipeline.sqlite"
    res = run(cfg, alvo_final=10, enviar=True)
    assert res.total > 0
    assert res.total == res.rejeitados + sum(res.roteados.values())
    # trava de envio é a assinatura (negocio.contato): preenchida -> dry-run envia
    # todos os leads de e-mail; vazia -> bloqueia todos
    if cfg.get("negocio", "contato", default="").strip():
        assert res.enviados == res.roteados.get("email", 0)
    else:
        assert res.enviados == 0
    (cfg.root / "data" / "_teste_pipeline.sqlite").unlink(missing_ok=True)


def _run_all():
    import inspect
    mod = sys.modules[__name__]
    falhas = 0
    for nome, fn in sorted(inspect.getmembers(mod, inspect.isfunction)):
        if not nome.startswith("test_"):
            continue
        try:
            fn()
            print(f"  PASS {nome}")
        except AssertionError as e:
            falhas += 1
            print(f"  FAIL {nome}: {e}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"  ERRO {nome}: {type(e).__name__}: {e}")
    print(f"\n{'OK' if falhas == 0 else 'FALHOU'} — {falhas} falha(s)")
    return falhas


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
