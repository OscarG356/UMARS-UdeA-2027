"""Ejecuta y compara C y D con las mismas semillas y escenarios en Webots."""

import argparse
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import uuid

from .resumir_v8 import BASE, ROOT, resumir


WEBOTS = Path("C:/Program Files/Webots/msys64/mingw64/bin/webots.exe")
ESCENARIO = (
    "semilla_escenario", "omega_norte", "omega_sur", "fase_norte", "fase_sur",
    "inicio_x", "inicio_y", "meta_x", "meta_y",
)
METRICAS = (
    ("Llegadas", "exito", sum),
    ("Colisiones registradas", "colision", sum),
    ("Vetos de trayectoria", "vetos_trayectoria", sum),
    ("Contactos geométricos", "contactos_geometricos", sum),
    ("Acciones por llegada compartida", "pasos", statistics.mean),
    ("Giros puros por llegada compartida", "giros_puros", statistics.mean),
    ("Giros evitables por llegada compartida", "giros_con_avance_seguro", statistics.mean),
)


def evaluaciones(args):
    corridas, _ = resumir()
    penalizaciones = {"C": 0, "D": 0.2}
    for carpeta, cfg, fase, filas in corridas:
        experimento = cfg["experimento"]
        presupuesto = cfg["entrenamiento"], cfg["evaluacion"], cfg["max_acciones"]
        if (fase == "EVALUACION" and experimento in penalizaciones
                and cfg["politica"] == "q" and cfg["semilla"] in args.semillas
                and presupuesto == (args.entrenamiento, args.evaluacion, args.max_acciones)
                and cfg["penalizacion_giro"] == penalizaciones[experimento]):
            yield carpeta, cfg, filas


def evaluar_lote(args, lote):
    return {(cfg["semilla"], cfg["experimento"]) for _, cfg, _ in evaluaciones(args)
            if cfg.get("lote") == lote}


def ejecutar(args, lote):
    completas = evaluar_lote(args, lote)
    print(f"Lote {lote}", flush=True)
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith("UMARS_")}
    entorno.update(
        WEBOTS_PYTHON_COMMAND=sys.executable,
        WEBOTS_DISABLE_SAVE_SCREEN_PERSPECTIVE_ON_CLOSE="1",
        UMARS_ENTRENAMIENTO=str(args.entrenamiento),
        UMARS_EVALUACION=str(args.evaluacion),
        UMARS_MAX_ACCIONES=str(args.max_acciones),
        UMARS_V8_POLITICA="q",
        UMARS_V8_PANEL_LIDAR="0",
        UMARS_V8_SALIR="1",
        UMARS_V8_LOTE=lote,
    )
    comando = [
        str(args.webots), "--minimize", "--no-rendering", "--batch", "--mode=fast",
        "--stdout", "--stderr", str(ROOT / "worlds" / "marte_v8_dinamico.wbt"),
    ]
    for semilla in args.semillas:
        for experimento, penalizacion in (("C", "0"), ("D", "0.2")):
            if (semilla, experimento) in completas:
                print(f"Ya completa · {experimento} · semilla {semilla}", flush=True)
                continue
            print(f"Webots · {experimento} · semilla {semilla}", flush=True)
            entorno.update(
                UMARS_V8_SEMILLA=str(semilla), UMARS_V8_EXPERIMENTO=experimento,
                UMARS_V8_PENALIZACION_GIRO=penalizacion,
            )
            with tempfile.TemporaryFile() as registro:
                try:
                    proceso = subprocess.run(
                        comando, env=entorno, cwd=ROOT, stdout=registro,
                        stderr=subprocess.STDOUT, timeout=args.timeout,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                except subprocess.TimeoutExpired:
                    proceso = None
                completa = (semilla, experimento) in evaluar_lote(args, lote)
                if proceso is None or proceso.returncode or not completa:
                    registro.seek(0)
                    detalle = registro.read().decode("utf-8", errors="replace").splitlines()
                    motivo = "tiempo agotado" if proceso is None else f"código {proceso.returncode}"
                    raise RuntimeError(
                        f"Corrida incompleta {experimento}, semilla {semilla} ({motivo}).\n"
                        + "\n".join(detalle[-20:])
                    )


def comparar(args, lote):
    candidatas = {}
    for carpeta, cfg, filas in evaluaciones(args):
        if lote is None or cfg.get("lote") == lote:
            candidatas.setdefault(cfg.get("lote"), {})[cfg["semilla"], cfg["experimento"]] = (
                carpeta, cfg, filas
            )

    requeridas = {(semilla, variante) for semilla in args.semillas for variante in ("C", "D")}
    completas = [grupo for grupo in candidatas.values() if requeridas <= grupo.keys()]
    if not completas:
        raise ValueError("Falta un mismo lote con corridas completas de C y D para las semillas solicitadas.")
    seleccion = max(completas, key=lambda grupo: max(ruta.name for ruta, _, _ in grupo.values()))

    pares = []
    detalle = []
    escenarios_vistos = set()
    for semilla in args.semillas:
        ruta_c, cfg_c, filas_c = seleccion[semilla, "C"]
        ruta_d, cfg_d, filas_d = seleccion[semilla, "D"]
        ignoradas = {"experimento", "penalizacion_giro", "lote"}
        if ({k: v for k, v in cfg_c.items() if k not in ignoradas}
                != {k: v for k, v in cfg_d.items() if k not in ignoradas}):
            raise ValueError(f"Las configuraciones de C y D difieren para la semilla {semilla}.")
        por_escenario_c = {tuple(f[k] for k in ESCENARIO): f for f in filas_c}
        por_escenario_d = {tuple(f[k] for k in ESCENARIO): f for f in filas_d}
        if (len(por_escenario_c) != len(filas_c)
                or len(por_escenario_d) != len(filas_d)
                or por_escenario_c.keys() != por_escenario_d.keys()):
            raise ValueError(f"C y D no evaluaron los mismos escenarios únicos para {semilla}.")
        if escenarios_vistos.intersection(por_escenario_c):
            raise ValueError(f"La semilla {semilla} repite escenarios de otra corrida.")
        escenarios_vistos.update(por_escenario_c)
        coincidencias = [(c, por_escenario_d[clave]) for clave, c in por_escenario_c.items()]
        pares.extend(coincidencias)
        detalle.append((semilla, ruta_c, ruta_d, coincidencias))

    lineas = [
        "# Comparación pareada de C y D", "",
        f"Cada variante entrenó durante {args.entrenamiento} episodios por semilla. "
        f"La evaluación usó {args.evaluacion} escenarios por semilla, con un máximo "
        f"de {args.max_acciones} acciones por episodio. C usó penalización 0 y D, 0,2.",
        "", f"**Escenarios pareados:** {len(pares)}. **Semillas de entrenamiento:** {len(detalle)}.",
        "",
        "| Métrica | C | D | Diferencia D − C |",
        "|---|---:|---:|---:|",
    ]
    llegadas = [(c, d) for c, d in pares if c["exito"] == d["exito"] == "1"]
    for nombre, clave, agregar in METRICAS:
        muestras = llegadas if agregar is statistics.mean else pares
        if not muestras:
            lineas.append(f"| {nombre} | — | — | — |")
            continue
        c, d = (agregar(int(p[i][clave]) for p in muestras) for i in (0, 1))
        lineas.append(f"| {nombre} | {c:g} | {d:g} | {d-c:+g} |"
                      if agregar is sum else f"| {nombre} | {c:.2f} | {d:.2f} | {d-c:+.2f} |")
    solo_c = sum(c["colision"] == "1" and d["colision"] == "0" for c, d in pares)
    solo_d = sum(c["colision"] == "0" and d["colision"] == "1" for c, d in pares)
    lineas.extend([
        "", f"Los promedios de eficiencia se calculan sobre las llegadas compartidas ({len(llegadas)}).",
        f"Hubo colisión solo en C en {solo_c} escenarios y solo en D en {solo_d}.",
        "Los episodios de una misma semilla comparten la tabla Q entrenada. "
        "Las diferencias son descriptivas.", "", "## Resultados por semilla", "",
        "| Semilla | Llegadas C / D | Colisiones C / D | Llegadas compartidas | Corridas |",
        "|---|---:|---:|---:|---|",
    ])
    for semilla, ruta_c, ruta_d, coincidencias in detalle:
        exitos_c = sum(int(c["exito"]) for c, _ in coincidencias)
        exitos_d = sum(int(d["exito"]) for _, d in coincidencias)
        colisiones_c = sum(int(c["colision"]) for c, _ in coincidencias)
        colisiones_d = sum(int(d["colision"]) for _, d in coincidencias)
        compartidas = sum(c["exito"] == d["exito"] == "1" for c, d in coincidencias)
        ruta_c = ruta_c.relative_to(BASE).as_posix()
        ruta_d = ruta_d.relative_to(BASE).as_posix()
        lineas.append(
            f"| {semilla} | {exitos_c} / {exitos_d} | {colisiones_c} / {colisiones_d} | "
            f"{compartidas} | [C]({ruta_c}/episodios.csv) · [D]({ruta_d}/episodios.csv) |"
        )
    salida = BASE / "comparacion_cd.md"
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(salida)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejecutar", action="store_true")
    parser.add_argument("--lote", type=uuid.UUID, help="Identificador de un lote existente")
    parser.add_argument("--webots", type=Path, default=WEBOTS)
    parser.add_argument("--semillas", type=int, nargs="+", default=[42, 1042, 2042])
    parser.add_argument("--entrenamiento", type=int, default=120)
    parser.add_argument("--evaluacion", type=int, default=20)
    parser.add_argument("--max-acciones", type=int, default=120)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if min(args.semillas) < 0 or len(set(args.semillas)) != len(args.semillas):
        parser.error("Las semillas deben ser únicas y no negativas.")
    if min(args.entrenamiento, args.evaluacion, args.max_acciones, args.timeout) < 1:
        parser.error("El presupuesto y el tiempo de espera deben ser positivos.")
    lote = args.lote.hex if args.lote else (uuid.uuid4().hex if args.ejecutar else None)
    try:
        if args.ejecutar:
            ejecutar(args, lote)
        comparar(args, lote)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
