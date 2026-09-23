"""Contrato de um verificador de e-mail."""
from __future__ import annotations

import abc
import re
from dataclasses import dataclass

from ..config import Config

# valid  = seguro enviar | risky = catch-all/aceita-tudo | invalid = não enviar
STATUS_VALID = "valid"
STATUS_RISKY = "risky"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class ValidationResult:
    email: str
    status: str = STATUS_UNKNOWN
    score: float = 0.0  # 0..1

    @property
    def enviavel(self) -> bool:
        """Só 'valid' libera envio. 'risky' fica de fora por padrão (§9)."""
        return self.status == STATUS_VALID


def sintaxe_ok(email: str) -> bool:
    return bool(_RE_EMAIL.match(email.strip()))


class EmailValidator(abc.ABC):
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    @abc.abstractmethod
    def validate(self, email: str) -> ValidationResult:
        ...

    def validate_many(self, emails: list[str]) -> list[ValidationResult]:
        return [self.validate(e) for e in emails]

    def melhor(self, candidatos: list[str]) -> ValidationResult | None:
        """Valida candidatos em ordem; retorna o primeiro 'valid', senão o
        melhor 'risky', senão None. Para no primeiro 'valid' (economiza créditos)."""
        melhor_risky: ValidationResult | None = None
        for email in candidatos:
            r = self.validate(email)
            if r.status == STATUS_VALID:
                return r
            if r.status == STATUS_RISKY and (
                melhor_risky is None or r.score > melhor_risky.score
            ):
                melhor_risky = r
        return melhor_risky
