"""Rilevamento della wake word «Amy» sul testo trascritto.

Questa implementazione non finge di fare keyword spotting acustico: rileva la
wake word nella trascrizione locale. Per un rilevamento a basso consumo si può
integrare openWakeWord come filtro davanti allo STT, senza cambiare
l'interfaccia.

Lo STT sbaglia spesso una parola inventata come «Amy»: la trascrizione tipica è
«Emi», «Ami» o «Emy». Il confronto quindi accetta una distanza di edit piccola
sul primo token, oppure dopo un prefisso di richiamo («ehi», «ok», «hey»).
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Sequence, Tuple

PREFIXES = ("ehi", "hey", "ok", "okay", "oh", "ei", "ciao")


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^\w\s']", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def edit_distance(a: str, b: str) -> int:
    """Distanza di Levenshtein, senza dipendenze."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if ca == cb else 1),
                )
            )
        previous = current
    return previous[-1]


class WakeWordDetector:
    def __init__(self, phrase: str = "amy", sensitivity: float = 0.5) -> None:
        self.phrase = normalize(phrase) or "amy"
        self.sensitivity = max(0.0, min(float(sensitivity), 1.0))

    # ------------------------------------------------------------------ varianti
    def _variants(self) -> List[str]:
        variants = {self.phrase}
        if self.sensitivity >= 0.5:
            variants.update({"ehi %s" % self.phrase, "hey %s" % self.phrase, "ok %s" % self.phrase})
        if self.sensitivity >= 0.8:
            variants.update({"ami", "ammy", "emmi", "emi", "emmy"})
        return sorted(variants, key=len, reverse=True)

    def _tolerance(self) -> int:
        """Errori ammessi sul token, in base alla lunghezza della parola.

        «Amy» è una parola inventata e lo STT la trascrive quasi sempre in modo
        diverso («Emi», «Ami», «Emy»): per una parola così corta servono due
        caratteri di tolleranza. Il confronto resta limitato al primo token o
        subito dopo un prefisso di richiamo, per non attivarsi su parole comuni
        («mai», «mia»).
        """
        if self.sensitivity < 0.5:
            # Sotto la soglia predefinita vale solo il confronto esatto.
            return 0
        length = len(self.phrase)
        if length <= 3:
            return 2
        if length <= 5:
            return 1 if self.sensitivity < 0.8 else 2
        return 0 if self.sensitivity < 0.8 else 1

    def _token_matches(self, token: str) -> bool:
        if token in self._variants():
            return True
        tolerance = self._tolerance()
        if tolerance <= 0:
            return False
        if token.startswith(self.phrase) or self.phrase.startswith(token):
            # «am», «amy», «amyy»: prefissi brevi non bastano, serve il token intero.
            if len(token) >= max(2, len(self.phrase) - tolerance):
                return True
        # Le trascrizioni sbagliate di «Amy» iniziano per vocale («Emi», «Ami»,
        # «Emy»). Senza questo filtro la distanza di edit accettava anche «ha»
        # (distanza 2) e attivava Amy su frasi qualsiasi.
        if token[:1] not in {"a", "e"}:
            return False
        return edit_distance(token, self.phrase) <= tolerance

    def _match_index(self, tokens: Sequence[str]) -> Tuple[int, int]:
        """Restituisce (primo token, indice del token della wake word) o (-1, -1)."""
        if not tokens:
            return -1, -1
        for index, token in enumerate(tokens[:2]):
            if index == 1 and tokens[0] not in PREFIXES:
                break
            if self._token_matches(token):
                return 0, index
        return -1, -1

    # ------------------------------------------------------------------ API
    def matches(self, text: str) -> bool:
        tokens = normalize(text).split()
        return self._match_index(tokens)[0] >= 0

    def extract_command(self, text: str) -> Optional[str]:
        """Restituisce il testo dopo la wake word, oppure None se assente."""
        tokens = normalize(text).split()
        start, index = self._match_index(tokens)
        if start < 0:
            return None
        remainder = " ".join(tokens[index + 1:]).strip(" ,.;:!?-")
        if not remainder:
            return None
        return remainder
