# UMARS v8 con filtro de borde durante el aprendizaje

## Recuperación comprobada del escenario 102061

Con la tabla histórica de D, semilla 2042, los pasos 16 a 18 fueron giros izquierda, derecha e izquierda. La alternancia activó el antibucle. En el paso 19, estado 13, el rover estaba en `(0,555887; 1,716076) m`, con rumbo de +30°. Los tres avances parecían seguros para los sensores y el antibucle ofreció únicamente esos tres. El borde superior admite el centro del chasis hasta y = 1,75 m. Los tres avances cruzaban ese límite y la lista de acciones quedó vacía. [Corrida de referencia](../validacion_borde_v8/D_2042/corregido/20261124_153811_d3e91e37/transiciones.csv)

La reconstrucción temporal confirmó que **ambos giros puros eran seguros en ese paso**. Girar a la izquierda dejaba al rover orientado a +60°, sin avances compatibles con el borde. Girar a la derecha lo orientaba a 0° y dejaba dos avances compatibles, `AVANZAR` y `AVANZAR_DERECHA`. En modo de rescate, cuando el antibucle está activo y la intersección de candidatos queda vacía, se habilitan solo los giros puros que respetan el borde y abren una trayectoria de avance dentro del terreno. Tras elegir el giro, el validador temporal comprueba las rocas antes de mover el rover. Las posiciones de las rocas no intervienen en la selección del giro.

| Configuración | Resultado | Acciones | Giros puros | Vetos por borde | Contactos con rocas |
|---|---|---:|---:|---:|---:|
| Referencia congelada | Sin acciones seguras | 18 | 4 | 0 | 0 |
| Rescate aislado | Meta | 28 | 5 | 0 | 0 |

Webots reprodujo las primeras 18 transiciones. El giro a la derecha se ejecutó en el paso 19, seguido de `AVANZAR_DERECHA`, y el rover llegó en el paso 28. El resultado comprueba la recuperación de este escenario. [CSV del rescate](rescate_102061.csv) · [Transiciones en Webots](rescate/D_2042/20261124_155504_c0bc24f5/transiciones.csv)

## Comparación del entrenamiento con filtro

El nuevo lote usa la intersección con el borde antes de elegir y también para el máximo Q del estado siguiente. Si esa intersección queda vacía, la actualización anterior usa su recompensa original sin un valor futuro de una acción inexistente. El rescate permanece como una prueba aislada. Así, tanto las tablas nuevas como las históricas se evalúan con el mismo filtro de borde y el mismo antibucle.

El diseño contempla 120 episodios de entrenamiento por combinación de política y semilla, con tablas inicializadas en cero, tres semillas de entrenamiento (42, 1042 y 2042), α = 0,10, γ = 0,95 y el programa de exploración v8. C y D comparten escenarios de entrenamiento. La diferencia de recompensa es la penalización de giro de 0,2 en D. Se conservaron los 144 estados, las cinco acciones y los sensores.

Las cinco políticas de comparación son C nueva, D nueva, C histórica, D histórica y reglas. En cada bloque se usarán los mismos 20 escenarios de evaluación para las cinco, con identificadores nuevos y separados de los de entrenamiento y de la validación anterior. La evaluación Q usa ε = 0 y las tablas en memoria en solo lectura. Los promedios de acciones y giros se limitan a las llegadas compartidas de cada par. Las llegadas exclusivas se registran por separado.

## Resultados medidos de la evaluación

| Política | Semilla | Llegadas | Vetos de borde | Contactos | Sin acciones | Límite | Acciones ejecutadas | Giros ejecutados |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C_nuevo | 42 | 16/20 | 0 | 2 | 2 | 0 | 475 | 68 |
| D_nuevo | 42 | 20/20 | 0 | 0 | 0 | 0 | 488 | 26 |
| C_nuevo | 1042 | 20/20 | 0 | 0 | 0 | 0 | 503 | 38 |
| D_nuevo | 1042 | 19/20 | 0 | 1 | 0 | 0 | 685 | 181 |
| C_nuevo | 2042 | 17/20 | 0 | 3 | 0 | 0 | 466 | 42 |
| D_nuevo | 2042 | 20/20 | 0 | 0 | 0 | 0 | 481 | 17 |
| C_histórico | 42 | 17/20 | 0 | 3 | 0 | 0 | 464 | 55 |
| D_histórico | 42 | 16/20 | 0 | 4 | 0 | 0 | 608 | 202 |
| reglas | 42 | 16/20 | 0 | 3 | 0 | 0 | 468 | 68 |
| C_histórico | 1042 | 14/20 | 0 | 6 | 0 | 0 | 457 | 77 |
| D_histórico | 1042 | 19/20 | 0 | 1 | 0 | 0 | 634 | 133 |
| reglas | 1042 | 16/20 | 0 | 4 | 0 | 0 | 474 | 76 |
| C_histórico | 2042 | 11/20 | 0 | 8 | 0 | 1 | 805 | 397 |
| D_histórico | 2042 | 17/20 | 0 | 3 | 0 | 0 | 476 | 48 |
| reglas | 2042 | 12/20 | 0 | 8 | 0 | 0 | 423 | 74 |

### Eficiencia en llegadas compartidas

| Políticas | Llegadas compartidas | Acciones medias | Giros medios | Llegadas exclusivas |
|---|---:|---:|---:|---:|
| C_histórico y C_nuevo | 40 | 31.175 / 25.65 | 7.8 / 2.625 | 2 / 13 |
| C_histórico y D_histórico | 40 | 31.325 / 32.225 | 7.925 / 7.8 | 2 / 12 |
| C_histórico y D_nuevo | 41 | 31.0976 / 28.0732 | 7.7561 / 4.0976 | 1 / 18 |
| C_histórico y reglas | 37 | 29.5135 / 26.2432 | 6.4324 / 3.8649 | 5 / 7 |
| C_nuevo y D_histórico | 50 | 25.36 / 31.18 | 2.34 / 6.92 | 3 / 2 |
| C_nuevo y D_nuevo | 52 | 25.3462 / 27.7115 | 2.3654 / 3.6731 | 1 / 7 |
| C_nuevo y reglas | 40 | 25.725 / 26.225 | 2.625 / 3.825 | 13 / 4 |
| D_histórico y D_nuevo | 51 | 31 / 27.7451 | 6.8235 / 3.7255 | 1 / 8 |
| D_histórico y reglas | 40 | 32.25 / 26.225 | 7.775 / 3.85 | 12 / 4 |
| D_nuevo y reglas | 43 | 28.4186 / 26.1628 | 4.3721 / 3.7442 | 16 / 1 |

Los resultados describen las tres semillas y los escenarios de evaluación ejecutados.

[Consolidado](consolidado.csv) · [Episodios](episodios.csv) · [Eficiencia pareada](eficiencia_pareada.csv) · [Llegadas exclusivas](llegadas_exclusivas.csv)
