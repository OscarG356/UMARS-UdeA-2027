# Reproducción y revisión de UMARS v8

## Preparación

Ejecutar desde la raíz del proyecto, con Webots R2025a y el entorno Python del proyecto. Los sensores se inicializan dentro del Supervisor y las dependencias del generador se enumeran en `requirements.txt`. El archivo principal de simulación es `worlds/marte_v8_dinamico.wbt`.

## Corridas de referencia, una a la vez

1. Cerrar la instancia anterior después de que muestre `RESUMEN EVALUACION` o `RESUMEN REGLAS`. Si Webots consulta por guardar el mundo, descartar los cambios de pose de la sesión.
2. Consultar la corrida pendiente en PowerShell. El comando imprime un bloque y no abre Webots por sí mismo.

   ```powershell
   .\.venv\Scripts\python.exe -m herramientas.estudiar_aprendizaje_borde_v8
   ```

3. Usar el bloque completo para preparar el entorno de la corrida. La última línea abre Webots en pausa con `--mode=pause`. Pulsar **Ctrl+2** en Webots para iniciar. Si la apertura se realiza desde Codex, abrir una sola instancia en pausa y arrancarla en la interfaz.
4. Esperar el resumen de los 20 episodios y cerrar la instancia. Las carpetas de los resultados se guardan bajo `resultados/aprendizaje_borde_v8/comparar/<grupo>/<id>/`. La carpeta histórica se usa como origen de la tabla en lectura. El modo comparar nunca ejecuta entrenamiento ni activa el rescate.
5. Repetir desde el paso 2. El lector verifica la identidad de configuración y escenario, los motivos terminales y la coincidencia de Q con la tabla de referencia, cuando corresponde. No contabiliza una corrida incompleta.

Para la evaluación de C y D, los escenarios nuevos se emparejan por identificador, frecuencias, fases, inicio y meta. El validador devuelve los escenarios pendientes antes de intentar presentar una comparación completa. Las corridas existentes de entrenamiento están disponibles como evidencia y no se vuelven a lanzar para consolidar.

## Regenerar figuras y datos

```powershell
.\.venv\Scripts\python.exe -m herramientas.generar_informe_umars_v8
```

El generador solo lee los datos existentes. Exporta CSV y PNG a esta carpeta y actualiza la sección numérica del Markdown. Se puede ejecutar con corridas pendientes, que quedan identificadas en el documento y en su CSV. Las figuras se guardan a 200 dpi. Los casos de navegación de referencia se seleccionan a partir de acciones y motivo final registrados.

## Revisar las comprobaciones

- Comparar las fuentes y los SHA-256 en [configuraciones.csv](datos/configuraciones.csv). Las tablas que se evalúan están cargadas como matrices de solo lectura. Se contrastan las filas Q de evaluación contra las tablas.
- Contar por separado filas de `ENTRENAMIENTO`, `EVALUACION` y `REGLAS` en [episodios.csv](datos/episodios.csv).
- Verificar que el denominador de las medias pareadas sea `llegadas_compartidas` en [eficiencia_pareada.csv](datos/eficiencia_pareada.csv). Los casos exclusivos se conservan con ambos desenlaces.
- Para una prueba local del código sin iniciar simulación, usar:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest herramientas.test_qlearning herramientas.test_v8 herramientas.test_controlador_v8 -q
  ```

[Controlador](../../controllers/umars_v8/umars_v8.py) · [Selección y verificación de corridas](../../herramientas/estudiar_aprendizaje_borde_v8.py) · [Generador de figuras y tablas](../../herramientas/generar_informe_umars_v8.py)
