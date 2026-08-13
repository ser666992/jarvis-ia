# logs/ — Logging centralizado

Um logger por módulo, todos gravando em `logs/jarvis.log`, com rotação
automática (stdlib `logging.handlers.RotatingFileHandler` — nenhuma
dependência externa).

## Configuração (`config.json` → `logs`)

| Chave | Efeito |
|---|---|
| `nivel` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `arquivo_max_bytes` | tamanho máximo antes de girar o arquivo |
| `arquivos_backup` | quantos arquivos antigos manter (`jarvis.log.1`, `.2`, ...) |

## Uso

```python
from logs.logger import get_logger

log = get_logger("ia")
log.info("provedor %s respondeu em %.2fs", nome, tempo)
log.warning("dependência ausente: %s", "pyttsx3")
```

No chat, o comando `/logs` mostra as últimas linhas gravadas
(`logs.logger.tail(n)`).

## Por que não usa uma tabela no banco

Log é, por natureza, um fluxo de eventos técnicos de alto volume —
arquivo de texto rotativo é o formato certo para isso (fácil de
inspecionar com qualquer editor/`tail`, sem competir com o SQLite de
`core/memory.py` e `core/database.py`, que guardam dados estruturados
de longo prazo).
