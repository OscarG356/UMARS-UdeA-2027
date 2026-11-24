"""Consolida corridas v8 completas sin mezclar recompensa de entrenamiento y desempeño."""

from pathlib import Path
import csv
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "resultados" / "experimentos_v8"


def leer_csv(ruta):
    with ruta.open(newline="", encoding="utf-8") as archivo:
        return list(csv.DictReader(archivo))


def resumir():
    corridas = []
    incompletas = []
    for configuracion in sorted(BASE.glob("*/**/configuracion.json")):
        carpeta = configuracion.parent
        datos = json.loads(configuracion.read_text(encoding="utf-8"))
        archivo = carpeta / "episodios.csv"
        if not archivo.exists():
            incompletas.append(str(carpeta.relative_to(BASE)))
            continue
        episodios = leer_csv(archivo)
        fases = (["REGLAS"] if datos["politica"] == "reglas" else
                 ["EVALUACION"] if datos["experimento"] == "A" else
                 ["ENTRENAMIENTO", "EVALUACION"])
        completos = all(
            sum(e["fase"] == fase for e in episodios)
            == datos["entrenamiento" if fase == "ENTRENAMIENTO" else "evaluacion"]
            for fase in fases
        )
        if not completos:
            incompletas.append(str(carpeta.relative_to(BASE)))
            continue
        for fase in fases:
            filas = [e for e in episodios if e["fase"] == fase]
            corridas.append((carpeta, datos, fase, filas))
    return corridas, incompletas


def media(filas, clave):
    return statistics.mean(float(f[clave]) for f in filas)


def escribir():
    BASE.mkdir(parents=True, exist_ok=True)
    corridas, incompletas = resumir()
    if not corridas:
        print(f"Aun no hay corridas v8 completas en {BASE}")
        return
    campos = [
        "experimento", "politica", "fase", "corrida", "semilla",
        "max_acciones", "penalizacion_giro", "episodios",
        "exitos", "colisiones", "vetos_trayectoria",
        "contactos_geometricos", "limites", "acciones_promedio",
        "giros_puros_promedio", "giros_con_avance_promedio",
        "giros_forzados_promedio", "distancia_m_promedio",
        "retorno_base_promedio", "retorno_aprendizaje_promedio",
        "tiempo_s_promedio", "intervenciones_antibucle_promedio",
    ]
    resumen = []
    for carpeta, datos, fase, filas in corridas:
        resumen.append({
            "experimento": datos["experimento"],
            "politica": datos["politica"], "fase": fase,
            "corrida": str(carpeta.relative_to(BASE)),
            "semilla": datos["semilla"],
            "max_acciones": datos["max_acciones"],
            "penalizacion_giro": datos["penalizacion_giro"],
            "episodios": len(filas),
            "exitos": sum(int(f["exito"]) for f in filas),
            "colisiones": sum(int(f["colision"]) for f in filas),
            "vetos_trayectoria": sum(int(f["vetos_trayectoria"]) for f in filas),
            "contactos_geometricos": sum(
                int(f["contactos_geometricos"]) for f in filas
            ),
            "limites": sum(f["resultado"] == "MAX_ACCIONES" for f in filas),
            "acciones_promedio": media(filas, "pasos"),
            "giros_puros_promedio": media(filas, "giros_puros"),
            "giros_con_avance_promedio": media(filas, "giros_con_avance_seguro"),
            "giros_forzados_promedio": media(filas, "giros_forzados"),
            "distancia_m_promedio": media(filas, "distancia_recorrida_m"),
            "retorno_base_promedio": media(filas, "retorno_base"),
            "retorno_aprendizaje_promedio": media(filas, "retorno_entrenamiento"),
            "tiempo_s_promedio": media(filas, "tiempo_simulado_s"),
            "intervenciones_antibucle_promedio": media(
                filas, "intervenciones_antibucle"
            ),
        })
    with (BASE / "resumen_corridas.csv").open(
        "w", newline="", encoding="utf-8"
    ) as archivo:
        writer = csv.DictWriter(archivo, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resumen)

    lineas = [
        "# Resultados experimentales v8", "",
        "Cada fila del CSV representa una corrida y una fase completas. La recompensa "
        "base permite comparar desempeño; la recompensa de aprendizaje incluye "
        "la penalización por giro cuando está activada. Corridas repetidas con "
        "idéntica semilla y escenario se mantienen separadas: no son nuevas "
        "muestras independientes.", "",
        "| Exp. | Política | Fase | Éxitos | Colisiones | Acciones medias | Giros con avance medios | Retorno base medio |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for fila in resumen:
        lineas.append(
            f"| {fila['experimento']} | {fila['politica']} | {fila['fase']} | "
            f"{fila['exitos']}/{fila['episodios']} | "
            f"{fila['colisiones']}/{fila['episodios']} | "
            f"{fila['acciones_promedio']:.2f} | "
            f"{fila['giros_con_avance_promedio']:.2f} | "
            f"{fila['retorno_base_promedio']:.2f} |"
        )
    lineas.extend([
        "", "## Referencia histórica A (v7)", "",
        "La evaluación v7 de la meta norte registró 10/10 llegadas, pero "
        "son diez repeticiones del mismo escenario y no diez muestras independientes. "
        "La prueba de generalización sobre ocho combinaciones de inicio y meta "
        "registró 8/8 llegadas para Q y para reglas; Q requirió 464 acciones y "
        "reglas 245. Estas cifras son históricas y no se integran en el "
        "cálculo estadístico de v8. Una nueva corrida A carga la tabla v7 "
        "y evalúa sin actualizarla.", "",
        "Las evaluaciones dinámicas usan velocidades distintas de entrenamiento "
        "y fases reproducibles. Una comparación causal B frente a C o D requiere "
        "tener completas las corridas correspondientes y revisar las mismas semillas.",
    ])
    if incompletas:
        lineas.extend(["", "## Corridas incompletas", ""])
        lineas.extend(f"- `{nombre}`" for nombre in incompletas)
    (BASE / "RESUMEN.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    evaluacion = [r for r in resumen if r["fase"] in ("EVALUACION", "REGLAS")]
    if evaluacion:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        seleccion = {}
        for fila in evaluacion:
            clave = (fila["experimento"], fila["politica"])
            if clave not in seleccion or fila["corrida"] > seleccion[clave]["corrida"]:
                seleccion[clave] = fila
        etiquetas = []
        valores = {"exitos": [], "colisiones": [], "acciones_promedio": [],
                   "giros_con_avance_promedio": []}
        for grupo, fila in sorted(seleccion.items()):
            etiquetas.append("/".join(grupo))
            for clave in valores:
                valores[clave].append(
                    float(fila[clave]) / float(fila["episodios"])
                    if clave in ("exitos", "colisiones") else float(fila[clave])
                )
        fig, axs = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
        for ax, (clave, lista) in zip(axs.flat, valores.items()):
            ax.bar(etiquetas, lista)
            ax.set_title(clave.replace("_", " "))
            ax.tick_params(axis="x", rotation=30)
            if clave in ("exitos", "colisiones"):
                ax.set_ylim(0, 1)
        fig.suptitle("Última corrida completa por grupo; A usa tabla Q histórica")
        fig.savefig(BASE / "comparacion_evaluacion.png", dpi=150)
        plt.close(fig)
    print(f"Corridas completas: {len(corridas)}; incompletas: {len(incompletas)}")
    print(f"Resumen: {BASE / 'RESUMEN.md'}")


if __name__ == "__main__":
    escribir()
