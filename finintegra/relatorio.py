"""Gera uma imagem-relatório (PNG) com o resumo da base de prospecção, para
enviar aos sócios. Roda a análise da Receita e desenha o painel com matplotlib.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .analise import _CNAE_NOMES, rodar_analise
from .config import Config

_AZUL = "#2f7bf6"
_ESCURO = "#1f2328"
_CINZA = "#6b7280"
_VERDE = "#1c7a3f"
_CARD_BG = "#f3f7fc"
_CARD_BD = "#dfe6ef"

_NOMES_TIER = {
    "agro": "Agronegócio",
    "tier1": "Autopeças, metal\ne plástico",
    "tier2": "Alimentos e\nmáquinas",
    "tier3": "Confecção, móveis\ne construção",
    "?": "Outros",
}


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def gerar_relatorio(cfg: Config) -> Path:
    d = rodar_analise(cfg)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    total = max(1, d["total"])
    fig = plt.figure(figsize=(12, 8), dpi=160)
    fig.patch.set_facecolor("white")

    bg = fig.add_axes([0, 0, 1, 1])
    bg.set_xlim(0, 1); bg.set_ylim(0, 1); bg.axis("off")

    # --- cabeçalho ---
    bg.text(0.05, 0.935, "Base de Prospecção B2B", fontsize=26, fontweight="bold", color=_ESCURO)
    bg.text(0.05, 0.892, "Empresas-alvo · dados públicos da Receita Federal",
            fontsize=13, color=_CINZA)
    try:
        logo = plt.imread(str(cfg.root / "assets" / "logo_email.png"))
        fig.figimage(logo, xo=fig.bbox.xmax - logo.shape[1] - 55,
                     yo=fig.bbox.ymax - logo.shape[0] - 45, zorder=5)
    except Exception:
        pass

    # --- KPI cards ---
    kpis = [
        (_fmt(d["total"]), "empresas (CNPJ)", _AZUL),
        (f'{_fmt(d["com_email"])}', f'com e-mail · {100*d["com_email"]/total:.0f}%', _VERDE),
        (f'{_fmt(d["com_tel"])}', f'com telefone · {100*d["com_tel"]/total:.0f}%', _VERDE),
        (f'{_fmt(d["proprio"])}', f'e-mail próprio · {100*d["proprio"]/total:.0f}%', _AZUL),
    ]
    x0, w, gap, y0, h = 0.05, 0.213, 0.017, 0.70, 0.135
    for i, (num, lab, cor) in enumerate(kpis):
        x = x0 + i * (w + gap)
        bg.add_patch(FancyBboxPatch((x, y0), w, h, boxstyle="round,pad=0.008,rounding_size=0.02",
                                    facecolor=_CARD_BG, edgecolor=_CARD_BD, linewidth=1.2))
        bg.text(x + w / 2, y0 + 0.078, num, fontsize=27, fontweight="bold",
                color=cor, ha="center", va="center")
        bg.text(x + w / 2, y0 + 0.028, lab, fontsize=11.5, color=_CINZA, ha="center", va="center")

    # --- gráfico 1: por segmento ---
    ax1 = fig.add_axes([0.06, 0.11, 0.40, 0.44])
    itens = sorted(d["por_tier"].items(), key=lambda kv: kv[1], reverse=True)
    nomes = [_NOMES_TIER.get(t, t) for t, _ in itens]
    vals = [v for _, v in itens]
    barras = ax1.bar(range(len(vals)), vals, color=_AZUL, width=0.62)
    ax1.set_xticks(range(len(vals)))
    ax1.set_xticklabels(nomes, fontsize=9.5, color=_ESCURO)
    for b, v in zip(barras, vals):
        ax1.text(b.get_x() + b.get_width() / 2, v, f"  {_fmt(v)}\n  {100*v/total:.0f}%",
                 ha="center", va="bottom", fontsize=9.5, color=_ESCURO)
    ax1.set_ylim(0, max(vals) * 1.22)
    ax1.set_title("Empresas por segmento", fontsize=13, fontweight="bold",
                  color=_ESCURO, loc="left", pad=10)
    for s in ("top", "right", "left"):
        ax1.spines[s].set_visible(False)
    ax1.set_yticks([]); ax1.tick_params(length=0)

    # --- gráfico 2: principais CNAEs ---
    ax2 = fig.add_axes([0.57, 0.11, 0.38, 0.44])
    todos: Counter = Counter()
    for c in d["sub_cnae"].values():
        todos.update(c)
    top = todos.most_common(8)[::-1]
    labels = [_CNAE_NOMES.get(g, g) for g, _ in top]
    tvals = [q for _, q in top]
    barsh = ax2.barh(range(len(tvals)), tvals, color=_AZUL, height=0.66)
    ax2.set_yticks(range(len(tvals)))
    ax2.set_yticklabels(labels, fontsize=10, color=_ESCURO)
    for b, v in zip(barsh, tvals):
        ax2.text(v, b.get_y() + b.get_height() / 2, f" {_fmt(v)}",
                 va="center", ha="left", fontsize=9.5, color=_ESCURO)
    ax2.set_xlim(0, max(tvals) * 1.16)
    ax2.set_title("Principais setores (CNAE)", fontsize=13, fontweight="bold",
                  color=_ESCURO, loc="left", pad=10)
    for s in ("top", "right", "bottom"):
        ax2.spines[s].set_visible(False)
    ax2.set_xticks([]); ax2.tick_params(length=0)

    # --- rodapé ---
    bg.text(0.05, 0.045,
            "Filtros: setores-alvo (CNAE) · SP, MG, RS e SC · empresas ativas · "
            "porte EPP/Demais (sem MEI).",
            fontsize=9.5, color=_CINZA)
    bg.text(0.05, 0.018,
            f"Amostra de 1 dos 10 arquivos da base nacional (≈ 1/10 do Brasil) — "
            f"o total nacional é da ordem de {_fmt(d['total']*10)}+ empresas.",
            fontsize=9.5, color=_CINZA)

    out = cfg.root / "data" / "relatorio_prospeccao.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    return out
