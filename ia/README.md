# ia/ — Provedores de IA (todos opcionais)

Nenhuma chave de API é obrigatória. O `AIManager` detecta
automaticamente quais provedores estão configurados e tenta cada um,
na ordem definida em `config.json` → `ia.ordem_provedores`. Se nenhum
provedor remoto estiver configurado, ele tenta um modelo local
(`ia/local_model.py`); se isso também não estiver disponível, o
núcleo do Jarvis (`core/jarvis.py`) continua funcionando normalmente
com a base de conhecimento + plugins + conversa natural já existentes
(nenhuma IA externa nunca foi obrigatória neste projeto).

Todas as chamadas HTTP usam `urllib` da stdlib (`ia/http_utils.py`) —
**nenhum provedor exige instalar `requests` nem nenhuma outra lib**
para funcionar.

## Provedores suportados

| Nome no config | Tipo | Precisa de chave? |
|---|---|---|
| `openai` | remoto | sim |
| `anthropic` | remoto | sim |
| `gemini` | remoto | sim |
| `mistral` | remoto | sim |
| `openrouter` | remoto | sim |
| `deepseek` | remoto | sim |
| `nvidia` | remoto (API Catalog / NIM, compatível OpenAI) | sim |
| `ollama` | local (`http://localhost:11434`) | não |
| `lm_studio` | local (`http://localhost:1234/v1`) | não |
| `openai_compatible` | genérico, qualquer endpoint compatível | depende |
| `servidor_proprio` | seu próprio servidor local | depende |

Configure em `config/config.json` → `ia.provedores.<nome>`, ou via
variável de ambiente `JARVIS_IA_PROVEDORES_<NOME>_API_KEY` (não fica
gravada em disco).

## Assistente de configuração (`ia/setup.py`)

No primeiro início sem nenhum provedor configurado, `main.py` pergunta
se você quer configurar um agora (aceita **qualquer** um dos
provedores acima, incluindo NVIDIA). Recusar uma vez não pergunta de
novo nas próximas execuções (`ia.perguntar_no_inicio` vai para
`false`); rode `/configurarapi` no chat quando quiser configurar ou
trocar de provedor depois.

O assistente **valida de verdade** antes de salvar: faz uma chamada
mínima real (poucos tokens) ao provedor escolhido com a chave/URL
informada, via `ia.setup.test_provider(...)`. Só grava em
`config/config.json` (`ia.setup.save_provider(...)`) se a chamada
funcionou — uma chave errada nunca é salva silenciosamente, o erro
real da API (401, 403, conexão recusada, etc.) é mostrado para o
usuário corrigir.

```python
import ia.setup as ia_setup

ia_setup.list_providers()  # [(nome, rótulo, precisa_de_chave, url_padrao), ...]
ok, mensagem = ia_setup.test_provider("nvidia", api_key="nvapi-...")
if ok:
    ia_setup.save_provider("nvidia", api_key="nvapi-...")
```

## NVIDIA (NIM / API Catalog)

O endpoint da NVIDIA (`https://integrate.api.nvidia.com/v1`) é
compatível com o formato de chat da OpenAI, então é coberto pelo
mesmo `OpenAICompatibleProvider` — basta uma `NVIDIA_API_KEY` (gerada
no NVIDIA API Catalog) em `ia.provedores.nvidia.api_key`. Rodar um NIM
localmente (container próprio) também funciona: aponte
`ia.provedores.nvidia.base_url` para o endereço do container.

Aceleração via CUDA/TensorRT/Triton/NeMo/Riva para modelos rodando
*localmente* (fora de um NIM) é detectada em `sistema.detect_nvidia_stack()`
mas não é orquestrada aqui — esses componentes exigem os instaladores
oficiais da NVIDIA (fora do `pip`) e hardware compatível.

## Modelo local (`ia/local_model.py`)

Sem nenhum provedor configurado, o Jarvis tenta, em ordem:
1. `llama-cpp-python` + um arquivo `.gguf` (aponte o caminho em
   `ia.modelo_local.caminho_gguf`).
2. `transformers` + `torch` + um modelo do Hugging Face indicado em
   `ia.modelo_local.nome_modelo` (ex.: `"distilgpt2"`) -- usa GPU
   automaticamente se `sistema.device_for_ml()` retornar `"cuda"`.

Nos dois casos, o modelo só é carregado/baixado se o usuário apontou
explicitamente qual usar -- o Jarvis nunca escolhe um modelo sozinho
para baixar sem avisar (evita downloads grandes e respostas fracas de
surpresa). Sem essas libs instaladas, ou sem nenhum modelo indicado,
`ia` reporta indisponível e o Jarvis segue 100% no modo baseado em
regras que já existia.

## Adicionar um provedor novo via plugin

```python
from ia.base import AIProvider
from ia.manager import AIManager

class MeuProvider(AIProvider):
    name = "meu_provedor"
    kind = "remoto"
    def available(self): return True
    def chat(self, messages, **kw): return "resposta"

AIManager.register_provider(MeuProvider())
```

## Uso programático

```python
import ia

nome_provedor, resposta = ia.manager().chat("qual a capital da França?", history=[])
ia.status()   # {"disponivel": ..., "motivo": ..., "detalhes": {...}}
```
