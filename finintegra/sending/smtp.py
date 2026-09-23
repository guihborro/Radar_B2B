"""Envio real por SMTP (Gmail, Outlook, ou qualquer servidor).

Credenciais vêm do .env (nunca commitadas). Para Gmail, use uma "senha de app"
(precisa de verificação em 2 etapas ligada): https://myaccount.google.com/apppasswords

Config em config.yaml -> seção `smtp`. Selecione com ferramentas.envio: "smtp".
"""
from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage

from .base import EmailSender, SendResult
from ..messaging.email_html import LOGO_CID, email_para_html, logo_path
from ..storage.models import Lead


class SMTPSender(EmailSender):
    def _credenciais(self) -> tuple[str, int, str, str, str]:
        cfg = self.cfg
        host = cfg.get("smtp", "host", default="smtp.gmail.com")
        port = int(cfg.get("smtp", "port", default=587))
        usuario = cfg.env("SMTP_USUARIO") or cfg.get("smtp", "usuario", default="")
        senha = cfg.env("SMTP_SENHA")
        remetente = cfg.get("smtp", "remetente", default="")
        if not remetente:
            # monta "Nome | Empresa <conta@servidor.com>" p/ dar identidade na inbox
            nome = str(cfg.get("smtp", "nome_exibicao", default="")).strip()
            remetente = f"{nome} <{usuario}>" if nome else usuario
        if not usuario or not senha:
            raise RuntimeError(
                "Faltam credenciais SMTP. Defina SMTP_USUARIO e SMTP_SENHA no .env "
                "(Gmail: use uma 'senha de app', não a senha normal)."
            )
        return host, port, usuario, senha, remetente

    def _montar(self, lead: Lead, remetente: str) -> EmailMessage:
        msg = lead.mensagem
        assert msg is not None
        assunto = msg.assunto
        if self.modo_teste():
            assunto = f"[TESTE→{lead.empresa.nome}] {assunto}"
        em = EmailMessage()
        em["Subject"] = assunto
        em["From"] = remetente
        em["To"] = self.destino(lead)
        em["Reply-To"] = remetente                      # respostas voltam pra você
        em.set_content(msg.corpo)                       # corpo em texto puro

        formato = str(self.cfg.get("copy", "formato_email", default="texto")).lower()
        if formato == "html":
            # versão "bonita" (logo + layout). Tende a cair em Promoções — use só
            # em contato quente/newsletter. Para cold outreach, prefira "texto".
            logo = logo_path(self.cfg)
            logo_src = f"cid:{LOGO_CID}" if logo else ""
            em.add_alternative(email_para_html(msg, self.cfg, logo_src=logo_src), subtype="html")
            if logo:
                html_part = em.get_payload()[-1]
                html_part.add_related(logo.read_bytes(), maintype="image", subtype="png",
                                      cid=f"<{LOGO_CID}>")
        # formato == "texto": só o text/plain acima -> parece e-mail pessoal 1-a-1,
        # cai na aba Principal e reduz Spam/Promoções.
        return em

    def _conectar(self):
        host, port, usuario, senha, remetente = self._credenciais()
        srv = smtplib.SMTP(host, port, timeout=30)
        srv.starttls(context=ssl.create_default_context())
        srv.login(usuario, senha)
        return srv, remetente

    def _do_send(self, lead: Lead) -> SendResult:
        srv, remetente = self._conectar()
        try:
            srv.send_message(self._montar(lead, remetente))
        finally:
            srv.quit()
        return SendResult(True, "email", f"enviado para {self.destino(lead)}")

    def enviar_lote(self, leads: list[Lead], pausa: float = 1.0) -> list[SendResult]:
        """Envia vários e-mails reusando UMA conexão (mais confiável e educado com
        o servidor). `pausa` em segundos entre envios reduz risco de rate-limit."""
        srv, remetente = self._conectar()
        resultados: list[SendResult] = []
        try:
            for i, lead in enumerate(leads):
                ok, motivo = self.pode_enviar(lead)
                if not ok:
                    resultados.append(SendResult(False, lead.canal, f"bloqueado: {motivo}"))
                    continue
                try:
                    srv.send_message(self._montar(lead, remetente))
                    resultados.append(SendResult(True, "email", f"enviado para {self.destino(lead)}"))
                except Exception as e:  # noqa: BLE001
                    resultados.append(SendResult(False, "email", f"erro: {e}"))
                if pausa and i < len(leads) - 1:
                    time.sleep(pausa)
        finally:
            srv.quit()
        return resultados
