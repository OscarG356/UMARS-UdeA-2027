# Resultados experimentales v8

Cada fila del CSV representa una corrida y una fase completas. La recompensa base permite comparar desempeño; la recompensa de aprendizaje incluye la penalización por giro cuando está activada. Corridas repetidas con idéntica semilla y escenario se mantienen separadas: no son nuevas muestras independientes.

| Exp. | Política | Fase | Éxitos | Colisiones | Acciones medias | Giros con avance medios | Retorno base medio |
|---|---|---|---:|---:|---:|---:|---:|
| A | q | EVALUACION | 2/2 | 0/2 | 107.00 | 31.00 | -0.13 |
| B | q | ENTRENAMIENTO | 1/2 | 0/2 | 83.50 | 25.50 | -28.40 |
| B | q | EVALUACION | 0/2 | 2/2 | 31.00 | 2.00 | -75.84 |
| B | q | ENTRENAMIENTO | 40/60 | 4/60 | 73.98 | 18.03 | -4.85 |
| B | q | EVALUACION | 10/10 | 0/10 | 73.00 | 14.00 | 33.87 |
| B | q | ENTRENAMIENTO | 1/2 | 0/2 | 83.50 | 25.50 | -28.40 |
| B | q | EVALUACION | 0/2 | 2/2 | 31.00 | 2.00 | -75.84 |
| B | reglas | REGLAS | 2/2 | 0/2 | 25.00 | 2.00 | 82.21 |
| C | q | ENTRENAMIENTO | 2/2 | 0/2 | 52.50 | 19.50 | 54.64 |
| C | q | EVALUACION | 1/2 | 1/2 | 72.50 | 14.00 | -41.99 |
| C | reglas | REGLAS | 1/2 | 1/2 | 19.50 | 2.50 | 10.49 |
| D | q | ENTRENAMIENTO | 2/2 | 0/2 | 52.50 | 19.50 | 54.64 |
| D | q | EVALUACION | 1/2 | 1/2 | 72.50 | 14.00 | -41.99 |
| D | reglas | REGLAS | 1/2 | 1/2 | 19.50 | 2.50 | 10.49 |

## Referencia histórica A (v7)

La evaluación v7 de la meta norte registró 10/10 llegadas, pero son diez repeticiones del mismo escenario y no diez muestras independientes. La prueba de generalización sobre ocho combinaciones de inicio y meta registró 8/8 llegadas para Q y para reglas; Q requirió 464 acciones y reglas 245. Estas cifras son históricas y no se integran en el cálculo estadístico de v8. Una nueva corrida A carga la tabla v7 y evalúa sin actualizarla.

Las evaluaciones dinámicas usan velocidades distintas de entrenamiento y fases reproducibles. Una comparación causal B frente a C o D requiere tener completas las corridas correspondientes y revisar las mismas semillas.
