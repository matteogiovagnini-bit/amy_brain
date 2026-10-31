"""Rilevamento della wake word «Amy» sul testo trascritto.

Questa implementazione non finge di fare keyword spotting acustico: rileva la
wake word nella trascrizione locale. Per un rilevamento a basso consumo si può
integrare openWakeWord come filtro davanti allo STT, senza cambiare l'interfaccia.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^\w\s']", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class WakeWordDetector:
    def __init__(self, phrase: str = "amy", sensitivity: float = 0.5) -> None:
        self.phrase = normalize(phrase) or "amy"
        self.sensitivity = max(0.0, min(float(sensitivity), 1.0))

    def _variants(self) -> list:
        variants = {self.phrase}
        if self.sensitivity >= 0.5:
            variants.update({"ehi %s" % self.phrase, "hey %s" % self.phrase, "ok %s" % self.phrase})
        if self.sensitivity >= 0.8:
            # Varianti frequenti di trascrizione, accettate solo ad alta sensibilità.
            variants.update({"ami", "ammy", "emmi"})
        return sorted(variants, key=len, reverse=True)

    def matches(self, text: str) -> bool:
        normalized = normalize(text)
        for variant in self._variants():
            if re.search(r"(^|\s)%s(\s|$)" % re.escape(variant), normalized):
                return True
        return False

    def extract_command(self, text: str) -> Optional[str]:
        """Restituisce il testo dopo la wake word, oppure None se assente."""
        normalized = normalize(text)
        for variant in self._variants():
            pattern = re.compile(r"(^|\s)%s(\s|$)" % re.escape(variant))
            match = pattern.search(normalized)
            if match:
                remainder = normalized[match.end():].strip(" ,.;:!?-")
                return remainder or None
        return None
