# config/ — Configuração centralizada

Um único arquivo de configuração para todo o Jarvis: `config/config.json`.

## Como funciona

- Na primeira execução, `config/config.json` é criado automaticamente
  a partir do template `config/config.example.json`.
- Editar `config.json` à mão é seguro: campos que faltarem continuam
  usando o valor default (merge automático), então atualizar o Jarvis
  não quebra um config antigo.
- Se preferir YAML: instale `pyyaml` (`pip install pyyaml`) e crie
  `config/config.yaml` — ele passa a ter prioridade sobre o JSON. Sem
  `pyyaml` instalado, o Jarvis ignora o YAML e usa o JSON normalmente
  (zero dependência obrigatória).
- Qualquer chave pode ser sobrescrita por variável de ambiente:
  `JARVIS_<CAMINHO_EM_MAIUSCULO_COM_UNDERSCORE>`. Exemplo:
  `JARVIS_IA_PROVEDORES_OPENAI_API_KEY=sk-...` sobrescreve
  `ia.provedores.openai.api_key` sem precisar editar o arquivo (útil
  para não deixar chaves de API em texto puro no disco).

## Seções

| Seção | Controla |
|---|---|
| `geral` | nome do assistente, idioma, usuário padrão (`usuario_padrao` -- também o "operador" reconhecido pela abertura da GUI) e `intro_animada` (`true` por padrão -- a abertura cinematográfica da GUI; ver `gui/intro.py`) |
| `modulos` | liga/desliga cada módulo (`ia`, `voz`, `visao`, `automacao`, `dispositivos`, `sistema`, `seguranca`, `logs`, `atualizacoes`, `visao_continua`, `controle_pc`) |
| `personalidade` | estilo de resposta, voz robótica (`voz_robotica` liga/desliga, `tom_voz_robotica` ajusta o quão grave, -9 por padrão; `efeito_ultron` liga o processamento de áudio que deixa a voz mais grave/metálica/em camadas com reverb frio -- estilo IA vilanesca, NÃO clone de voz de ninguém -- e `intensidade_ultron` 0..1 regula o quanto, 0.7 por padrão; requer numpy + SAPI/Windows, cai pra prosódia simples sem eles), se o bloco "Confiança: X%" aparece nas respostas (`mostrar_confianca`, `false` por padrão), se o provedor de IA que gerou a resposta aparece no rodapé (`mostrar_provedor_ia`, `false` por padrão -- diga "mostra o provedor da ia"/"esconde o provedor da ia" pra alternar), auto-melhoria periódica (`auto_melhoria`/`auto_melhoria_intervalo_horas`), aprendizado autônomo de tecnologia (`aprender_tecnologia`/`aprender_tecnologia_intervalo_horas`), análise de hábitos (`analisar_habitos`), sistema de "sonhos" (`sonhos`/`sonhos_intervalo_horas`) e assistência proativa opt-in sobre erros detectados na tela (`assistencia_proativa`, `false` por padrão — ver `visao_continua/README.md`) — ver seções "Jarvis criando código sozinho" e "Mais autonomia" no README principal |
| `ia` | ordem de tentativa dos provedores, chaves de API, modelo local, e `timeout_geracao_segundos` (600s = 10min por padrão) -- teto de tempo pra IA GERAR código/jogo/correção, bem mais folgado que uma resposta de chat comum porque gerar um arquivo inteiro num modelo grande/local demora; `0` desliga o teto (espera indefinidamente) se mesmo 10min não bastar |
| `voz` | wake word (+ chave opcional do Picovoice, e `palavras_chave` para mais de uma palavra de ativação), idioma de reconhecimento, motor de STT/TTS, microfone, detecção de silêncio, velocidade da fala (`velocidade_fala`, 205 por padrão -- "fala mais rápido"/"fala mais devagar" ajusta em tempo real) |
| `escuta_ativa` | teto de segurança (`duracao_maxima_minutos`, 30 por padrão) para a sessão de escuta acompanhada com tempo limitado — ver `automacao/README.md` |
| `visao` | câmera, reconhecimento facial, detecção de objetos |
| `sistema` | monitoramento de hardware (intervalo, histórico) e o Sistema de Curiosidade/Previsão (`curiosidade`, `true` por padrão, `curiosidade_intervalo_minutos`, 10 -- coleta snapshots leves e avisa sobre tendências reais como disco enchendo; ver `sistema/curiosidade.py`) |
| `seguranca` | modo administrador, se ações destrutivas (fechar programa, instalar app, rodar código gerado etc.) exigem a palavra "confirmo" na frase (`exigir_confirmacao_acoes_destrutivas`, `true` por padrão -- diga "não peça confirmação"/"peça confirmação" pra alternar globalmente), backup automático |
| `logs` | nível de log, rotação de arquivo |
| `automacao` | sites conhecidos para "abra ...", e se logins/Instagram automatizados preferem o Brave em vez do Chromium do Playwright quando instalado (`preferir_brave`, `true` por padrão) |
| `dispositivos` | caminho do `adb`, porta SSH padrão |
| `instagram` | `envio_automatico` (`false` por padrão -- ver "ativa o envio automático do instagram" no README), `limite_envios_por_dia` (15 por padrão) e `preferir_brave` (`false` por padrão -- diferente do resto da automação, o login do Instagram usa Chromium puro por padrão, mesmo com `automacao.preferir_brave=true`, porque o reCAPTCHA do Instagram/Google ficou em branco com o Shields do Brave ativo em teste real) |
| `visao_continua` | se o acompanhamento contínuo da tela está ativo (`ativa`, `false` por padrão -- diga "liga a visão contínua" pra ligar), intervalo entre checagens (`intervalo_segundos`, 3 por padrão), sensibilidade da detecção de mudança (`limiar_mudanca`, 12.0) e quantas observações manter em memória (`manter_historico`, 20) — ver `visao_continua/README.md` |
| `atualizacoes` | checagem automática periódica de atualização via git (`verificar_automaticamente`, `true` por padrão, `intervalo_horas`, 24 por padrão) -- só avisa por notificação, nunca aplica sozinho (`git pull` só roda com "atualiza o jarvis, confirmo") — ver `atualizacoes/README.md` |

## Uso programático

```python
from config.settings import get_settings

settings = get_settings()
settings.get("ia.provedores.openai.api_key")
settings.is_module_enabled("voz")          # True/False
settings.get_provider_config("nvidia")     # já resolve override por env var
settings.set("seguranca.modo_administrador", True)
settings.save()
```
