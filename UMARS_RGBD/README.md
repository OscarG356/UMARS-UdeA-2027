# UMARS – Inicio RGB-D en Webots

> Para los experimentos actuales con Q-learning v8, rocas móviles y vistas
> integradas de cámara y Lidar, consulte
> [la guía v8](resultados/experimentos_v8/README.md).

Este proyecto es un **primer hito de percepción estacionaria**, no el rover móvil final ni el entrenamiento de Q-learning.

## Preparar Python (PowerShell, Windows 11)

Desde la carpeta raíz del proyecto:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
python -c "import cv2, numpy, matplotlib; print('Librerías listas')"
```

Si PowerShell bloquea la activación, no necesitas modificar políticas globales: ejecuta ` .\.venv\Scripts\python.exe -m pip install -r requirements.txt` y los comandos con esa ruta. También puedes abrir `cmd` y usar `.venv\Scripts\activate.bat`.

## Webots

1. Instala Webots **R2025a estable** desde https://github.com/cyberbotics/webots/releases/latest
2. Configura en Webots (Tools > Preferences > General) el Python executable como `RUTA_DEL_PROYECTO\.venv\Scripts\python.exe` (la posición del ajuste puede variar según versión). La API `controller` la proporciona Webots en su proceso de ejecución.
3. En Webots: **File > Open World...** y abre `worlds/marte_rgbd.wbt`.
4. Pulsa **Run**. En la consola del simulador verás distancias y la decisión heurística recomendada.
5. Espera unos pasos de simulación hasta que aparezcan `capturas/rgb.png` y `capturas/depth.csv`. Si cambias obstáculos, borra las capturas previas y reinicia la escena para obtener evidencia nueva.
6. En la terminal de VS Code ejecuta `python herramientas/analizar_captura.py`. Verás `capturas/analisis_rgbd.png`.

### Si no abre o no captura
- En el árbol de escena asegúrate de que el Robot tenga `controller "percepcion_rgbd"` y existan los dispositivos `rgb` y `depth`.
- Ejecuta la simulación con el botón de *play*, no solo abriendo el mundo.
- El archivo `capturas/depth.csv` no existe hasta que se ejecute el controlador.
- Comprueba qué Python usa Webots y que pueda importar `controller`.
- Este es un proyecto de ejemplo construido para R2025a; el equipo todavía debe validarlo ejecutándolo en su PC. Si algún nodo produce error de versión, empieza con el ejemplo oficial `range_finder.wbt` y luego migra el controlador.

## Arquitectura para integrar Kinect v1 después
- Webots: API de `Camera` y `RangeFinder`.
- Kinect real: capa de captura compatible con el driver que efectivamente funcione.
- Ambas fuentes deben entregar una matriz RGB y una matriz de profundidad en **metros**, con resolución/calibración conocidas, y valores invalidos identificados.
- El clasificador por regiones solo utiliza profundidad; RGB queda disponible para ampliaciones posteriores.
- La señal de rumbo hacia la meta **todavía no se implementa**; habrá que definirla por separado para completar los 24 estados de Q-learning.

## A continuación
1. Poner el robot en movimiento con ruedas y control independiente de seguridad.
2. Crear episodios, meta, recompensas y baseline de navegación.
3. Implementar Q-learning tabular y ruido controlado en la ocupación observada.
4. Repetir evaluaciones con cinco semillas y mapas de prueba no vistos.
