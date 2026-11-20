"""Verifica se o site de uma empresa está no ar (pra só linkar sites confiáveis).

Faz um HEAD/GET rápido no domínio (HTTPS, com fallback HTTP), em paralelo e com
CACHE em memória — o mesmo domínio não é checado duas vezes. NÃO é uma varredura
da base inteira: roda só sobre os domínios dos resultados exibidos.

'Confiável' aqui = responde por HTTP (site vivo). Pra checagem de malware/phishing
seria preciso a Google Safe Browsing API (grátis, mas com chave) — fora do escopo.
"""
from __future__ import annotations

import concurrent.futures
import time

_TIMEOUT = 2.5
_TTL = 7 * 24 * 3600            # cache de 7 dias
_CACHE: dict[str, tuple[bool, float]] = {}   # dominio -> (no_ar, quando)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MatchmakerBot/1.0)"}


def _resp_ok(url: str) -> bool:
    import requests
    r = requests.head(url, timeout=_TIMEOUT, allow_redirects=True, headers=_HEADERS)
    if r.status_code < 400:
        return True
    if r.status_code in (403, 405):        # servidor não gosta de HEAD -> tenta GET
        r = requests.get(url, timeout=_TIMEOUT, allow_redirects=True,
                         headers=_HEADERS, stream=True)
        return r.status_code < 400
    return False


def _checar(dom: str) -> bool:
    import requests
    try:
        return _resp_ok(f"https://{dom}")
    except requests.exceptions.SSLError:
        # cert inválido: tenta HTTP (site existe, só não tem HTTPS bom)
        try:
            return _resp_ok(f"http://{dom}")
        except requests.RequestException:
            return False
    except requests.RequestException:
        # DNS/conexão/timeout: domínio morto -> falha rápido (sem 2º timeout)
        return False


def sites_ativos(dominios: list[str]) -> dict[str, bool]:
    """{dominio: no_ar}. Usa cache; só checa os pendentes, em paralelo."""
    agora = time.time()
    unicos = {d for d in dominios if d}
    pendentes = [d for d in unicos
                 if _CACHE.get(d, (None, 0.0))[1] < agora - _TTL]
    if pendentes:
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
            for dom, ok in zip(pendentes, ex.map(_checar, pendentes)):
                _CACHE[dom] = (ok, agora)
    return {d: _CACHE.get(d, (False, 0.0))[0] for d in unicos}
