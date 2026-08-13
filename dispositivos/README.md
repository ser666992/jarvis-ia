# dispositivos/ — Android, Bluetooth, Serial, MQTT, SSH

Todos os backends são opcionais e independentes entre si.

| Arquivo | Cobre | Dependência |
|---|---|---|
| `adb.py` | Android (conectar por Wi-Fi sem cabo, abrir apps, instalar apk, shell, push/pull arquivo) | binário `adb` no PATH, ou uma cópia em `tools/platform-tools/` (Android SDK Platform Tools — não é pip; ver "Conectar o celular por Wi-Fi" abaixo) |
| `bluetooth_ble.py` | Bluetooth Low Energy (scan, ler/escrever característica) | `bleak` |
| `serial_device.py` | Arduino/ESP32/serial genérico (inclui listar portas sem device conectado) | `pyserial` |
| `mqtt.py` | IoT / casa inteligente (publish/subscribe em broker) | `paho-mqtt` |
| `ssh_client.py` | SSH em servidores/Raspberry Pi | `paramiko`, ou cliente `ssh` do sistema como fallback |

## Instalação

```bash
pip install -r requirements-dispositivos.txt
```

`adb` não é um pacote pip -- é um binário do Android SDK Platform
Tools. `dispositivos/adb.py` procura, nessa ordem: (1) um caminho
customizado em `config.json` → `dispositivos.adb_path`; (2) uma cópia
baixada em `tools/platform-tools/adb.exe` (ou `adb` no Linux/macOS),
dentro da própria pasta do projeto; (3) `adb` no PATH do sistema.
Baixe em https://developer.android.com/tools/releases/platform-tools
e extraia como `tools/platform-tools/` se não quiser mexer no PATH
global.

## Conectar o celular por Wi-Fi (sem cabo, mesma rede local)

`connect()`/`pair()`/`disconnect()` usam o protocolo ADB por TCP/IP na
rede local -- nunca abrem porta nenhuma pra internet, então não têm o
risco de expor ADB publicamente (portas ADB abertas na internet são
alvo comum de botnets; isto aqui fica só dentro da sua rede Wi-Fi).

**Android 11+ ("Depuração sem fio"), primeira vez:**
1. No celular: Opções do desenvolvedor > Depuração sem fio > Parear
   dispositivo com código.
2. No chat: `"pareia o celular <ip>:<porta> <código>"` (IP, porta e
   código de 6 dígitos aparecem na tela do celular).
3. No chat: `"conecta no celular <ip>:<porta>"` (porta da tela
   principal de Depuração sem fio, diferente da porta de pareamento).

Depois de parear uma vez, só precisa reconectar (`"conecta no celular
<ip>"`) enquanto o celular estiver na mesma rede Wi-Fi com a
depuração sem fio ligada.

**Qualquer versão do Android, com USB uma vez:** conecta o cabo,
`dispositivos.adb.enable_tcpip()` muda o aparelho pro modo TCP/IP,
desconecta o cabo, e a partir daí só `connect()` no IP Wi-Fi dele
(`dispositivos.adb.device_ip()` ajuda a descobrir esse IP).

Comandos no chat: `"celulares conectados"`, `"desconecta o celular"`,
`"abre o whatsapp no celular"` (por nome comum ou nome de pacote),
`"vê a bateria do celular"` (`dispositivos.adb.battery_level()`),
`"tira um print do celular"` (`dispositivos.adb.screenshot()`, salvo
em `data/screenshots/`).

### Notificações (leitura) e sugestão de resposta pro Instagram

Leitura via **ADB sem fio** (`dispositivos.adb.list_notifications()`):
lê via `dumpsys notification --noredact` -- leitura, nunca toca em
nenhum app, mas é melhor-esforço (formato varia por versão do
Android/fabricante), diferente do resto deste módulo que usa o
protocolo ADB documentado.

`plugins/instagram.py` usa isso pra: `"minhas mensagens do instagram"`
(lista) e `"sugere uma resposta pro instagram"` (a IA escreve uma
sugestão de resposta no seu estilo -- você revisa e envia manualmente
pelo app). **Isso não envia nada sozinho, de propósito**: não existe
API pública pra automatizar mensagens numa conta pessoal do Instagram
-- a oficial (Graph API) é só pra contas Business/Creator com
aprovação do Meta, e automação não-oficial viola os Termos de Uso e
arrisca banir a conta. A sugestão de resposta usa um prompt de sistema
próprio (não a persona configurada do Jarvis, nem no estilo "ultron")
-- ver `ia/manager.py:AIManager.chat(system_prompt=...)`.

## Extender com um novo dispositivo (via plugin)

```python
from dispositivos import register_device

def meu_sensor_handler(comando):
    ...

register_device("meu_sensor", meu_sensor_handler)
```

## Uso

```python
import dispositivos

dispositivos.adb.list_devices()
dispositivos.serial_device.list_ports()
dispositivos.mqtt.MQTTClient("localhost").connect()
dispositivos.ssh_client.run_command("192.168.0.10", "uptime", user="pi")
dispositivos.status()
```
