# seguranca/ — Autenticação, criptografia, permissões e backup

## Módulos

- `auth.py` — PIN/senha local por usuário, hash PBKDF2-HMAC-SHA256
  (200.000 iterações, stdlib `hashlib`, sem dependência externa).
  Nunca guarda a senha em texto puro.
- `crypto.py` — criptografia de segredos (ex.: API keys). Com
  `cryptography` instalado, usa Fernet (AES) de verdade, chave mestra
  em `data/.jarvis.key`. **Sem** `cryptography`, cai para uma
  ofuscação base64 reversível e `is_real_encryption()` retorna
  `False` — isso é intencional: o Jarvis nunca finge ter criptografia
  real quando não tem.
- `permissions.py` — política de "modo administrador" e "exigir
  confirmação para ações destrutivas" (`seguranca.modo_administrador`,
  `seguranca.exigir_confirmacao_acoes_destrutivas` no config). Módulos
  de automação/dispositivos devem chamar
  `check_destructive_action(descricao, confirmed=...)` antes de
  qualquer ação irreversível.
- `backup.py` — backup automático de `data/jarvis.db` para
  `data/backups/`, com limpeza dos mais antigos
  (`seguranca.backup_max_arquivos`). `maybe_auto_backup()` roda no
  startup do Jarvis e só cria backup novo se já tiver passado
  `seguranca.backup_intervalo_horas` desde o último.

## Dependência opcional

```bash
pip install -r requirements-seguranca.txt   # cryptography
```

## Uso

```python
import seguranca

seguranca.set_password("default_user", "1234", admin=True)
seguranca.verify_password("default_user", "1234")   # True

seguranca.encrypt("sk-minha-chave")
seguranca.is_real_encryption()                       # True só se 'cryptography' instalado

seguranca.check_destructive_action("apagar arquivo X", confirmed=True)

seguranca.create_backup()
seguranca.list_backups()
```
