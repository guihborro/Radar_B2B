"""CLI do FinIntegra.

Uso:
    python -m finintegra.cli rodar [--alvo 50] [--no-enviar]
    python -m finintegra.cli auditar
    python -m finintegra.cli status
    python -m finintegra.cli preview [--n 3]    # mostra mensagens sem persistir
"""
from __future__ import annotations

import argparse
import sys

from .audit import auditar
from .config import load_config
from .export_html import exportar, selecionar_leads
from .sending import get_sender
from .messaging import render_mensagem
from .pipeline import run
from .routing import escolher_canal
from .enrichment import enriquecer_lead
from .sourcing import get_provider
from .sourcing.base import ICPFilter
from .storage import Repository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finintegra", description="Prospecção FinIntegra")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # opção comum a todos os comandos: sobrescreve o provedor de dados na hora
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--provedor", default=None,
                        help="sobrescreve ferramentas.provedor_dados (ex.: mock, receita)")

    p_run = sub.add_parser("rodar", parents=[common],
                           help="ENVIA 100 e-mails a empresas industriais (via SMTP)")
    p_run.add_argument("--n", type=int, default=100, help="quantas empresas (padrão 100)")
    p_run.add_argument("--no-enviar", action="store_true", help="só mostra a prévia, não envia")
    p_run.add_argument("--sem-proprio", action="store_true",
                       help="envia para os SEM domínio próprio (gmail/contador), não para os de qualidade")
    p_run.add_argument("--sem-followup", action="store_true",
                       help="não envia follow-ups nesta rodada (só contatos novos)")
    p_run.add_argument("--llm", action="store_true", help="personaliza via Claude API")

    sub.add_parser("auditar", parents=[common], help="auditoria de confiabilidade do provedor (§4.3)")
    sub.add_parser("analisar", parents=[common], help="conta empresas-alvo (com e-mail/telefone) na base da Receita")
    sub.add_parser("relatorio", parents=[common], help="gera imagem-relatório (PNG) da base para os sócios")
    sub.add_parser("status", parents=[common], help="contagem de leads por status no banco")

    p_prev = sub.add_parser("preview", parents=[common], help="renderiza mensagens de exemplo")
    p_prev.add_argument("--n", type=int, default=3)

    p_html = sub.add_parser("html", parents=[common], help="gera HTML do e-mail + dados do cliente")
    p_html.add_argument("--n", type=int, default=1, help="quantos HTMLs gerar")
    p_html.add_argument("--llm", action="store_true", help="personaliza via Claude API")

    p_tst = sub.add_parser("enviar-teste", parents=[common],
                           help="envia o e-mail real para um endereço de TESTE (via SMTP)")
    p_tst.add_argument("--para", required=True, help="e-mail de teste que recebe o envio")
    p_tst.add_argument("--n", type=int, default=1, help="quantos e-mails enviar")
    p_tst.add_argument("--llm", action="store_true", help="personaliza via Claude API")

    p_bnc = sub.add_parser("bounce", parents=[common],
                           help="marca e-mails que voltaram (bounce) para nunca mais tentar")
    p_bnc.add_argument("emails", nargs="+", help="e-mails que voltaram")

    sub.add_parser("preparar-fila", parents=[common],
                   help="(re)constrói a fila ranqueada de leads (escaneia a Receita 1x)")

    sub.add_parser("followups", parents=[common],
                   help="agenda da cadência: quem recebe follow-up, em qual etapa e quando")

    sub.add_parser("funil", parents=[common],
                   help="métricas reais: enviados, respostas, bounces, taxa de resposta")

    p_lig = sub.add_parser("ligacoes", parents=[common],
                           help="gera lista de ligação/WhatsApp (tier1 contatado sem resposta)")
    p_lig.add_argument("--completos", action="store_true",
                       help="só quem já passou por TODA a cadência de e-mail")

    p_chk = sub.add_parser("checar-respostas", parents=[common],
                           help="lê a INBOX (IMAP) e marca respostas/bounces automaticamente")
    p_chk.add_argument("--dry-run", action="store_true", help="só mostra, não grava")

    p_resp = sub.add_parser("respondeu", parents=[common],
                            help="marca quem RESPONDEU manualmente (encerra a cadência)")
    p_resp.add_argument("emails", nargs="+", help="e-mails que responderam")

    args = parser.parse_args(argv)
    cfg = load_config()
    if getattr(args, "provedor", None):
        cfg.raw.setdefault("ferramentas", {})["provedor_dados"] = args.provedor
    try:
        return _dispatch(args, cfg)
    except (RuntimeError, FileNotFoundError) as e:
        # erros esperados (ex.: arquivos do provedor ausentes) — sem traceback
        print(f"\n[erro] {e}")
        return 1


def _dispatch(args, cfg) -> int:
    if args.cmd == "rodar":
        from .export_html import validar_reais
        from .fila import construir_fila, existe_fila, ler_fila
        from .followup import devidos as followups_devidos
        from .messaging import preencher_exemplos_se_vazio, render_mensagem
        from .supressao import carregar_suprimidos, enviados_hoje, ja_enviado, registrar
        industriais = ["tier1", "tier2", "tier3"]     # setor industrial (sem agro)
        limite_diario = int(cfg.get("operacao", "limite_diario", default=20))

        # limite diário (aquecimento): não estoura o que o Gmail tolera
        ja = enviados_hoje(cfg)
        alvo = min(args.n, max(0, limite_diario - ja))
        if not args.no_enviar and alvo <= 0:
            print(f"Limite diário de {limite_diario} já atingido hoje ({ja} enviados). "
                  f"Volte amanhã (ou aumente operacao.limite_diario).")
            return 0

        preencher_exemplos_se_vazio(cfg)

        # 1) FOLLOW-UPS têm prioridade: o e-mail já foi validado (não gastam
        #    crédito) e a taxa de resposta da sequência é quase o dobro.
        fups = [] if args.sem_followup else followups_devidos(cfg, limite=alvo)
        restante = max(0, alvo - len(fups))

        # 2) leads novos preenchem o que sobrou do limite do dia
        fila: list = []
        if restante:
            if args.sem_proprio:
                # caminho ao vivo (uso manual raro): varre a Receita na hora
                fila, _ = selecionar_leads(cfg, n=restante * 5, tiers=industriais,
                                           fator=12, so_dominio_proprio=False)
            else:
                # FILA pré-construída: leitura instantânea (o caminho do agendador)
                if not existe_fila(cfg):
                    print("Construindo a fila de leads pela 1ª vez (~1 min, só desta vez)...")
                    print(f"Fila criada com {construir_fila(cfg, industriais)} empresas.")
                cnpjs_env, emails_env = carregar_suprimidos(cfg)
                fila = [l for l in ler_fila(cfg) if not ja_enviado(l, cnpjs_env, emails_env)]
                for l in fila:
                    l.mensagem = render_mensagem(l, cfg)

        if not fups and not fila:
            print("Nada a enviar: nenhum follow-up devido hoje e nenhum lead novo na "
                  "fila. Rode 'preparar-fila' para reconstruir a lista.")
            return 1

        if args.no_enviar:
            print(f"PRÉVIA — nada enviado. Cota de hoje: {alvo} "
                  f"(limite {limite_diario}, já saíram {ja}).\n")
            if fups:
                print(f"  FOLLOW-UPS devidos ({len(fups)}, sem custo de validação):")
                for lead, etapa in fups:
                    print(f"    [etapa {etapa}] {lead.empresa.nome[:34]:34s} -> {lead.contato.email}")
            if fila:
                print(f"\n  LEADS NOVOS ({min(restante, len(fila))} de {len(fila)} na fila):")
                for lead in fila[:restante]:
                    print(f"    {lead.empresa.nome[:38]:38s} -> {lead.contato.email}")
                print("\n  (no envio real, cada lead novo ainda passa pela validação)")
            return 0

        if not cfg.env("SMTP_USUARIO") or not cfg.env("SMTP_SENHA"):
            print("[erro] Preencha SMTP_USUARIO e SMTP_SENHA no .env (a conta que envia).")
            return 1
        if fila and cfg.get("ferramentas", "verificador_email", default="mock") == "mock":
            print("[aviso] verificador_email = 'mock' — a validação NÃO é real e o bounce "
                  "pode voltar. Configure 'neverbounce'/'zerobounce' no config + chave no .env.\n")

        cfg.raw.setdefault("ferramentas", {})["envio"] = "smtp"
        cfg.raw.setdefault("operacao", {})["email_teste"] = ""
        cfg.raw["operacao"]["modo_seguro"] = False
        sender = get_sender(cfg)
        n_fup = n_novos = n_inv = n_falhas = 0

        # --- follow-ups: sem validação, o e-mail já foi validado no 1º envio ---
        if fups:
            print(f"Enviando {len(fups)} follow-up(s) (custo zero em créditos) ...")
            resultados = sender.enviar_lote([l for l, _ in fups], pausa=1.5)
            por_etapa: dict[int, list] = {}
            for (lead, etapa), r in zip(fups, resultados):
                if r.enviado:
                    por_etapa.setdefault(etapa, []).append(lead)
                else:
                    n_falhas += 1
                    print(f"  [falha] {lead.empresa.nome}: {r.detalhe}")
            for etapa, leads_ok in sorted(por_etapa.items()):
                registrar(cfg, leads_ok, f"followup{etapa}")
                n_fup += len(leads_ok)

        # --- leads novos: validação REAL só nos finalistas ---
        if fila and restante:
            print(f"Validando e-mails (real) para separar {restante} lead(s) novo(s) ...")
            aprovados, reprovados = validar_reais(cfg, fila, restante)
            n_inv = registrar(cfg, reprovados, "invalido")   # não retentar
            if aprovados:
                print(f"Enviando {len(aprovados)} e-mail(s) novo(s) via SMTP "
                      f"({cfg.env('SMTP_USUARIO')}) ...")
                resultados = sender.enviar_lote(aprovados, pausa=1.5)
                enviados_ok = [l for l, r in zip(aprovados, resultados) if r.enviado]
                registrar(cfg, enviados_ok, "enviado")
                n_novos = len(enviados_ok)
                for lead, r in zip(aprovados, resultados):
                    if not r.enviado:
                        n_falhas += 1
                        print(f"  [falha] {lead.empresa.nome}: {r.detalhe}")
            else:
                print("Nenhum e-mail novo passou na validação.")

        print(f"\nEnviados: {n_fup + n_novos} "
              f"({n_novos} novo(s) + {n_fup} follow-up(s)) | "
              f"reprovados na validação: {n_inv} | falhas no envio: {n_falhas}")
        print("Registrado em data/enviados.csv (não reenvia).")
        return 0

    if args.cmd == "bounce":
        from .supressao import registrar_emails
        n = registrar_emails(cfg, args.emails, "bounce")
        print(f"{n} e-mail(s) marcados como bounce em data/enviados.csv (não serão mais tentados).")
        return 0

    if args.cmd == "followups":
        from .followup import agenda
        linhas = agenda(cfg)
        if not linhas:
            print("Ninguém na cadência ainda (nenhum 1º e-mail enviado).")
            return 0
        rotulo = {"devido": "DEVIDO HOJE", "aguardando": "aguardando",
                  "concluido": "concluída", "encerrado": "encerrada"}
        fora = [d for d in linhas if d["situacao"] == "fora_padrao"]
        ativos = [d for d in linhas if d["situacao"] != "fora_padrao"]
        for d in ativos:
            quando = "" if d["faltam"] is None else (
                "agora" if d["faltam"] <= 0 else f"em {d['faltam']}d")
            print(f"  {rotulo[d['situacao']]:12s} etapa {d['etapas_enviadas']}/3  "
                  f"{(d['empresa'] or '?')[:30]:30s} {d['email'][:34]:34s} {quando}")
        devidos_hoje = sum(1 for d in ativos if d["situacao"] == "devido")
        print(f"\n{len(ativos)} na cadência | {devidos_hoje} devido(s) hoje "
              f"(o `rodar` envia automaticamente)")
        if fora:
            print(f"{len(fora)} envio(s) antigo(s) fora da cadência "
                  f"(e-mail de contador/terceiro, não recebem follow-up)")
        return 0

    if args.cmd == "funil":
        from .funil import relatorio_texto
        print(relatorio_texto(cfg))
        return 0

    if args.cmd == "ligacoes":
        from .telefone import gerar_lista, salvar_csv
        linhas = gerar_lista(cfg, so_completos=args.completos)
        if not linhas:
            criterio = ("Ninguém completou a cadência de e-mail ainda"
                        if args.completos else
                        "Nenhum tier1 contatado sem resposta com telefone")
            print(f"{criterio}. Nada a ligar por enquanto.")
            return 0
        print(f"LISTA DE LIGAÇÃO/WHATSAPP — {len(linhas)} lead(s) tier1 sem resposta\n")
        for d in linhas:
            print(f"  {d['empresa'][:34]:34s} {d['telefone']:20s} "
                  f"{d['etapas_email']} e-mail(s) | {d['dias_desde_1o']}d")
            if d["decisor"]:
                print(f"     decisor: {d['decisor']}")
            print(f"     gancho:  {d['gancho'][:80]}")
        p = salvar_csv(cfg, linhas)
        print(f"\nSalvo em {p} (abre no Excel, com link de WhatsApp).")
        return 0

    if args.cmd == "checar-respostas":
        from .respostas import detectar
        r = detectar(cfg, dry_run=args.dry_run)
        if r.erro:
            print(f"[erro] {r.erro}")
            return 1
        marca = " (dry-run, nada gravado)" if args.dry_run else ""
        print(f"Lidas {r.lidos} mensagens da INBOX.{marca}")
        print(f"  Respostas: {len(r.respostas)}")
        for e in r.respostas:
            print(f"    respondeu -> {e}")
        print(f"  Bounces: {len(r.bounces)}")
        for e in r.bounces:
            print(f"    bounce    -> {e}")
        if not args.dry_run and (r.respostas or r.bounces):
            print("Registrado em data/enviados.csv (cadência atualizada).")
        return 0

    if args.cmd == "respondeu":
        from .supressao import registrar_emails
        n = registrar_emails(cfg, args.emails, "respondeu")
        print(f"{n} marcado(s) como RESPONDEU — a cadência de follow-up desses para aqui.")
        return 0

    if args.cmd == "preparar-fila":
        from .fila import construir_fila
        print("Escaneando a Receita e ranqueando os leads (~1 min)...")
        total = construir_fila(cfg, ["tier1", "tier2", "tier3"])
        print(f"Fila pronta: {total} empresas ranqueadas em data/fila_leads.jsonl")
        return 0

    if args.cmd == "auditar":
        print(auditar(cfg).resumo())
        return 0

    if args.cmd == "analisar":
        from .analise import rodar_analise
        rodar_analise(cfg)
        return 0

    if args.cmd == "relatorio":
        from .relatorio import gerar_relatorio
        caminho = gerar_relatorio(cfg)
        print(f"\nImagem salva: {caminho}")
        return 0

    if args.cmd == "status":
        repo = Repository(cfg.db_path)
        counts = repo.counts_by_status()
        repo.close()
        if not counts:
            print("Banco vazio. Rode: python -m finintegra.cli rodar")
        else:
            for st, c in sorted(counts.items()):
                print(f"  {st:14s} {c}")
        return 0

    if args.cmd == "html":
        caminhos = exportar(cfg, n=args.n, usar_llm=args.llm)
        if not caminhos:
            print("Nenhum lead roteado para e-mail. Tente --n maior.")
        for p in caminhos:
            print(f"  e-mail: {p}")
            print(f"  dados:  {p.with_name(p.stem + '_dados.html')}")
        return 0

    if args.cmd == "enviar-teste":
        # tudo vai para --para (modo de teste), via SMTP, mesmo com modo_seguro
        cfg.raw.setdefault("operacao", {})["email_teste"] = args.para
        cfg.raw.setdefault("ferramentas", {})["envio"] = "smtp"
        leads, _ = selecionar_leads(cfg, n=args.n, usar_llm=args.llm)
        if not leads:
            print("Nenhum lead roteado para e-mail. Tente --n maior.")
            return 1
        sender = get_sender(cfg)
        print(f"Enviando {len(leads)} e-mail(s) de teste para {args.para} ...")
        for lead in leads:
            r = sender.send(lead)
            marca = "OK " if r.enviado else "FALHA"
            print(f"  [{marca}] {lead.empresa.nome}: {r.detalhe}")
        return 0

    if args.cmd == "preview":
        provider = get_provider(cfg)
        f = ICPFilter.from_config(cfg, alvo_final=args.n)
        f.limite = args.n
        for lead in provider.search(f)[: args.n]:
            lead.tier = cfg.cnae_tier(lead.empresa.cnae) or ""
            enriquecer_lead(lead)
            # força e-mail validado fictício só p/ preview do texto
            if lead.contato.email_candidatos:
                lead.contato.email = lead.contato.email_candidatos[0]
                lead.contato.email_status = "valid"
            lead.canal = escolher_canal(lead, cfg) or "email"
            msg = render_mensagem(lead, cfg)
            print("=" * 70)
            print(f"{lead.empresa.nome} | CNAE {lead.empresa.cnae} | {lead.tier} "
                  f"| canal: {lead.canal}")
            print(f"Assunto: {msg.assunto}")
            print(msg.corpo)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
