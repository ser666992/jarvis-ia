# visao/ — Visão computacional

100% opcional — cada recurso liga independentemente conforme a
dependência correspondente estiver instalada.

## Módulos

| Arquivo | Recurso | Dependência |
|---|---|---|
| `camera.py` | captura de webcam | `opencv-python` |
| `ocr.py` | leitura de texto em imagem | `pytesseract` + `Pillow` + binário Tesseract |
| `faces.py` | detecção facial (sempre que `opencv` estiver ok) / reconhecimento (identificar quem é) | `opencv-python` / `face_recognition` |
| `objects.py` | detecção de objetos (YOLO) | `ultralytics` |
| `gestures.py` | detecção de mãos/gestos | `mediapipe` |
| `screen.py` | captura, leitura (OCR) e gravação de tela | `mss` (+ `opencv-python` para gravar vídeo) |
| `video_edit.py` | edição básica de vídeo (cortar trecho, acelerar) | `opencv-python` |

Assim como em `ia/local_model.py`, `objects.detect()` só baixa o
checkpoint do YOLO na primeira chamada real — `available()` nunca
dispara esse download sozinho.

**OCR (melhoria de precisão)**: `ocr.read_text_from_frame()` agora
pré-processa a imagem (escala de cinza + upscale 2x + binarização
Otsu) antes de passar pro Tesseract -- texto de UI/screenshot é
pequeno e com antialiasing, bem diferente do documento escaneado
(texto grande, preto sólido) em que o Tesseract foi majoritariamente
treinado, e lido "cru" ele errava/perdia letras com frequência.
`ocr.available()` também ficou cacheado: antes chamava o binário do
Tesseract via subprocesso (`get_tesseract_version()`) a cada checagem,
o que pesava em quem consulta isso com frequência (ex.: `visao_continua`,
a cada tick em que a tela mudou).

**OCR com localização (novo)**: `ocr.localizar_texto_na_tela(texto)`
vai além de `read_screen_text()` (só o texto corrido) -- devolve TAMBÉM
a posição de cada trecho encontrado, em coordenadas absolutas de tela
prontas pra `controle_pc.entrada.clicar()`. Base de "clica no texto
..." (ver `plugins/clicar_texto.py` e `controle_pc/README.md`), que
combina visão computacional com controle de mouse pra clicar em texto
visível na tela mesmo quando o app não expõe árvore de acessibilidade
(diferente de `controle_pc.clicar_elemento`, que precisa disso).

## Instalação

```bash
pip install -r requirements-visao.txt
```

Tesseract OCR precisa do binário nativo instalado à parte (não é só
`pip install`) — no Windows, use o instalador oficial do projeto
Tesseract e garanta que fique no PATH.

## Uso

```python
from visao.camera import Camera
from visao import faces, ocr, objects, screen

cam = Camera(index=0)
frame = cam.snapshot()

faces.detect_faces(frame)           # [(x, y, largura, altura), ...]
objects.detect(frame)               # [{"classe": "person", "confianca": 0.92, "caixa": (...)}]
ocr.read_text_from_frame(frame)     # texto lido na imagem

screen.screenshot()                 # frame da tela
screen.read_screen_text()           # OCR direto na tela
screen.record_screen("captura.mp4", seconds=10)

from visao import video_edit
video_edit.cortar("captura.mp4", inicio_seg=2, fim_seg=8, caminho_saida="corte.mp4")
video_edit.acelerar("captura.mp4", fator=2, caminho_saida="rapido.mp4")
```

Pelo chat, tudo isso é exposto via `plugins/video_creation.py`
("grava minha tela por 20 segundos", "corta o vídeo ... de 5 a 15
segundos", "acelera o vídeo ... em 2x").
