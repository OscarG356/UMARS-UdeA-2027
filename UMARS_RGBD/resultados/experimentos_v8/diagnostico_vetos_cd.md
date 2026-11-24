# Diagnóstico de los vetos de trayectoria en UMARS v8

**El sensor Lidar estuvo activo en las seis corridas.** El lote ocultó su panel visual en C y D. La diferencia que hizo divergir a las políticas fue la penalización de entrenamiento. En evaluación, D eligió 27 veces un avance que sus sensores admitían y que la comprobación geométrica rechazó por cruzar el límite del terreno. En los 27 casos el filtro anterior a la elección también admitía `GIRAR_DERECHA`, y esa alternativa pasaba la comprobación geométrica para el paso registrado.

## Configuración y sensor Lidar

Se compararon los seis JSON del [lote pareado](comparacion_cd.md), sus 720 episodios de entrenamiento y 120 episodios de evaluación. Para cada semilla, los JSON difieren en dos campos: el identificador `experimento` y `penalizacion_giro` (C = 0,0, D = 0,2). El identificador etiqueta la variante. Ambas ejecutan el mismo controlador y mundo dinámico, empiezan con una tabla de ceros de 144 × 5, usan las mismas semillas, inicio, meta, velocidades y fases de rocas por episodio en ambas fases. Comparten 120 episodios de entrenamiento, 20 de evaluación, máximo de 120 acciones, α = 0,10, γ = 0,95 y el mismo programa de ε (1,0 con factor 0,95 y mínimo 0,05 en entrenamiento, 0 en evaluación). Los JSON carecen de una huella del código ejecutado. La reproducción de las decisiones y de las seis tablas Q finales con el código actual ofrece una comprobación independiente de la consistencia del algoritmo registrado. [Lanzador](../../herramientas/comparar_cd_v8.py) · [Controlador v8](../../controllers/umars_v8/umars_v8.py) · [Agente Q](../../controllers/umars_qlearning/agente_q.py)

`UMARS_V8_PANEL_LIDAR=0` solo hace que `PanelLidar.mostrar()` regrese antes de dibujar en `lidar_display`. El dispositivo `lidar_seguridad` se habilita cada 32 ms, su nube se activa con `enablePointCloud()` y `observar()` llama a `getPointCloud()` y fusiona los tres indicadores de avance mediante una conjunción de profundidad y Lidar. Una nube ausente o vacía interrumpe el controlador con error. Las **30 664 transiciones** del lote contienen `lidar_min_m` positivo y finito, incluidas las 27 acciones vetadas. En evaluación de la semilla 1042 se registraron 273 valores distintos en C y 201 en D. En las 210 comparaciones paso a paso hasta la primera decisión diferente de cada escenario de evaluación, coinciden el estado, el mínimo Lidar, los indicadores de avance, la lista permitida en su orden y el estado del antibucle. El CSV guarda el mínimo y los indicadores fusionados. La contribución de cada sensor a cada indicador exigiría la nube y la imagen originales. [Controlador v8](../../controllers/umars_v8/umars_v8.py) · [Visualización](../../controllers/umars_qlearning/visualizar_lidar.py) · [Fusión sensorial](../../controllers/umars_qlearning/percepcion.py)

## Qué comprueba cada filtro y cómo termina un episodio

1. **Antes de elegir.** `FiltroAntibucle.permitidas()` usa los avances seguros estimados por profundidad y Lidar, el error angular a la meta y su memoria de giros. Esa lista restringe la exploración y el máximo Q. Los límites del terreno y las posiciones futuras de las rocas quedan fuera de esa lista.
2. **Después de elegir, antes de mover el rover.** `validar_accion_temporal()` proyecta la acción durante 96 ms. Muestrea al menos 20 intervalos, incluido el inicio y el final, y comprueba el disco del rover de radio 0,25 m contra el borde y los rectángulos de las rocas en el tiempo correspondiente. La primera posición inválida impide el movimiento y asigna provisionalmente `VETO_TRAYECTORIA`. El rover queda quieto y las rocas siguen actualizándose durante los tres subpasos. Si aparece una intersección en esos subpasos, el registro final pasa a `CONTACTO_GEOMETRICO`.
3. **Al evaluar el resultado.** Un motivo de colisión o salida del terreno termina el episodio, incluso si se bloqueó el movimiento. Un contacto geométrico es la intersección detectada en una pose efectivamente alcanzada durante un subpaso, incluida la de un rover quieto cuando una roca se acerca. `MAX_ACCIONES` es el final por llegar a 120 acciones sin meta ni motivo de colisión. Si coinciden en el último paso, el motivo de colisión o el éxito tiene prioridad. [Controlador v8](../../controllers/umars_v8/umars_v8.py) · [Validación geométrica](../../controllers/umars_v8/control_v8.py) · [Entorno y recompensa](../../controllers/umars_qlearning/entorno.py)

| Terminación de evaluación | C | D |
|---|---:|---:|
| Llegada a la meta | 46 | 28 |
| Veto final por límite del terreno | 0 | 27 |
| Contacto geométrico con la roca izquierda | 14 | 5 |
| Límite de 120 acciones | 0 | 0 |

El campo agregado `colision` suma 14 para C y 32 para D porque incluye los vetos. El replay del validador identificó una colisión futura con la roca izquierda en las 19 acciones que terminaron registradas como contacto. Fueron giros puros bloqueados y hubo contacto durante la espera de los subpasos. Contar solo `VETO_TRAYECTORIA` mide los vetos que conservaron esa etiqueta al final. [Resultados pareados](comparacion_cd.md)

La recompensa base de ambas variantes es `−1 + 2 × (distancia antes − distancia después)`, con −50 adicionales ante un motivo de colisión y +100 al llegar. Un veto por borde sin desplazamiento da −51. D añade −0,20 a un giro puro si alguna bandera de avance fusionada es verdadera y la transición todavía no terminó por meta o colisión. El controlador aplica el corte por máximo de acciones después de calcular ese coste, por lo que el último giro de un episodio agotado puede pagar la penalización. La actualización Q solo se ejecuta en entrenamiento. En evaluación la penalización queda registrada como recompensa de aprendizaje y actúa sobre la política únicamente a través de los Q aprendidos previamente. En el replay con las acciones permitidas registradas, coincidieron las 30 664 recompensas base y de aprendizaje, las selecciones y las seis tablas Q finales. La coincidencia comprueba el cálculo con las observaciones guardadas. El CSV carece de las imágenes y las nubes completas para recalcular la percepción desde cero. [Código de recompensa](../../controllers/umars_qlearning/entorno.py) · [Coste de giro](../../controllers/umars_v8/control_v8.py) · [Actualización Q](../../controllers/umars_qlearning/agente_q.py)

## Semilla 1042

En el primer paso del entrenamiento, C y D observaron el estado 42, leyeron 1,375 m en el Lidar y ejecutaron el mismo `GIRAR_DERECHA`. La recompensa base fue −1,0. El coste adicional de D hizo que la primera actualización de Q de ese giro fuera −0,12 frente a −0,10 de C. La **primera elección distinta durante el entrenamiento** fue en el episodio 9, paso 12. El estado 72, la pose, el mínimo Lidar de 0,3068 m y la lista de dos giros eran iguales y los tres avances estaban bloqueados. C eligió izquierda (Q −0,708766 frente a −0,736355 para derecha) y D eligió derecha (Q −0,823235 frente a −0,829627 para izquierda). Ambos giros se ejecutaron y el coste adicional fue cero en ese paso. La diferencia provino de los Q acumulados.

En los 20 escenarios de evaluación las decisiones divergieron por primera vez en el **paso 5, estado 30**. C prefirió `AVANZAR_DERECHA` y corrigió rumbo de +60° a +30°. D prefirió `AVANZAR` y conservó +60°. Ambos tenían los tres avances marcados seguros y las cinco acciones permitidas. Las dos acciones pasaron el validador temporal en ese momento. Más adelante D acumuló **18 vetos por borde**, todos al elegir `AVANZAR_DERECHA`. Quince de esos 18 vetos ocurrieron en escenarios en los que C sí llegó. D tuvo otro fallo por contacto y llegó en un escenario en el que C también llegó. [Transiciones de C 1042](C/q_20261124_133511_9efb8f25/transiciones.csv) · [Transiciones de D 1042](D/q_20261124_140316_6809930e/transiciones.csv)

En el escenario **101043**, el veto ocurrió en el paso 16 de D, estado 13. El rover estaba en `(0,7582; 1,7120) m` a +30°. El filtro dejó `AVANZAR_DERECHA` (Q 10,353554) y `GIRAR_DERECHA` (Q 8,293066), con las tres banderas sensoriales de avance activas. El arco seleccionado habría llevado el centro hasta y = 1,7632 m, cuando el máximo admisible es 1,75 m por el margen del chasis. El replay encontró el primer cruce al 50 % de la acción. El rover permaneció en su posición y el episodio terminó con −51. En los 27 vetos del lote se observó la misma elección, con el centro antes de la acción entre y = 1,7120 y 1,7161 m, rumbo +30° y primer cruce entre el 45 % y el 50 % de la trayectoria. [Transiciones de D 1042](D/q_20261124_140316_6809930e/transiciones.csv) · [Transiciones de D 2042](D/q_20261124_142425_a34ee0f3/transiciones.csv) · [Tamaño del terreno](../../worlds/marte_v8_dinamico.wbt)

## Giros necesarios y alcance de la evidencia

La penalización usa las banderas sensoriales **antes** de aplicar las restricciones por rumbo y el antibucle. D penalizó 2 621 giros durante el entrenamiento. En **1 247** de esos pasos la lista realmente permitida contenía un único giro puro. En **639** de esos 1 247 pasos, la separación entre el disco del rover y la roca móvil más próxima era de 20 cm o menos al comienzo de la acción. Esto confirma que D puede cobrar un giro obligatorio para la política incluso cerca de una roca móvil. La proximidad es una medida descriptiva, no una prueba de que el giro fuera indispensable para completar el rodeo.

En el replay se comprobaron los tres avances geométricos en cada giro penalizado de D, tanto en entrenamiento como en evaluación. Hubo **un** giro penalizado para el que los tres avances tenían veto geométrico. En entrenamiento de la semilla 1042, episodio 94, paso 33, la única acción permitida era `GIRAR_DERECHA`, el rover estaba a unos 8,7 cm de la roca norte y los tres avances cruzaban el borde. El giro pasó la validación y pagó −0,20. En el caso comprobado la restricción que hacía necesario girar era el borde. En los demás giros penalizados había al menos un avance geométricamente admisible para ese paso. Su utilidad para completar el rodeo varios pasos después sigue abierta. También queda abierta la contribución de los giros penalizados cerca de rocas a la preferencia aprendida que lleva a D hacia el borde. [Coste de giro](../../controllers/umars_v8/control_v8.py) · [Filtro antes de elegir](../../controllers/umars_qlearning/agente_q.py) · [Transiciones de D 1042](D/q_20261124_140316_6809930e/transiciones.csv)

## Una modificación recomendada y su prueba

**Excluir las trayectorias que cruzan el borde antes de elegir la acción.** Aplicar una comprobación común a los candidatos de C y D, usando la misma pose, el mismo radio y la misma proyección que ya usa el validador. Para aislar el mecanismo observado, la nueva comprobación se limitaría al borde y dejaría la validación temporal de las rocas en su lugar actual.

El primer control ya se hizo fuera de Webots. Reconstruí la pose anterior a cada uno de los 27 vetos, descarté los candidatos que cruzaban el borde y apliqué el mismo criterio de máximo Q y desempate. En **27/27 casos**, la acción de reemplazo fue `GIRAR_DERECHA` y pasó también la validación con rocas para ese paso. Este resultado se refiere a la acción inmediata. El rumbo cambia después y los siguientes pasos quedan por comprobar.

La prueba de su efecto en llegadas sería una evaluación corta con la tabla D de la semilla 1042 congelada, ε = 0 y los mismos 20 escenarios. Comparar la política registrada con la misma tabla y la comprobación de borde activada. Medir vetos finales por borde, contactos, llegadas, límites de pasos, acciones y giros en las llegadas compartidas. La prueba tiene éxito si baja de 18 vetos por borde, supera 1 llegada y mantiene como máximo el contacto geométrico observado en la corrida original. También permite detectar si los vetos se convierten en contactos o en agotamiento de pasos. La auditoría se hizo con los archivos guardados, sin entrenar de nuevo ni modificar el controlador, los resultados originales, el espacio de estados, las acciones o los parámetros.

## Registro de las primeras decisiones diferentes cuando C llega y D falla

Orden de los vectores Q, redondeados a seis decimales: `AVANZAR`, `GIRAR_IZQUIERDA`, `GIRAR_DERECHA`, `AVANZAR_IZQUIERDA`, `AVANZAR_DERECHA`. Cada perfil corresponde a la primera diferencia de acción de todos los escenarios que lo citan. En los 25 escenarios el estado y las acciones permitidas coincidieron entre C y D, las tres banderas de avance fusionado eran verdaderas, el antibucle estaba inactivo y ambas acciones pasaron el validador temporal en el paso de divergencia. El final de D queda registrado por separado.

| Semilla y perfil | Paso | Estado C / D | Acciones permitidas en ambas, en orden | Q de C | Q de D | Acción de C | Acción de D |
|---:|---:|---:|---|---|---|---|---|
| 42 | 3 | 12 / 12 | `AVANZAR`, `AVANZAR_DERECHA`, `GIRAR_DERECHA` | `[2.005251, −0.267490, 6.782331, −0.128858, 12.189498]` | `[5.986528, −1.274412, −0.538589, −0.833410, 3.565386]` | `AVANZAR_DERECHA` | `AVANZAR` |
| 1042 | 5 | 30 / 30 | Las cinco, en el orden de Q | `[−0.771201, −1.306668, −1.290489, −1.208673, 0.024042]` | `[6.148286, −1.614712, −1.208237, 3.619165, −0.623905]` | `AVANZAR_DERECHA` | `AVANZAR` |
| 2042 | 2 | 26 / 26 | Las cinco, en el orden de Q | `[−0.885801, −0.866604, −0.926616, −0.904184, −0.876216]` | `[−0.742874, −0.734452, −0.780149, 3.357492, −0.719864]` | `GIRAR_IZQUIERDA` | `AVANZAR_IZQUIERDA` |

| Perfil | Semilla del escenario | Episodio | Lidar C / D al divergir (m) | Paso final D | Resultado D |
|---:|---:|---:|---:|---:|---|
| 42 | 100046 | 4 | 1,0333 | 15 | Contacto |
| 42 | 100049 | 7 | 1,0333 | 14 | Contacto |
| 1042 | 101043 | 1 | 0,7941 | 16 | Veto por borde |
| 1042 | 101044 | 2 | 0,7941 | 14 | Veto por borde |
| 1042 | 101045 | 3 | 0,7941 | 15 | Veto por borde |
| 1042 | 101046 | 4 | 0,7941 | 14 | Veto por borde |
| 1042 | 101047 | 5 | 0,7941 | 14 | Veto por borde |
| 1042 | 101048 | 6 | 0,7941 | 16 | Veto por borde |
| 1042 | 101049 | 7 | 0,7941 | 15 | Veto por borde |
| 1042 | 101051 | 9 | 0,7941 | 14 | Veto por borde |
| 1042 | 101052 | 10 | 0,7941 | 16 | Veto por borde |
| 1042 | 101053 | 11 | 0,7941 | 16 | Veto por borde |
| 1042 | 101055 | 13 | 0,7941 | 16 | Veto por borde |
| 1042 | 101057 | 15 | 0,7941 | 16 | Veto por borde |
| 1042 | 101058 | 16 | 0,7941 | 13 | Contacto |
| 1042 | 101060 | 18 | 0,7941 | 14 | Veto por borde |
| 1042 | 101061 | 19 | 0,7941 | 49 | Veto por borde |
| 1042 | 101062 | 20 | 0,7941 | 15 | Veto por borde |
| 2042 | 102045 | 3 | 1,1840 | 15 | Veto por borde |
| 2042 | 102046 | 4 | 1,1840 | 15 | Veto por borde |
| 2042 | 102047 | 5 | 1,1840 | 15 | Veto por borde |
| 2042 | 102053 | 11 | 1,1840 | 15 | Veto por borde |
| 2042 | 102058 | 16 | 1,1840 | 15 | Veto por borde |
| 2042 | 102060 | 18 | 1,1840 | 15 | Veto por borde |
| 2042 | 102061 | 19 | 1,1840 | 14 | Veto por borde |

Registros por semilla en `transiciones.csv`. [C 42](C/q_20261124_131617_da9a1ef4/transiciones.csv) · [D 42](D/q_20261124_132535_a87f1ecb/transiciones.csv) · [C 1042](C/q_20261124_133511_9efb8f25/transiciones.csv) · [D 1042](D/q_20261124_140316_6809930e/transiciones.csv) · [C 2042](C/q_20261124_141441_232a2f1a/transiciones.csv) · [D 2042](D/q_20261124_142425_a34ee0f3/transiciones.csv)
