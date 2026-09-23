"""Valida o ReceitaFederalProvider com arquivos sintéticos no layout do open data.
Não baixa nada — escreve CSVs no formato da Receita num diretório temporário.

    python tests/test_receita.py    (runner embutido)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finintegra.config import load_config
from finintegra.sourcing import get_provider
from finintegra.sourcing.base import ICPFilter


def _est_row(base, fantasia, situacao, cnae, uf, ddd, tel, email):
    row = [""] * 30
    row[0], row[1], row[2], row[3] = base, "0001", "00", "1"
    row[4], row[5], row[11] = fantasia, situacao, cnae
    row[19], row[20], row[21], row[22], row[27] = uf, "1234", ddd, tel, email
    return ";".join(row)


def _emp_row(base, razao, porte):
    row = [""] * 7
    row[0], row[1], row[4], row[5] = base, razao, "100000,00", porte
    return ";".join(row)


def _soc_row(base, ident, nome):
    row = [""] * 11
    row[0], row[1], row[2] = base, ident, nome
    return ";".join(row)


def _montar(pasta: Path):
    est = [
        # A: CNAE 25 (tier1), SP, ativa  -> deve passar
        _est_row("11111111", "Usimetal A", "02", "2542000", "SP", "11", "33334444", "contato@usimetala.com.br"),
        # B: CNAE 47 (fora do alvo)      -> filtrado por CNAE
        _est_row("22222222", "Mercado B", "02", "4711301", "SP", "11", "0", "x@b.com.br"),
        # C: CNAE 22 mas UF BA           -> filtrado por UF
        _est_row("33333333", "Plast C", "02", "2229300", "BA", "71", "0", "x@c.com.br"),
        # D: CNAE 25, RS, porte ME (01)  -> filtrado por porte
        _est_row("44444444", "Metal D", "02", "2542000", "RS", "51", "0", "x@d.com.br"),
        # E: CNAE 28 (tier2), MG, Demais -> deve passar
        _est_row("55555555", "Maquinas E", "02", "2811900", "MG", "31", "55556666", "vendas@maquinase.com.br"),
        # F: CNAE 25, SP, mas INATIVA    -> filtrado por situação
        _est_row("66666666", "Inativa F", "08", "2542000", "SP", "11", "0", "x@f.com.br"),
    ]
    emp = [
        _emp_row("11111111", "USIMETAL INDUSTRIA LTDA", "03"),  # EPP
        _emp_row("44444444", "METAL D ME", "01"),               # ME -> some
        _emp_row("55555555", "MAQUINAS E SA", "05"),            # Demais
    ]
    soc = [
        _soc_row("11111111", "2", "JOAO DA SILVA"),   # PF
        _soc_row("55555555", "1", "HOLDING XPTO"),    # PJ -> ignorado
        _soc_row("55555555", "2", "MARIA SOUZA"),     # PF
    ]
    (pasta / "K0.ESTABELE").write_text("\n".join(est), encoding="latin-1")
    (pasta / "K0.EMPRECSV").write_text("\n".join(emp), encoding="latin-1")
    (pasta / "K0.SOCIOCSV").write_text("\n".join(soc), encoding="latin-1")


def test_receita_filtra_e_mapeia():
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        _montar(pasta)
        cfg = load_config()
        cfg.raw["ferramentas"]["provedor_dados"] = "receita"
        cfg.raw["receita"] = {"pasta": str(pasta), "portes": ["03", "05"], "situacao_ativa": True}

        prov = get_provider(cfg)
        leads = prov.search(ICPFilter.from_config(cfg, alvo_final=20))

        nomes = sorted(l.empresa.nome for l in leads)
        assert nomes == ["MAQUINAS E SA", "USIMETAL INDUSTRIA LTDA"], nomes

        def base8(cnpj: str) -> str:
            return "".join(c for c in cnpj if c.isdigit())[:8]
        by = {base8(l.empresa.cnpj): l for l in leads}
        a = by["11111111"]
        assert a.empresa.cnae == "2542000"
        assert a.empresa.dominio == "usimetala.com.br"          # domínio do e-mail
        assert a.empresa.porte == "EPP"
        assert a.contato.nome == "Joao Da Silva"                 # sócio PF
        assert a.contato.telefone == "+55 11 33334444"
        assert a.contato.email_candidatos == ["contato@usimetala.com.br"]

        e = by["55555555"]
        assert e.contato.nome == "Maria Souza"                   # ignora o sócio PJ


def test_receita_sem_arquivos_erro_claro():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config()
        cfg.raw["receita"] = {"pasta": str(tmp)}
        prov = get_provider(cfg)
        try:
            prov.search(ICPFilter.from_config(cfg, alvo_final=5))
            assert False, "deveria ter levantado RuntimeError"
        except RuntimeError as e:
            assert "ESTABELE" in str(e)


def _run_all():
    import inspect
    falhas = 0
    for nome, fn in sorted(inspect.getmembers(sys.modules[__name__], inspect.isfunction)):
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
