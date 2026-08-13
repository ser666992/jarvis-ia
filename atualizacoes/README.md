# atualizacoes/ — Versão, checagem e atualização

- `version.py` — `VERSION` atual do Jarvis.
- `updater.py` — `check_for_updates()` usa `git fetch` +
  `git rev-parse` para comparar o commit local com o remoto
  configurado. Apenas referências Git são atualizadas; arquivos do
  projeto não são modificados.

**Checagem automática periódica** (config `atualizacoes.verificar_automaticamente`,
ligado por padrão, `atualizacoes.intervalo_horas`, 24h por padrão):
roda sozinha em segundo plano e avisa por notificação quando encontra
um commit novo no remoto -- notifica **uma vez por commit** (não fica
repetindo o mesmo aviso a cada checagem enquanto a mesma atualização
continuar pendente).

**Aplicar a atualização nunca acontece sozinho.** `aplicar_atualizacao(confirmed=True)`
é a ÚNICA função que roda `git pull` de verdade, e exige confirmação
explícita (mesma regra de qualquer ação de alto impacto neste projeto,
ver `seguranca/permissions.py`) -- puxar código novo pode sobrescrever
trabalho local e só vale totalmente depois de reiniciar o processo,
então isso nunca acontece sem o usuário pedir de propósito. Ver
`plugins/atualizacoes.py` pros comandos de chat.

Se o diretório não for um repositório git, ou `git` não estiver
instalado, isso é reportado claramente (`verificavel: false`) em vez
de travar o programa -- a checagem automática simplesmente não encontra
nada pra avisar nesse caso.

## Comandos

```
tem atualização nova / verifica atualização do jarvis
atualiza o jarvis, confirmo
```

## Uso programático

```python
import atualizacoes

atualizacoes.check_for_updates()
# {"verificavel": True, "atualizacao_disponivel": False,
#  "motivo": "já está na versão mais recente do remoto configurado.",
#  "versao_local": "0.2.0", ...}

atualizacoes.aplicar_atualizacao(confirmed=True)
# {"sucesso": True, "saida": "Already up to date."}
```
