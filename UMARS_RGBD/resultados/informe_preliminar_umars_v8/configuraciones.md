# Configuraciones y trazabilidad experimental

| Parámetro | Valor |
|---|---|
| Mundo y simulador | `worlds/marte_v8_dinamico.wbt`, Webots R2025a. |
| Estado y acción | 144 estados y cinco acciones, sin aproximación neuronal. |
| Horizonte y tiempo | 120 acciones. Paso Webots 32 ms, tres subpasos por acción. |
| Q-learning | α = 0,10, γ = 0,95, inicialización en cero en cada entrenamiento. |
| ε de entrenamiento | Inicial 1,0, decrece por 0,95 por episodio, mínimo 0,05. |
| Evaluación | ε = 0, tablas en solo lectura para Q. La política por reglas no entrena. |
| Coste adicional de giro | C y reglas 0. D 0,2 por giro marcado como evitable. |
| Semillas base | 42, 1042, 2042. |
| Entrenamiento por tabla | 120 episodios. |
| Evaluación por grupo | 20 episodios por semilla, incluidos una vez por política. |
| Bases nuevas de evaluación | 200042, 201042 y 202042. Los identificadores son base + 100 000 + episodio. |
| Pose y meta | Inicio (−1,5; 0) m, rumbo 0 rad. Meta (2,2; 0,75) m y tolerancia 0,35 m. |
| Seguridad | Radio geométrico 0,25 m; percepción usa 0,27 m; las referencias nuevas aplican filtro previo de borde y validador temporal. |
| Rescate | Escenario 102061, episodio 19 de la evaluación de D 2042 original. Prueba aislada, desactivada en entrenamiento y comparación. |

## Cohortes

- **Histórico v8 C/D.** Seis tablas del lote `ec6e12209a6e45d8bdc02d1b61e5d81e`, aprendidas sin filtro previo. Las evaluaciones originales de ese lote usan otros identificadores que el estudio nuevo. [Fuentes originales](../experimentos_v8/comparacion_cd.md)
- **Validación previa de borde.** Dieciocho corridas y 360 episodios, originales frente a corregidos. Sirve para comparar efecto del filtro en tablas congeladas. La corrida repetida con geometría guardada incorrecta se mantuvo en su carpeta y se excluyó de la validación por diferencia de posiciones de rocas. [Consolidado original](../validacion_borde_v8/consolidado.csv)
- **Estudio actual.** Seis entrenamientos nuevos con borde tanto al decidir como al tomar el máximo Q futuro. Nueve referencias planificadas con las seis tablas históricas y reglas por bloque. En los cinco grupos, los escenarios de evaluación de cada bloque comparten semillas, fases, velocidades, inicio y meta.
- **Rescate del episodio 102061.** Misma tabla histórica D 2042, inicio y secuencia hasta el fallo. La única variante experimental permite giros que respetan el borde y abren un avance cuando el antibucle dejó la lista vacía. [Datos](datos/rescate_102061.csv)

Los valores efectivos de cada corrida, la carpeta de evidencia y los SHA-256 de las tablas están en el CSV de [configuraciones](datos/configuraciones.csv). La disponibilidad por semilla figura en [pendientes.csv](datos/pendientes.csv).
