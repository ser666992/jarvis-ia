"""
ia/local_model.py
====================
Fallback de modelo de linguagem local, sem nenhuma API externa.
Tenta, em ordem:
  1. `llama-cpp-python`, se o usuário apontar um arquivo `.gguf` em
     `ia.modelo_local.caminho_gguf` no config.
  2. `transformers` (pipeline text-generation), se o usuário apontar
     um modelo em `ia.modelo_local.nome_modelo` (ex.: `"distilgpt2"`,
     ou qualquer id do Hugging Face) -- roda em GPU se
     `sistema.device_for_ml()` disser "cuda", senão CPU.

Em ambos os casos o modelo só é usado se o usuário indicou
explicitamente qual -- este módulo nunca escolhe um modelo "surpresa"
para baixar sozinho (evita downloads grandes e respostas de baixa
qualidade sem o usuário saber que isso ia acontecer).

Sem nenhuma dessas bibliotecas instaladas, ou sem nenhum modelo
apontado no config, `available()` retorna False e o AIManager segue
para o fallback final do Ultron (base de conhecimento / conversa
natural) -- nunca trava o programa.

Importante: `available()` só verifica se as bibliotecas podem ser
importadas (rápido, sem rede) -- ela NUNCA carrega/baixa o modelo de
verdade. O carregamento (que pode baixar pesos do Hugging Face na
primeira vez) só acontece dentro de `chat()`, no primeiro uso real,
para que checar status/disponibilidade nunca tenha esse efeito
colateral pesado.
"""

from ia.base import AIProvider


class LocalModelProvider(AIProvider):
    name = "modelo_local"
    kind = "local"

    def __init__(self, model_name: str = "", gguf_path: str = ""):
        self.model_name = model_name
        self.gguf_path = gguf_path
        self._pipeline = None
        self._backend = None

    def _llama_cpp_importable(self) -> bool:
        if not self.gguf_path:
            return False
        try:
            import os
            import llama_cpp  # noqa: F401
            return os.path.isfile(self.gguf_path)
        except Exception:
            return False

    def _transformers_importable(self) -> bool:
        # Exige um modelo explícito em ia.modelo_local.nome_modelo -- sem
        # isso, não escolhemos um modelo "surpresa" para baixar sozinhos.
        if not self.model_name:
            return False
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
            return True
        except Exception:
            return False

    def _load_transformers(self) -> bool:
        if self._backend == "transformers" and self._pipeline:
            return True
        if not self._transformers_importable():
            return False
        try:
            from transformers import pipeline
            import sistema
            device = 0 if sistema.device_for_ml() == "cuda" else -1
            self._pipeline = pipeline("text-generation", model=self.model_name, device=device)
            self._backend = "transformers"
            return True
        except Exception:
            return False

    def _load_llama_cpp(self) -> bool:
        if self._backend == "llama_cpp" and self._pipeline:
            return True
        if not self._llama_cpp_importable():
            return False
        try:
            from llama_cpp import Llama
            self._pipeline = Llama(model_path=self.gguf_path, n_ctx=4096, verbose=False)
            self._backend = "llama_cpp"
            return True
        except Exception:
            return False

    def available(self) -> bool:
        return self._llama_cpp_importable() or self._transformers_importable()

    def chat(self, messages: list, **kwargs) -> str:
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"

        if self._load_llama_cpp():
            result = self._pipeline(prompt, max_tokens=kwargs.get("max_tokens", 256), stop=["\nuser:"])
            return result["choices"][0]["text"].strip()

        if self._load_transformers():
            result = self._pipeline(
                prompt, max_new_tokens=kwargs.get("max_tokens", 128), num_return_sequences=1,
            )
            text = result[0]["generated_text"]
            return (text[len(prompt):] or text).strip()

        raise RuntimeError(
            "Nenhum backend de modelo local disponível "
            "(instale transformers+torch, ou llama-cpp-python + aponte ia.modelo_local.caminho_gguf)."
        )
