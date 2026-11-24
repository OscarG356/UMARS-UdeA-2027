# Diccionario de datos UMARS v8

Cada CSV usa UTF-8, coma como separador y punto decimal. Los campos vacíos representan valores ausentes, no un cero observado. Se conservaron las etiquetas de fase y motivo terminal de los archivos fuente.

## Archivos incluidos

| Archivo | Unidad de observación y alcance |
|---|---|
| `datos/episodios.csv` | Una fila por episodio histórico v8, del nuevo estudio o del rescate aislado. Se identifica cada origen. |
| `datos/transiciones.csv` | Una fila por decisión registrada, incluida la decisión terminal sin movimiento. Incluye la fila Q previa y las coordenadas de rover y rocas. |
| `datos/configuraciones.csv` | Una fila por corrida exportada. Incluye parámetros y SHA-256 de la tabla disponible. |
| `datos/consolidado_evaluacion.csv` | Una fila por política y semilla ejecutada del estudio en escenarios nuevos. |
| `datos/eficiencia_pareada.csv` | Una fila por par de políticas y semilla comparable o total. Las medias solo usan llegadas compartidas. |
| `datos/llegadas_exclusivas.csv` | Un escenario y par por fila cuando llega una sola de las políticas. |
| `datos/estados_visitados.csv` | Número de decisiones observadas en cada estado por corrida y fase, incluido el estado de un bloqueo. |
| `datos/cobertura_sensores.csv` | Decisiones, lecturas válidas, mínimo, mediana y máximo por corrida, fase y medida sensorial. |
| `datos/cambios_q_entrenamiento.csv` | Una fila reconstruida por actualización, con valores Q y objetivo. Se usa el siguiente CSV de transición para el máximo futuro. |
| `datos/casos_representativos.csv` | Identificadores de los casos mostrados en la figura de trayectorias y distancias. |
| `datos/pendientes.csv` | Corridas planificadas todavía sin CSV completo validado. |
| `datos/validacion_borde_previa.csv` | Validación separada de tablas congeladas y reglas en 360 episodios. |
| `datos/validacion_borde_previa_episodios.csv`, `datos/validacion_borde_previa_recuperados.csv` | Registros por escenario de esa validación y lista de sus 26 episodios recuperados. |
| `datos/experimentos_v8_iniciales.csv` | Resumen original v8, incluye etapas con tamaños de muestra distintos. |
| `datos/experimentos_pre_v8.csv` | Resumen histórico con la fase y fuente originales. |
| `datos/rescate_102061.csv` | Referencia y rescate aislado con la misma tabla D. |

## Identidad y episodios

| Campo o familia | Interpretación |
|---|---|
| `etapa`, `fuente` | Cohorte exportada y carpeta original relativa a la raíz del proyecto. |
| `politica_informe`, `experimento`, `politica` | Etiqueta del informe, configuración A–D y familia registrada como `q` o `reglas`. La etiqueta C que aparece en una corrida por reglas corresponde a coste de giro cero. |
| `semilla_corrida`, `semilla_escenario`, `episodio` | Semilla de la política o bloque, semilla de las rocas y número del episodio dentro de su fase. La clave de una transición es fuente, fase, episodio y paso. |
| `fase`, `epsilon` | `ENTRENAMIENTO`, `EVALUACION` o `REGLAS`. ε es una probabilidad sin unidad. Solo Q se actualiza en entrenamiento. |
| `omega_norte`, `omega_sur`, `fase_norte`, `fase_sur` | Velocidades angulares en rad/s y fases iniciales en rad. |
| `inicio_*`, `meta_*`, `distancia_final_meta_m` | Coordenadas del plano y distancia euclidiana final en metros. |
| `pasos`, `acciones`, `acciones_ejecutadas` | Decisiones con una acción intentada y el subconjunto que cambió posición o rumbo. Una acción vetada consume un paso. El evento sin acción no lo consume. |
| `giros_puros`, `giros_ejecutados`, `giros_con_avance_seguro`, `giros_forzados` | Conteos de giros puros. El conteo ejecutado exige cambio de pose. La clasificación con avance seguro y forzado usa la percepción fusionada antes de otros filtros. |
| `distancia_recorrida_m`, `tiempo_simulado_s` | Suma de desplazamientos XY entre poses registradas y tiempo simulado tras el calentamiento, en m y s. |
| `retorno_base`, `retorno_entrenamiento`, `penalizacion_total` | Sumas en puntos, sin descuento. La segunda incluye el coste adicional de giro. |
| `resultado`, `exito`, `colision` | Etiqueta final y banderas binarias del controlador. La bandera de colisión agrupa motivos geométricos y salida del terreno. |
| `contactos_rocas`, `vetos_borde`, `sin_acciones_seguras`, `max_acciones` | Métricas separadas derivadas de los motivos y su origen. Contacto requiere `CONTACTO_GEOMETRICO` y un motivo `COLISION_*`. Veto por borde requiere `VETO_TRAYECTORIA` y `FUERA_DEL_TERRENO`. |
| `observaciones_con_mascara_sensor`, `avances_descartados_por_percepcion` | Decisiones con tres banderas sensoriales válidas y número de valores 0 en ellas. El denominador de candidatos es tres por decisión válida. |
| `observaciones_con_mascara_borde`, `candidatos_descartados_por_borde` | Número de decisiones con lista previa disponible y tamaño acumulado de la diferencia respecto a la lista final. En el rescate se pueden añadir giros. La métrica cuenta únicamente los candidatos retirados. |
| `estados_visitados`, `intervenciones_antibucle` | Número de estados distintos en el episodio y observaciones con el antibucle en modo escape. |

## Transiciones y sensores

| Campo o familia | Interpretación |
|---|---|
| `paso`, `estado`, `siguiente_estado`, `q_*` | Número de decisión, índice tabular, siguiente índice cuando se registra y cinco Q inmediatamente antes de elegir. Los valores Q de reglas no son una política aprendida. |
| `acciones_antes_filtro_borde`, `acciones_permitidas`, `accion` | Máscara previa, candidatos finales y acción seleccionada. Las listas usan punto y coma. |
| `terminal`, `terminal_q`, `acciones_permitidas_siguiente` | Evento terminal registrado y, en entrenamiento nuevo, bandera y máscara usadas al formar el objetivo Q. Un bloqueo se registra como una fila sin acción, y el paso anterior omite el término futuro de Q. |
| `recompensa_base`, `penalizacion_giro`, `recompensa_aprendizaje` | Puntos de esa transición, antes y después de incorporar el coste. |
| `x`, `y`, `rumbo_rad`, `distancia_meta_m` | Pose y distancia **posteriores** a la acción, en m, rad y m. En un evento sin acción corresponden a la pose observada. |
| `roca_norte_*`, `roca_sur_*` | Coordenadas de centros después de la acción, en m. Pueden faltar en un evento sin acción. |
| `lidar_min_m` | Menor norma horizontal finita y positiva de la nube **antes** de elegir, en m. |
| `rgbd_*_m` | Mínimo axial procesado de la franja o percentil 20 por sector antes de elegir, en m. Solo está presente desde la instrumentación adicional de las referencias. |
| `avances_seguros_rgbd`, `avances_seguros_lidar`, `avance_seguro_*` | Conjuntos admisibles estimados por cada sensor, cuando se capturaron, y tres banderas fusionadas para avance recto, curvo izquierdo y curvo derecho. |
| `motivo_terminacion`, `origen_colision`, `antibucle_activo` | Etiqueta de final, mecanismo de contacto/veto y estado de la memoria de escape antes de la selección. |

## Comparación pareada y actualización Q

En `eficiencia_pareada.csv`, `escenarios` cuenta escenarios comparables, `llegadas_compartidas` cuenta éxitos de ambos, `perdidos` indica llegada exclusiva de la izquierda y `recuperados` indica llegada exclusiva de la derecha. Las etiquetas de orden no implican que una política sea una corrección de la otra. Los campos `acciones_ejecutadas_*` y `giros_ejecutados_*` de ese archivo son medias, con la unidad de movimientos por llegada compartida.

Los campos `q_previo`, `max_q_siguiente`, `objetivo`, `delta_q` y `q_actualizado` documentan una actualización individual. El máximo queda vacío en terminal. El historial usa la lista registrada en el paso siguiente si carece de una columna explícita; las corridas nuevas registran la máscara futura empleada. La reconstrucción es un cálculo a partir de valores del controlador y no una captura independiente posterior a cada actualización.
