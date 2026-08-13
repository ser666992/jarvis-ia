"""
ia/base.py
============
Interface comum de um provedor de IA (`AIProvider`). Todo provedor em
`ia/providers/` implementa isso. `ia/manager.py` (AIManager) usa essa
interface para tentar provedores em ordem, sem precisar saber os
detalhes de cada API.
"""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    name = "base"
    kind = "remoto"  # "remoto" (precisa de internet) ou "local" (servidor local, ex Ollama)

    @abstractmethod
    def available(self) -> bool:
        """True se este provedor está pronto para uso (chave/URL configurada)."""
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages: list, **kwargs) -> str:
        """messages: lista de {"role": "system"|"user"|"assistant", "content": str}.
        Retorna o texto da resposta, ou levanta exceção em caso de erro."""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"nome": self.name, "tipo": self.kind, "disponivel": self.available()}
