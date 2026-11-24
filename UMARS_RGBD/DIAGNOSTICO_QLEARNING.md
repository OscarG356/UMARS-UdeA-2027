# Diagnostico del Q-learning tabular

El controlador activo esta en `controllers/umars_qlearning/`. Su estado v4 es
`8 patrones de ocupacion * 3 direcciones de meta * 3 lados de rodeo *
2 clases de distancia a la meta`, es decir, 144 estados. Tiene cinco acciones: avanzar 0.20 m,
girar 30 grados en el sitio a izquierda o derecha y avanzar 0.20 m en arco
con giro de 30 grados a izquierda o derecha. El movimiento se aplica al nodo mediante `Supervisor`;
no se accionan motores. Antes de avanzar, el entorno comprueba la trayectoria
contra las cajas de los obstaculos. Una etiqueta `COLISION_*` indica un
avance rechazado por esa comprobacion geometrica, no un choque fisico medido.

La recompensa es `-1 + 2 * (distancia_anterior - distancia_actual)`, con
`-50` adicional por colision y `+100` por meta. Entrenamiento usa
epsilon-greedy y Q-learning con `alpha=0.10`, `gamma=0.95`; evaluacion usa
`epsilon=0` y no modifica Q. Un veto de avance basado en la profundidad
frontal evita elegir `AVANZAR` cuando una lectura cercana cae dentro del
margen de un paso. La politica de reglas usa las mismas observaciones y
acciones para comparar el rodeo de obstaculos.

Pruebas locales sin Webots:

```powershell
.\.venv\Scripts\python.exe herramientas\test_qlearning.py -v
```

Prueba en Webots: inicia Webots desde la misma terminal PowerShell
despues de configurar estas variables y abre `worlds/marte_qlearning.wbt`
mediante **File > Open World**, luego pulsa **Run**. Si ya estaba abierto,
cierralo antes para que herede las variables de entorno.

```powershell
$env:UMARS_ENTRENAMIENTO = '60'
$env:UMARS_EVALUACION = '10'
$env:UMARS_MAX_ACCIONES = '120'
$env:UMARS_POLITICA = 'q'
$env:UMARS_META_X = '2.2'
$env:UMARS_META_Y = '0.75'
$env:UMARS_DEBUG_STEPS = '1'
& 'C:\Program Files\Webots\msys64\mingw64\bin\webots.exe'
```

El mundo principal de entrenamiento ya tiene la meta `2.2, 0.75`; la copia
`worlds/marte_qlearning_meta_cercana.wbt` conserva la meta original.
La roca central queda en la ruta.

## Resultado anterior con la meta lejana

`resultados/diagnostico_ql_meta_lejana/` conserva la corrida del 19/11/2026:
0/60 metas en entrenamiento y 0/10 en evaluacion. El entrenamiento hizo
517 avances y 2440 giros; nunca paso de x=0.19 (meta x=2.2). Los diez
episodios de evaluacion giraron hasta apuntar hacia el oeste y salieron del
terreno. Las 24 terminaciones por colision geometrica o borde del terreno
se produjeron con `avance_seguro=1`. La tabla Q de esa corrida no se reutiliza.

## Revision v2: resultado

En `marte_qlearning.wbt`, el RangeFinder y la camara RGB tienen ahora un
campo visual de 2.1 radianes; `minRange` del RangeFinder es 0.05 m.
Las tres regiones de profundidad se solapan y cubren todo el ancho. Cuando
la meta queda a mas de 90 grados, el rover debe girar hacia ella antes de
avanzar. Recompensa, epsilon, alpha, gamma y numero de episodios permanecen
iguales. Los mundos anteriores estan guardados como `*_v1.wbt`.

La corrida v2 queda conservada en `resultados/diagnostico_ql_meta_lejana_v2/`.
Q termino con 0/60 metas en entrenamiento y 0/10 en evaluacion. La politica
de reglas tambien termino con 0/10 en
`resultados/diagnostico_reglas_meta_lejana_v2/`. En ambos casos abundaron
los giros en el sitio; Q hizo 644 avances y 3494 giros. El CSV de
transiciones incluye rumbo, error angular, posicion y distancias por region.

## Revision v3: cinco acciones

El [articulo de Ha y Vinh](https://www.mdpi.com/2076-0825/13/1/26)
(Actuators 2024, 13(1), 26) usa cinco comandos
de velocidad angular con velocidad lineal constante. Aqui se adaptan dos
avances curvos y se conservan los giros en el sitio porque el rover puede
quedar cerca de una roca sin espacio para avanzar. La comprobacion de
colision muestrea toda la curva. Q sigue siendo tabular, ahora de 24 x 5;
por eso no se cargan las tablas anteriores de 24 x 3.

Reabre `worlds/marte_reglas_meta_lejana.wbt` y pulsa **Run** para probar
la politica de referencia con los mismos cinco movimientos. Sus resultados
se guardan en `resultados/diagnostico_reglas_meta_lejana_v3/`.

Luego abre `worlds/marte_qlearning.wbt` y pulsa **Run**. El entrenamiento
y evaluacion integrados guardan sus CSV y tabla en
`resultados/diagnostico_ql_meta_lejana_v3/`.

Despues de entrenar, abre `worlds/marte_evaluacion.wbt` y pulsa **Run**.
El evaluador exige la nueva tabla v3, no modifica Q y escribe en
`resultados/diagnostico_evaluacion_ql_lejana_v3/`.

La revision v3 se ejecuto en Webots; su resultado se resume abajo.

## Revision v4: lado de rodeo y distancia

La corrida v3 esta en `resultados/diagnostico_ql_meta_lejana_v3/`:
0/60 metas durante entrenamiento y 0/10 durante evaluacion. La politica
por reglas si consiguio 10/10 metas en
`resultados/diagnostico_reglas_meta_lejana_v3/`.

El estado v3 no guardaba el lado por el que se rodeaba una roca ni la
distancia a la meta. La tabla v4 usa 144 estados y cinco acciones. El lado
vale ninguno, izquierda o derecha y se conserva mientras el obstaculo
permanece al costado; la distancia se divide en menos de 2.5 m y 2.5 m o
mas. Se retiro la regla que obligaba a repetir el ultimo giro cuando el
frente estaba bloqueado. Recompensa y parametros de aprendizaje no cambian.

Reabre `worlds/marte_qlearning.wbt` y pulsa **Run**. Los resultados v4 se
guardan en `resultados/diagnostico_ql_meta_lejana_v4/` sin sobrescribir v3.
Despues, `worlds/marte_evaluacion.wbt` cargara solo la tabla v4 de 144 x 5
y escribira en `resultados/diagnostico_evaluacion_ql_lejana_v4/`.
La politica de reglas usa `resultados/diagnostico_reglas_meta_lejana_v4/`.

## Revision v4: limite de 120 acciones

En la corrida anterior hubo 2 metas en 60 episodios de entrenamiento,
alcanzadas en 46 y 50 acciones. Otros 52 episodios agotaron el limite de
60 acciones; en esos episodios la distancia final a la meta siguio siendo
mayor de 2 m. La evaluacion integrada termino 0/10 en `MAX_ACCIONES` y
realizo 550 giros sobre 600 acciones. Por tanto, ampliar el horizonte es
una prueba concreta, pero aun no resuelve por si mismo los giros repetidos.

Entrenamiento y evaluacion usan ahora 120 acciones por defecto. Los parametros
de Q-learning, el numero de episodios y la tabla de estados no cambian.
El entrenamiento parte de una tabla nueva y guarda la corrida en
`resultados/diagnostico_ql_meta_lejana_v4_max120/`, conservando los datos v4.
Despues de abrir `worlds/marte_qlearning.wbt` y pulsar **Run**, abre
`worlds/marte_evaluacion.wbt` para evaluar la nueva tabla; el evaluador escribe
en `resultados/diagnostico_evaluacion_ql_lejana_v4_max120/`.
Si cambias `UMARS_MAX_ACCIONES` en ambos controladores, el nombre de las
carpetas se ajusta al limite elegido.

## Revision v5: seguridad por trayectoria

La corrida v4 con 120 acciones esta en
`resultados/diagnostico_ql_meta_lejana_v4_max120/`: hubo 4/60 metas en
entrenamiento y 0/10 en evaluacion. En evaluacion, 1110 de 1200 acciones
fueron giros. Desde el paso 12 el rover quedo en el mismo punto, mientras
un pixel lateral cercano vetaba los tres avances.

Ahora la profundidad axial del RangeFinder se proyecta al plano XY y se
comprueba por separado contra el trayecto de `AVANZAR`,
`AVANZAR_IZQUIERDA` y `AVANZAR_DERECHA`, usando radio 0.25 m mas margen
0.02 m. Los giros permanecen disponibles. La deteccion geometrica del
simulador sigue verificando colisiones al ejecutar cada accion. La tabla
permanece en 144 x 5, y recompensa, epsilon y episodios no cambian. El
CSV de transiciones agrega las dos banderas de seguridad para las curvas.

Primero abre `worlds/marte_reglas_meta_lejana.wbt` y pulsa **Run**; guarda
los resultados en `resultados/diagnostico_reglas_meta_lejana_v5_max120/`.
Luego ejecuta `worlds/marte_qlearning.wbt`; entrena desde una tabla nueva
y guarda en `resultados/diagnostico_ql_meta_lejana_v5_max120/`. El propio
entrenamiento incluye 10 episodios de evaluacion. Por ultimo, si quieres
comprobar la tabla por separado, abre `worlds/marte_evaluacion.wbt`; el
resultado va a `resultados/diagnostico_evaluacion_ql_lejana_v5_max120/`.
Los datos de la version anterior quedan intactos. No se agrego Lidar aun.

## Revision v6: cobertura lateral con Lidar

La corrida v5 confirmo un punto ciego. Con reglas hubo 0/10 metas y 10/10
colisiones contra la piedra lateral izquierda, siempre en el paso 14.
La camara RGB-D consideraba seguros los tres avances justo antes del choque.
Q llego 5/60 veces en entrenamiento, pero 0/10 en evaluacion; los diez
episodios se atascaron en la misma posicion tras cinco pasos de avance.

Se agrego un Lidar fijo de una capa y 270 grados, montado sobre el chasis,
a los tres mundos activos. Su nube de puntos se compara con los mismos tres
trayectos y su radio de seguridad; una accion de avance solo se permite
cuando RGB-D y Lidar coinciden en que esta libre. El estado Q sigue siendo
144 x 5 y no se modifican recompensa, epsilon ni maximo de 120 acciones.
El CSV guarda la distancia minima del Lidar y las tres banderas de seguridad
que produjo. El Lidar no proporciona informacion geometrica privilegiada del
Supervisor: solo usa las lecturas del sensor. Es necesario reiniciar Webots
o reabrir cada mundo para que aparezca el dispositivo nuevo.

Ejecuta primero `worlds/marte_reglas_meta_lejana.wbt` y comprueba si deja de
colisionar en el paso 14. La carpeta nueva sera
`resultados/diagnostico_reglas_meta_lejana_v6_max120/`. Despues ejecuta
`worlds/marte_qlearning.wbt`, que entrenara una tabla nueva y guardara en
`resultados/diagnostico_ql_meta_lejana_v6_max120/`. El evaluador separado
`worlds/marte_evaluacion.wbt` cargara esa tabla y escribira en
`resultados/diagnostico_evaluacion_ql_lejana_v6_max120/`.

## Resultados v6 y panel del Lidar en Webots

La corrida v6 obtuvo 10/10 metas con reglas, siempre en 25 acciones,
sin colisiones. En el paso 14 el Lidar marco inseguros los tres avances:
el rover giro y rodeo la piedra. Q llego 12/60 veces durante entrenamiento,
sin colisiones, pero 0/10 durante evaluacion. Los diez episodios de
evaluacion repitieron un ciclo de giros en la posicion (0.110, 1.104),
a 2.120 m de la meta. Estos datos no demuestran que Q haya convergido.
En el modelo geometrico del mundo, desde esa posicion los tres avances
colisionarian a rumbos 0 y 30 grados; a 60 grados ya queda libre la curva
izquierda y a 90 grados queda libre el avance recto. Q alterna entre
0 y 30 grados, de modo que el Lidar esta vetando trayectorias realmente
inseguras y la politica no completa el giro de escape.

Al ejecutar cualquiera de los tres mundos activos, el dispositivo
`lidar_display` aparece como panel con borde cian dentro de la vista 3D de
Webots. Muestra dos vistas cenitales
de la nube de puntos real: una de 0.8 m y otra de 5 m. El centro blanco es
el rover; las lineas muestran los tres trayectos de un paso, en rojo cuando
la fusion RGB-D + Lidar los considera bloqueados. Si se elige un avance,
ese trayecto se dibuja mas grueso. El panel se actualiza cada dos acciones
y conserva la ultima imagen al terminar el controlador. Se puede mover y
redimensionar dentro de Webots. Si esta oculto, selecciona el rover y
activa `Overlays > Display Devices > lidar_display`; comprueba tambien
que `Hide All Display Overlays` este desactivado. Reabre el mundo para cargar
el nuevo nodo `Display`. `UMARS_LIDAR_CADA` cambia la frecuencia y
`UMARS_LIDAR_VENTANA=0` desactiva el dibujo. El panel solo muestra lecturas
y decisiones; no altera la politica ni la tabla Q.

## Revision v7: romper ciclos de giro

La evaluacion v6 termino 0/10: en la posicion (0.110, 1.104), Q alterno
entre rumbo 0 y 30 grados hasta agotar 120 acciones. En ambos rumbos los
avances chocarian con la piedra; la salida geometrica aparece al continuar
el giro hacia 60 o 90 grados.

El filtro v7 detecta la inversion de giro tras al menos tres giros
consecutivos sin desplazamiento.
Desde entonces mantiene el ultimo sentido de giro mientras todos los
avances esten bloqueados; cuando el Lidar y RGB-D habilitan algun avance,
solo permite elegir entre esos avances. Al moverse, el filtro se reinicia.
El filtro se reinicia tambien al comienzo de cada episodio y se aplica
tanto a la seleccion epsilon-greedy como a las acciones futuras usadas en
la actualizacion Q. No modifica estados, acciones, recompensa, epsilon,
alpha, gamma, episodios ni sensores. Las reglas no usan este filtro.
El CSV agrega `modo_antibucle` y `acciones_permitidas` para comprobarlo.

Primero ejecuta `worlds/marte_qlearning.wbt`; la nueva tabla y los CSV
se guardaran en `resultados/diagnostico_ql_meta_lejana_v7_max120/`.
Luego, si quieres evaluar por separado, abre `worlds/marte_evaluacion.wbt`;
el evaluador cargara la tabla v7 y escribira en
`resultados/diagnostico_evaluacion_ql_lejana_v7_max120/`. La corrida v6
queda conservada. La mejora de exito aun requiere probarse en Webots.

Para aislar el efecto del filtro antes de entrenar otra tabla, tambien puedes
evaluar la tabla v6 existente con el controlador v7. Antes de iniciar una
nueva instancia de Webots desde PowerShell, configura:

```powershell
$env:UMARS_MAX_ACCIONES = '120'
$env:UMARS_EVALUACION = '10'
$env:UMARS_POLITICA = 'q'
$env:UMARS_Q_PATH = (Resolve-Path 'resultados/diagnostico_ql_meta_lejana_v6_max120/q_table.npy').Path
$env:UMARS_SALIDA = (Join-Path (Get-Location) 'resultados/evaluacion_v6_con_antibucle')
```

Abre `worlds/marte_evaluacion.wbt` y pulsa **Run**. Esta prueba usa Q v6 sin
actualizarla y guarda sus CSV aparte; para volver a evaluar v7, elimina esas
dos variables de entorno y reinicia Webots antes de abrir el evaluador.

## Prueba de generalizacion: meta al sur

La corrida v7 con la meta original `(2.2, 0.75)` obtuvo 44/60 metas en
entrenamiento y 10/10 en evaluacion integrada y separada. Los diez
episodios de evaluacion recorrieron la misma trayectoria de 107 acciones;
eso comprueba repetibilidad en un solo escenario, no generalizacion.

Para probar otra meta sin reentrenar, abre
`worlds/marte_evaluacion_meta_sur.wbt` y pulsa **Run**. Conserva el inicio,
las tres rocas, las observaciones y la tabla Q v7; solo desplaza la meta
a `(2.2, -0.75)`. El evaluador usa `epsilon=0` y no actualiza Q. Guarda
los resultados por separado en
`resultados/diagnostico_evaluacion_ql_meta_x2p20_ym0p75_v7_max120/`.
El mundo original `worlds/marte_evaluacion.wbt` sigue con la meta
`(2.2, 0.75)` y su carpeta de resultados anterior no se sobrescribe.
Si habias configurado `UMARS_Q_PATH` o `UMARS_SALIDA` para otra prueba,
retira esas variables y reinicia Webots antes de ejecutar este mundo.

Para comprobar que la meta sur es alcanzable con las mismas observaciones,
puedes repetir este mundo con `UMARS_POLITICA=reglas` en un proceso nuevo
de Webots. El evaluador guarda esa referencia en una carpeta separada
con `reglas` en el nombre.

### Resultados medidos con la meta sur (19/11/2026)

La evaluacion separada de la misma tabla Q v7 registro 10/10 metas,
0 colisiones, 33 acciones y retorno 73.95302 en cada episodio. La posicion
final fue `(2.1176, -1.0371)`, a 0.2987 m de la meta `(2.2, -0.75)`;
el radio de llegada configurado es 0.35 m. Los 10 episodios tienen
exactamente la misma secuencia de acciones y posiciones. No hubo
exploracion (`epsilon=0`) ni actualizaciones de Q en el evaluador.

La ruta pasa por debajo de la roca central y de la piedra sur. Usando los
rectangulos de colision del mundo, el radio de chasis de 0.25 m y los
segmentos entre posiciones registradas, la holgura minima aproximada fue
0.0415 m junto a la roca central y 0.0489 m junto a la piedra sur. El
filtro antibucle intervino en 4 de las 33 acciones: mantuvo tres giros a
la derecha y despues habilito un avance. La meta norte original habia
requerido 107 acciones y habia dado retorno -0.1331 con esta tabla.

Esto demuestra que la politica llega a dos metas en el mismo mapa e inicio.
Las diez repeticiones de cada meta son deterministas y no prueban robustez
ante cambios de posicion inicial, obstaculos o ruido. La holgura pequena
tambien limita lo que se puede concluir sobre seguridad en otro mapa.

## Prueba controlada de generalizacion por punto de partida

Los mundos dedicados activan automaticamente el modo de generalizacion:
el evaluador ejecuta una vez cada
inicio `base=(-1.5, 0.0)`, `norte=(-1.5, 0.5)`, `sur=(-1.5, -0.5)` y
`oeste=(-2.0, 0.0)`, todos con rumbo inicial de 0 grados. Comprueba que
cada posicion esta dentro del terreno y fuera de las rocas y la meta.
Se mantienen la tabla Q v7, el mapa, las observaciones, las cinco acciones,
el limite de 120 acciones y `epsilon=0`. Q no se actualiza. Para reglas se
usan las mismas posiciones, sensores y movimientos. Cada ejecucion crea
una carpeta unica bajo `resultados/generalizacion/`, con CSV y
`configuracion.json` que incluye el SHA256 de la tabla Q. La tabla original
y las corridas anteriores no se sobrescriben.

Hay dos mundos dedicados con la misma geometria y el controlador
`evaluar_generalizacion`:
`worlds/marte_generalizacion_norte.wbt` (meta `2.2, 0.75`) y
`worlds/marte_generalizacion_sur.wbt` (meta `2.2, -0.75`). Este controlador
activa `UMARS_GENERALIZACION=1` antes de ejecutar `evaluar.py`; no hace
falta configurar esa variable a mano. Los mundos de evaluacion antiguos
siguen disponibles para repetir el escenario de inicio fijo.

Desde PowerShell, en la raiz del proyecto, prepara una corrida:

```powershell
$env:UMARS_POLITICA = 'q'       # Luego repetir con 'reglas'
$env:UMARS_MAX_ACCIONES = '120'
$env:UMARS_LIDAR_VENTANA = '0' # Solo desactiva el dibujo; el sensor sigue activo
Remove-Item Env:\UMARS_Q_PATH -ErrorAction SilentlyContinue
Remove-Item Env:\UMARS_SALIDA -ErrorAction SilentlyContinue
& 'C:\Program Files\Webots\msys64\mingw64\bin\webots.exe'
```

En Webots, usa **File > Open World** para abrir el mundo norte y pulsa
**Run** hasta ver `RESUMEN EVALUACION`. Despues abre el mundo sur y espera
su resumen. Cierra Webots, cambia `UMARS_POLITICA` a `reglas`, inicialo
otra vez y repite norte y sur. Se requieren cuatro corridas en total;
Webots debe arrancar de nuevo tras cambiar de politica para heredarla.
El evaluador imprime la carpeta de salida antes de empezar.

Al terminar, compara los cuatro conjuntos de CSV con:

```powershell
.\.venv\Scripts\python.exe herramientas\resumir_generalizacion.py
```

El resumen ignora corridas incompletas y muestra resultado, pasos y retorno
por inicio y politica, ademas de metas, colisiones y retorno medio. Esta
prueba aun no introduce ruido ni cambia obstaculos. Al preparar este modo,
las 14 pruebas locales pasaron; la corrida nueva en Webots queda pendiente
de ejecutarse desde la interfaz.

La primera prueba del 24/11/2026 uso los mundos de evaluacion sin activar
el modo de generalizacion. Sus cuatro CSV tienen diez repeticiones de
`inicio=base`, por lo que `resumir_generalizacion.py` los omite. Se
conservan bajo las carpetas `diagnostico_evaluacion_*`; no son evidencia
de los otros tres puntos de partida.
