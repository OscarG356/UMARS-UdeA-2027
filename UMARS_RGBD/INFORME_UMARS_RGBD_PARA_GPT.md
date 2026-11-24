# UMARS_RGBD: estado del proyecto y guia para revisar las matematicas

**Corte de datos:** 24 de noviembre de 2026. Este documento resume el codigo
y los CSV presentes en el proyecto. La fuente compacta es
`resultados/resumen_experimentos_umars.csv`; el detalle por episodio esta en
`resultados/episodios_experimentos_umars.csv`. Las trayectorias paso a paso
permanecen en los CSV originales indicados por esas dos tablas.

## 1. Objetivo y alcance real

El proyecto simula en Webots un rover que debe llegar a una meta evitando
tres rocas sobre un terreno de 6 x 4 m. Se comparan una politica por reglas
y un agente de **Q-learning tabular**. El proyecto empezo con percepcion
RGB-D estacionaria, paso a 24 estados y tres acciones, despues a cinco
acciones, 144 estados, comprobacion de trayectorias, Lidar y un filtro para
romper ciclos de giros. La version activa es **v7**, con tabla Q de 144 x 5.

La navegacion usa profundidad de un `RangeFinder` y una nube de puntos del
Lidar. La camara RGB esta habilitada, pero sus colores **no intervienen**
en el estado de Q ni en la politica de navegacion. El movimiento se aplica
directamente a `translation` y `rotation` mediante un `Supervisor` de
Webots: no hay motores, dinamica de ruedas, deslizamiento ni odometria real.
La posicion exacta del rover y la meta se usa para definir rumbo y distancia
a la meta, y para calcular recompensas. Las cajas de las rocas se usan para
validar colisiones y finalizar episodios; no se entregan directamente al
agente como observacion. `COLISION_*` significa que se rechazo una
trayectoria con el modelo geometrico, no un impacto medido fisicamente.

No se han incorporado DQL, ROS 2, ruido perceptual controlado ni pruebas con
obstaculos nuevos.

## 2. Archivos que implementan el sistema actual

| Archivo | Papel |
|---|---|
| `controllers/umars_qlearning/agente_q.py` | Acciones, codificacion de estado, epsilon-greedy, actualizacion Q, memoria de rodeo y filtro antibucle. |
| `controllers/umars_qlearning/percepcion.py` | Regiones de profundidad y seguridad de las tres trayectorias de avance, fusionadas con Lidar. |
| `controllers/umars_qlearning/movimientos.py` | Geometria de avances rectos, arcos y giros de 30 grados. |
| `controllers/umars_qlearning/entorno.py` | Geometria del terreno y rocas, colision, meta, recompensa y terminacion. |
| `controllers/umars_qlearning/umars_qlearning.py` | Entrenamiento, evaluacion integrada, registros CSV y guardado de Q. |
| `controllers/umars_qlearning/politica_reglas.py` | Referencia heuristica con las mismas observaciones y acciones. |
| `controllers/umars_qlearning/visualizar_lidar.py` | Panel de Lidar dentro de Webots; solo visualiza. |
| `controllers/evaluar/evaluar.py` | Evaluacion separada: carga Q, fija epsilon=0 y no la actualiza. |
| `controllers/evaluar_generalizacion/evaluar_generalizacion.py` | Activa cuatro inicios desde los mundos dedicados. |
| `herramientas/test_qlearning.py` | 14 pruebas locales de logica, sin Webots. |
| `herramientas/exportar_experimentos.py` | Regenera los dos CSV consolidados de este informe. |

Los mundos activos son `worlds/marte_qlearning.wbt` para entrenar,
`worlds/marte_generalizacion_norte.wbt` para meta `(2.2, 0.75)` y
`worlds/marte_generalizacion_sur.wbt` para meta `(2.2, -0.75)`. Los dos
ultimos usan la misma geometria y solo cambian la meta. La tabla empleada
en las pruebas actuales es
`resultados/diagnostico_ql_meta_lejana_v7_max120/q_table.npy`, de 144 x 5,
con 354 valores distintos de cero de un total de 720. Su SHA256 es:

```text
cdae124fb748e478299231413f38ff28001b086a8a30d7b9ed3762547a7e4e6c
```

## 3. Observacion y seguridad

La imagen de profundidad se divide en tres regiones horizontales solapadas:
izquierda `[0, 0.40]`, centro `[0.30, 0.70]` y derecha `[0.60, 1]` del
ancho. Se analiza la franja vertical que va de `0.38` a `0.58` de la
altura. Un retorno infinito se interpreta como alcance maximo de 5 m;
lecturas no validas pueden producir `DESCONOCIDO`. La distancia de una
region es el percentil 20 de sus lecturas validas. Con distancia menor a
1.50 m se clasifica `OCUPADO`; en otro caso, `LIBRE`.

Para la seguridad del siguiente movimiento se proyectan los pixeles de
profundidad axial al plano local del rover. Para una columna `u`, anchura
`W`, profundidad `z`, campo visual horizontal `F=2.1 rad` y sensor a
`x_s=0.19 m`:

```text
x = x_s + z
y = (1 - 2(u + 0.5)/W) * tan(F/2) * z
```

Cada punto del RGB-D y del Lidar se compara con muestras de cada una de
las tres trayectorias de avance. Una trayectoria se considera insegura si
algun punto queda a `0.27 m` o menos de ella: radio geometrico del chasis
`0.25 m` mas margen `0.02 m`. La autorizacion final es:

```text
avance_seguro(a) = RGBD_seguro(a) AND Lidar_seguro(a)
```

El Lidar del mundo es fijo, de una capa, 270 grados y 181 muestras
horizontales. Los giros en el sitio siempre siguen disponibles en el
filtro basico. La seguridad de percepcion y la comprobacion geometrica del
`Supervisor` son mecanismos distintos: la primera limita las acciones
antes de elegir; la segunda rechaza una trayectoria que aun resultara
invalida al ejecutarla.

## 4. Espacio de estados y acciones

El estado actual tiene cuatro componentes:

1. Ocupacion binaria izquierda-centro-derecha: 8 patrones. Tanto `OCUPADO`
   como `DESCONOCIDO` valen 1; `LIBRE` vale 0.
2. Direccion aproximada de la meta: izquierda `-1`, frente `0` o derecha
   `+1`, segun el error angular respecto del rumbo, con umbral de 30 grados.
3. Lado que se esta usando para rodear una roca: ninguno `0`, izquierda
   `1` o derecha `2`.
4. Distancia a la meta: lejos `0` si `d >= 2.5 m`, cerca `1` si `d < 2.5 m`.

Esto produce `8 * 3 * 3 * 2 = 144` estados. Si `b` es el entero de los
tres bits de ocupacion, `g` la direccion de meta, `m` el lado de rodeo y
`n` la clase de distancia, el indice exacto es:

```text
s = 2 * [3 * (3b + g + 1) + m] + n,       0 <= s <= 143
```

La tabla tiene cinco acciones en este orden, que tambien es el orden de
las cinco columnas de Q:

| Indice | Accion | Efecto nominal |
|---:|---|---|
| 0 | `AVANZAR` | 0.20 m recto. |
| 1 | `GIRAR_IZQUIERDA` | +30 grados, sin desplazamiento. |
| 2 | `GIRAR_DERECHA` | -30 grados, sin desplazamiento. |
| 3 | `AVANZAR_IZQUIERDA` | Arco de 0.20 m y +30 grados. |
| 4 | `AVANZAR_DERECHA` | Arco de 0.20 m y -30 grados. |

Para un avance recto desde `(x,y,theta)`:

```text
x' = x + 0.20 cos(theta)
y' = y + 0.20 sin(theta)
theta' = theta
```

Para un arco, `delta=+pi/6` a la izquierda o `-pi/6` a la derecha,
`R=0.20/delta`:

```text
x' = x + R[sin(theta + delta) - sin(theta)]
y' = y - R[cos(theta + delta) - cos(theta)]
theta' = theta + delta
```

La curva se muestrea en incrementos cercanos a 2.5 cm para verificarla.
Un giro puro solo cambia `theta`. El control del chasis es una asignacion
de pose al nodo, no un comando de velocidad a ruedas.

## 5. Recompensa, terminacion y aprendizaje

Sea `d_t` la distancia del rover a la meta antes de la accion y `d_(t+1)`
la distancia despues. La recompensa usada por el controlador actual es:

```text
r_t = -1 + 2(d_t - d_(t+1))
      - 50 si hay colision geometrica o salida del terreno
      + 100 si se entra en el radio de meta sin colision
```

La meta se alcanza con distancia `<= 0.35 m`. Colision y meta terminan
el episodio. Tambien termina al llegar a 120 acciones, sin bonificacion ni
penalizacion terminal adicional. El retorno registrado en CSV es la suma
**sin descuento** de recompensas. Cuando se llega a meta sin colision,
la suma de los progresos telescopa:

```text
retorno = 100 - T + 2(d_inicial - d_final)
```

Por ejemplo, desde el inicio base a la meta norte, Q tardo 107 pasos:
`100 - 107 + 2(3.7752 - 0.3418) ~= -0.133`. El retorno negativo cercano
a cero es consecuencia de los pasos adicionales; no indica por si mismo
un error de registro de recompensa. Reglas tardo 25 pasos y obtuvo 82.205.

El agente usa `alpha=0.10`, `gamma=0.95` y semilla 42. Parte de Q en cero.
Durante entrenamiento, la probabilidad de explorar empieza en 1.0 y se
actualiza al terminar cada episodio:

```text
epsilon_siguiente = max(0.05, 0.95 * epsilon_actual)
```

La exploracion escoge aleatoriamente entre las acciones permitidas; en el
otro caso se elige una accion con el Q maximo de ese mismo conjunto, con
desempate reproducible. La actualizacion es:

```text
Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_{a' en A_permitidas(s')} Q(s',a') - Q(s,a)]
```

Si la transicion es terminal, el objetivo es solo `r`. En la fase de
evaluacion `epsilon=0` y no se llama a la actualizacion. El maximo de
acciones futuras se calcula sobre las acciones que el sensor y los filtros
permiten; no es el maximo irrestricto de las cinco columnas.

**Atencion matematica:** el filtro antibucle guarda `ultimo_giro`,
`giro_escape` y `giros_sin_avance`, pero esa memoria no forma parte de los
144 estados de Q. Ademas, la lista de acciones permitidas depende del
error angular preciso, mientras Q solo guarda tres sectores. Por ello,
el mismo indice `s` puede tener diferentes conjuntos de acciones
disponibles y diferentes decisiones del filtro. Esta es una hipotesis
concreta para estudiar como posible fuente de no-Markovianidad y de
ineficiencia; los CSV por si solos no prueban que sea la unica causa.

## 6. Evolucion medida de los experimentos

Los valores siguientes salen de `resultados/resumen_experimentos_umars.csv`.
`E/T` significa exitos sobre episodios terminados. Estas versiones
cambiaron acciones, estados o sensores: **no son replicas bajo identica
configuracion**. Las filas de reglas son una referencia para la version
indicada, cuando existe un CSV correspondiente.
Las ecuaciones de las secciones 3 a 5 describen el **codigo v7 actual**;
no deben atribuirse sin mas a v1-v6. El proyecto conserva CSV y el
diagnostico historico, pero no todos los controladores originales de
cada version.

| Configuracion | Q entrenamiento | Q evaluacion integrada | Reglas | Cambio principal |
|---|---:|---:|---:|---|
| Meta cercana, 24 x 3 | 51/60 | 10/10 | sin corrida comparable | Meta cercana; exito no se transfirio a la meta lejana. |
| Meta lejana inicial, 24 x 3 | 0/60 | 0/10 | sin corrida comparable | Colisiones y salidas del terreno; 24 terminaciones geometricas en entrenamiento. |
| v2, 24 x 3 | 0/60 | 0/10 | 0/10 | Campo visual ampliado y orientacion a la meta. |
| v3, 24 x 5 | 0/60 | 0/10 | 10/10 | Dos avances curvos. |
| v4, 144 x 5, 60 pasos | 2/60 | 0/10 | sin corrida comparable | Memoria de lado y clase de distancia. |
| v4, 144 x 5, 120 pasos | 4/60 | 0/10 | sin corrida comparable | Horizonte duplicado. |
| v5, 144 x 5 | 5/60 | 0/10 | 0/10 | Proyeccion RGB-D y veto por trayectoria; reglas tuvo 10/10 colisiones contra la piedra lateral. |
| v6, 144 x 5 | 12/60 | 0/10 | 10/10 | Lidar cubre el punto ciego; Q aun alternaba giros. |
| v7, 144 x 5 | 44/60 | 10/10 | 10/10 | Filtro antibucle durante entrenamiento y evaluacion. |

En v7, entrenamiento tuvo **44 metas, 10 limites de acciones y 6 salidas
del terreno** en 60 episodios; retorno medio `3.179`. La evaluacion
integrada de la meta norte repitio diez veces la misma ruta de 107 acciones,
retorno `-0.133` y distancia final `0.3418 m`. La evaluacion separada de
meta sur repitio diez veces una ruta de 33 acciones, retorno `73.953`.

Existen otros archivos historicos (`diagnostico_evaluacion*`,
`resultados/episodios.csv`, `evaluacion_generalizacion`) que el CSV
consolidado conserva con su fuente y sin adjudicarles automaticamente
una version si no se puede verificar. Dos fuentes tienen transiciones pero
**cero episodios completos**: la evaluacion separada v6 y
`fase2_meta_cercana`. El consolidado las marca como parciales; no deben
interpretarse como tasas de exito.

## 7. Generalizacion controlada de la tabla v7

Se evaluo la **misma** Q v7, sin entrenamiento adicional, con metas norte
`(2.2, 0.75)` y sur `(2.2, -0.75)`. Para cada meta se probaron cuatro
inicios: `base=(-1.5,0)`, `norte=(-1.5,0.5)`, `sur=(-1.5,-0.5)` y
`oeste=(-2,0)`, todos con rumbo 0 grados. Reglas uso los mismos mundos,
observaciones y acciones. Hubo dos corridas Q identicas por meta; la
comparacion siguiente usa una sola de cada una, no cuenta las duplicadas
como muestras independientes.

| Meta | Inicio | Q: resultado / pasos / retorno | Reglas: resultado / pasos / retorno |
|---|---|---|---|
| Norte | base | META / 107 / -0.133 | META / 25 / 82.205 |
| Norte | norte | META / 42 / 64.982 | META / 23 / 83.780 |
| Norte | sur | META / 26 / 81.234 | META / 33 / 74.372 |
| Norte | oeste | META / 91 / 16.881 | META / 27 / 80.876 |
| Sur | base | META / 33 / 73.953 | META / 31 / 75.898 |
| Sur | norte | META / 56 / 51.158 | META / 34 / 73.294 |
| Sur | sur | META / 34 / 72.986 | META / 37 / 69.839 |
| Sur | oeste | META / 75 / 32.873 | META / 35 / 73.124 |

Ambas politicas tuvieron **8/8 llegadas y 0 colisiones geometricas** en
esta prueba. Q necesito **464 acciones** en total (media 58, retorno medio
49.242) y reglas **245** (media 30.625, retorno medio 76.674). Q fue mas
rapida en dos de ocho pares de rutas, pero en conjunto hizo 219 acciones
mas, alrededor de un 89 % adicional.

El problema visible es la **ineficiencia de Q al rodear rocas**, no la
incapacidad de alcanzar estas ocho combinaciones de inicio y meta. En la
ruta base hacia la meta norte, Q hizo 73 giros de 107 acciones; reglas hizo
3 giros en 25 acciones. En 55 de los 73 giros de Q, el CSV solo permitia
girar, porque los tres avances estaban bloqueados. En 18 giros habia al
menos un avance permitido. Entre los pasos 36 y 45, Q permanecio en
`(0.1085, 1.0723)` durante diez giros; el filtro antibucle intervino
despues. El estado 137 reaparece en distintas orientaciones con la misma
fila Q, ejemplo de la resolucion limitada del estado.

Al reconstruir las trayectorias con las muestras de `movimientos.py` y
las cajas del mundo, algunas rutas pasaron a unos **2 cm de holgura
geometrica** respecto del radio de chasis. Este calculo usa el modelo y
posiciones CSV redondeadas: no es una medida fisica de seguridad. Los
episodios son deterministas, con las mismas rocas y rumbo inicial; no
prueban robustez frente a cambios de mapa, ruido o dinamica real.

## 8. Como usar los CSV entregados

`resultados/resumen_experimentos_umars.csv` tiene **40 filas**: una por
carpeta y fase, con cantidad de episodios, exitos, terminaciones por
colision o terreno, limites de acciones, medias de pasos y retorno,
giros, uso del filtro, forma y hash de la Q cuando se conoce, y rutas de
origen. Es el archivo recomendado para una primera lectura por GPT.

`resultados/episodios_experimentos_umars.csv` tiene **791 filas**: 789
episodios y dos marcadores de fuente sin episodios completos. Incluye el
inicio cuando se registro, el resultado y la distancia final de cada
episodio, conteo de los cinco movimientos, giros con y sin avance
permitido, pasos con filtro, huella de trayectoria y referencia al CSV
original. Los campos no medidos historicamente se dejan vacios. Los
campos `meta_fuente` y `version_nombre` distinguen datos del CSV de
inferencias prudentes basadas en nombres y documentacion. Los registros
con `estado_registro != completo` no son episodios validos.

Los CSV originales de `transiciones` guardan cada paso, incluidos estado,
valores Q, accion, recompensa, distancia, rumbo, posicion y banderas de
sensores, segun la version. Se recomiendan para examinar una ruta concreta.
Para regenerar las dos tablas sin borrar los CSV originales:

```powershell
.\.venv\Scripts\python.exe herramientas\exportar_experimentos.py
```

## 9. Preguntas concretas para una revision matematica con GPT

Entregar este informe, los dos CSV consolidados y los archivos de codigo
de la seccion 2. Pedir que responda con formulas y ejemplos numericos:

1. Derivar la codificacion `s` de 144 estados y explicar que informacion
   se pierde al convertir profundidades, rumbos y distancias en categorias.
2. Verificar las ecuaciones del movimiento recto y curvo, el radio
   `R=paso/giro`, y la coherencia entre seguridad RGB-D/Lidar y trayectoria.
3. Derivar la recompensa total de una ruta y explicar por que Q puede
   llegar a la meta con retorno cercano a cero.
4. Comprobar la actualizacion Q, el caso terminal, el descuento `gamma`,
   epsilon-greedy y el maximo limitado a las acciones seguras.
5. Analizar si el estado de Q es suficientemente Markoviano cuando el
   filtro antibucle y el error angular preciso afectan las acciones
   disponibles sin estar codificados en `s`.
6. Comparar las transiciones de la ruta norte desde `base` y `oeste` con
   las de reglas. Separar giros forzados por seguridad de giros elegidos
   por Q. Identificar una correccion pequena y una prueba que aisle su
   efecto antes de cambiar varios parametros o entrenar otro sistema.

**Peticion sugerida:** "Explicame matematicamente el Q-learning de este
proyecto usando solo el codigo y los CSV adjuntos. Distingue hechos
observados de hipotesis. Calcula un ejemplo real de estado, movimiento,
recompensa y actualizacion Q. Explica por que Q da 8/8 metas pero usa
muchos mas giros que reglas. Propone una sola mejora verificable sin DQL
ni ROS 2 y dime que experimento deberia compararla".
