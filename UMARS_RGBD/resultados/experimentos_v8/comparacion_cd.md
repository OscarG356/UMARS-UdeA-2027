# Comparación pareada de C y D

Cada variante entrenó durante 120 episodios por semilla. La evaluación usó 20 escenarios por semilla, con un máximo de 120 acciones por episodio. C usó penalización 0 y D, 0,2.

**Escenarios pareados:** 60. **Semillas de entrenamiento:** 3.

| Métrica | C | D | Diferencia D − C |
|---|---:|---:|---:|
| Llegadas | 46 | 28 | -18 |
| Colisiones registradas | 14 | 32 | +18 |
| Vetos de trayectoria | 0 | 27 | +27 |
| Contactos geométricos | 14 | 5 | -9 |
| Acciones por llegada compartida | 33.76 | 35.48 | +1.71 |
| Giros puros por llegada compartida | 9.38 | 11.62 | +2.24 |
| Giros evitables por llegada compartida | 4.62 | 5.81 | +1.19 |

Los promedios de eficiencia se calculan sobre las llegadas compartidas (21).
Hubo colisión solo en C en 7 escenarios y solo en D en 25.
Los episodios de una misma semilla comparten la tabla Q entrenada. Las diferencias son descriptivas.

## Resultados por semilla

| Semilla | Llegadas C / D | Colisiones C / D | Llegadas compartidas | Corridas |
|---|---:|---:|---:|---|
| 42 | 16 / 16 | 4 / 4 | 14 | [C](C/q_20261124_131617_da9a1ef4/episodios.csv) · [D](D/q_20261124_132535_a87f1ecb/episodios.csv) |
| 1042 | 17 / 1 | 3 / 19 | 1 | [C](C/q_20261124_133511_9efb8f25/episodios.csv) · [D](D/q_20261124_140316_6809930e/episodios.csv) |
| 2042 | 13 / 11 | 7 / 9 | 6 | [C](C/q_20261124_141441_232a2f1a/episodios.csv) · [D](D/q_20261124_142425_a34ee0f3/episodios.csv) |
