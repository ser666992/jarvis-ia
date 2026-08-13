# sistema/ — Hardware, GPU e monitoramento

Cobre, no mesmo pacote, os pedidos "Sistema" e "Monitoramento" do
escopo original (são a mesma responsabilidade: ler o estado da
máquina).

## Módulos

- `hardware.py` — detecção de CPU/GPU. Cadeia de detecção de GPU:
  `torch.cuda` → `pynvml` → `nvidia-smi` (subprocess) → CPU. Também
  detecta (sem executar) presença de CUDA Toolkit, cuDNN, TensorRT,
  Triton, NeMo e Riva no ambiente, para reporte honesto de status —
  usar esse stack de verdade exige os instaladores oficiais da
  NVIDIA, que estão fora do escopo de `pip install`.
- `monitor.py` — snapshot de CPU/RAM/disco/rede/bateria (via `psutil`,
  opcional) e GPU; `MonitorLoop` grava snapshots periódicos em SQLite
  (`core/database.py`, tabela `sistema_snapshots`) se
  `sistema.monitorar_ao_iniciar=true` no config.
- `processes.py` — lista processos (via `psutil`) e serviços do
  Windows (via `sc query`, sem dependência extra).
- `display.py` — brilho da tela via WMI (`win32com`, Windows). Só
  funciona em telas com controle de brilho por software (a maioria de
  notebooks; monitores externos por HDMI/DP geralmente não). Ver
  `"aumenta/diminui/define o brilho"` em `plugins/system_control.py`.

## Dependências opcionais

`psutil` habilita CPU/RAM/rede/bateria/processos.
`torch` ou `pynvml` habilitam detecção de GPU sem depender do
`nvidia-smi` estar no PATH. Sem nenhuma delas, `sistema/` ainda
funciona: reporta o que sabe via stdlib (disco sempre funciona,
`platform` sempre funciona) e admite o que não sabe.

```bash
pip install -r requirements-sistema.txt
```

## Uso

```python
import sistema

sistema.full_report()          # {"cpu": {...}, "gpu": {...}, "nvidia_stack": {...}}
sistema.device_for_ml()        # "cuda" ou "cpu" -- usado por ia/local_model.py
sistema.snapshot()             # leitura pontual
sistema.save_snapshot()        # grava no histórico
sistema.history(limit=50)
sistema.list_processes(limit=10)
```
