# UMARS v8: guía de experimentos

La versión v8 añade una penalización configurable para giros puros evitables y
dos rocas móviles en un mundo nuevo. Los archivos y resultados de v7 permanecen
separados. A evalúa la tabla histórica v7 en el mundo estático con recompensa
original; B usa el mundo estático con penalización y entrena una tabla nueva;
C usa rocas móviles y recompensa original; D combina rocas móviles y penalización.

## Vistas dentro de Webots

Abra `worlds/marte_v8_dinamico.wbt` o `worlds/marte_v8_estatico.wbt` con
**File > Open World**. Maximice Webots y pulse **Simulation > Real-time** (`Ctrl+2`)
para que el controlador reciba las primeras imágenes y dibuje la nube del Lidar.

Si falta algún panel, seleccione `UMARS_rover_Q` en el árbol de escena.
En **Overlays**, desmarque **Hide All Camera Overlays**,
**Hide All RangeFinder Overlays** y **Hide All Display Overlays** si están activos.
Active `rgb` en **Camera Devices**, `depth` en **RangeFinder Devices** y
`lidar_display` en **Display Devices**. Los archivos `.wbproj` guardan la
posición y visibilidad individual de esos tres paneles. Si toda la vista 3D
está negra, compruebe **Simulation > Rendering**.

`lidar_display` muestra la nube en 2D. Para verla también en la escena 3D,
active **View > Optional Rendering > Show Lidar Point Cloud**.

## Comparación pareada C y D

Desde la raíz del proyecto, ejecute:

```powershell
.\.venv\Scripts\python.exe -m herramientas.comparar_cd_v8 --ejecutar
```

El lote entrena C y D desde tablas nuevas durante 120 episodios por semilla
(`42`, `1042` y `2042`). Evalúa cada par en 20 escenarios con los mismos
inicios, metas, velocidades y fases de las rocas. El máximo es 120 acciones.
Solo D aplica la penalización de 0,2. El lote abre Webots minimizado, con el
panel visual desactivado para acelerar la corrida. El controlador sigue
usando el Lidar y la profundidad.

El informe `comparacion_cd.md` contabiliza llegadas, colisiones, vetos y
contactos en todos los escenarios. Compara acciones y giros solo en los
escenarios en que ambas políticas llegaron, ya que un fallo temprano también
puede reducir el número de acciones. Una mejora observada requiere menos
acciones o giros y, como mínimo, conservar las llegadas y evitar un aumento
de las colisiones. Los episodios de una misma semilla comparten un entrenamiento.

Para reproducir el informe a partir de corridas ya guardadas, omita
`--ejecutar`. Para el piloto histórico, use `--semillas 42 --entrenamiento 2 --evaluacion 2`.

## Prueba corta, PowerShell

Desde la raíz del proyecto, con el entorno `.venv` activo, configure el
intérprete Python de Webots si aún no lo está en sus preferencias. Inicie
Webots **desde esta misma sesión de PowerShell**; una instancia abierta desde
el escritorio no hereda las variables definidas aquí:

```powershell
$env:WEBOTS_PYTHON_COMMAND = (Resolve-Path '.venv\Scripts\python.exe').Path
$env:UMARS_ENTRENAMIENTO = '2'
$env:UMARS_EVALUACION = '2'
$env:UMARS_MAX_ACCIONES = '120'
$env:UMARS_V8_SEMILLA = '42'
$env:UMARS_V8_POLITICA = 'q'
$env:UMARS_V8_PENALIZACION_GIRO = '0.2'
& 'C:\Program Files\Webots\msys64\mingw64\bin\webots.exe'
```

Abra `worlds/marte_v8_estatico.wbt` y ejecute la simulación para B. Para A,
ponga `$env:UMARS_V8_PENALIZACION_GIRO = '0'` y reinicie el mundo estático;
el controlador carga la tabla v7 y solo evalúa. Después,
abra `worlds/marte_v8_dinamico.wbt` y ejecute C y D por separado:

```powershell
# C: mundo dinámico, recompensa original
$env:UMARS_V8_PENALIZACION_GIRO = '0'
# Abrir el mundo dinámico y ejecutar hasta finalizar.

# D: mundo dinámico, penalización por giro
$env:UMARS_V8_PENALIZACION_GIRO = '0.2'
# Reiniciar el mismo mundo dinámico y ejecutar hasta finalizar.
```

Para comparar reglas en el mismo mundo y con las mismas semillas:

```powershell
$env:UMARS_V8_POLITICA = 'reglas'
$env:UMARS_V8_PENALIZACION_GIRO = '0.2' # B o D; use '0' para C
# Reiniciar el mundo correspondiente y ejecutar.
```

Las variables de entorno pasan del PowerShell a Webots y de Webots al
controlador. **Cierre Webots y vuelva a abrirlo desde ese mismo PowerShell**
después de cambiar una variable; reiniciar solo la simulación no actualiza el
entorno de un proceso Webots que ya estaba abierto.
Para ampliar entrenamiento, cambie `UMARS_ENTRENAMIENTO` (por ejemplo a `60`)
manteniendo la misma semilla, `UMARS_MAX_ACCIONES`, alfa, gamma y meta.

## Archivos de salida

Cada ejecución crea una carpeta nueva en `resultados/experimentos_v8/B`, `C`
o `D`, con identificador temporal único. El CSV de episodios registra metas,
semillas, acciones, giros, distancia, tiempo, retorno base, retorno usado para
aprender, éxitos y colisiones. El CSV de transiciones registra estado, los cinco
valores Q, acción, lecturas de seguridad y Lidar, recompensa y motivo de
terminación. Las posiciones de las rocas se guardan solo para verificar el
experimento; **no entran en la observación ni en la política**.

Ejecute el resumen solo después de completar corridas:

```powershell
.\.venv\Scripts\python.exe herramientas\resumir_v8.py
```

Genera `resumen_corridas.csv`, `RESUMEN.md` y un gráfico que muestra solo la
última corrida completa de cada grupo. Las corridas incompletas se excluyen
y las repetidas no se cuentan como muestras nuevas. La referencia A contiene
episodios repetidos del mismo escenario y no es una prueba independiente
frente a B, C o D. El CSV separa `vetos_trayectoria`, que son movimientos
rechazados antes de ejecutarse, y `contactos_geometricos`, detectados mientras
avanza la simulación. El campo general `colision` incluye ambos para mantener
la comparación con v7.

La tabla sigue siendo de 144 estados por cinco acciones. La velocidad y fase
de las rocas no figuran en el estado; una misma observación puede corresponder
a trayectorias futuras distintas. Es una limitación deliberada de esta prueba.

## Verificación local

```powershell
.\.venv\Scripts\python.exe -m unittest herramientas.test_qlearning herramientas.test_v8 -v
```

Estas pruebas comprueban lógica y archivos, pero no prueban que la cámara o el
Lidar detecten una roca en movimiento dentro de Webots. Esa verificación
requiere ejecutar el mundo dinámico y observar que cambien tanto el panel del
Lidar como `lidar_min_m` en `transiciones.csv` al desplazarse las rocas.
