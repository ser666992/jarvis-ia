"""Simulador somente-leitura de sequências de automação."""

import re

_RISKY = re.compile(
    r"\b(apag|delet|remove|format|deslig|reinici|compr|envia|public|instal)\w*",
    re.IGNORECASE,
)


def simulate(commands: list[str]) -> list[dict]:
    result = []
    for index, command in enumerate(commands, 1):
        text = str(command).strip()
        risk = "alto" if _RISKY.search(text) else "baixo"
        result.append({
            "step": index,
            "command": text,
            "risk": risk,
            "would_execute": False,
            "note": "simulação: nenhuma ação foi executada",
        })
    return result
