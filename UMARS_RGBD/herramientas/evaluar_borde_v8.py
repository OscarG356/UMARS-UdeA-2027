"""Compara dos evaluaciones de la tabla Q congelada de D, semilla 1042."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from math import isclose
import os
from pathlib import Path
import subprocess
import sys

from .comparar_cd_v8 import ESCENARIO, WEBOTS
from .resumir_v8 import BASE, ROOT, leer_csv


REFERENCIA = BASE / "D" / "q_20261124_140316_6809930e"
TABLA = REFERENCIA / "q_table.npy"
SALIDA = BASE.parent / "prueba_borde_v8"
VARIANTES = ("original", "corregido")
METRICAS = (
    "llegadas", "vetos_borde", "contactos_rocas", "max_acciones",
    "sin_acciones_seguras", "acciones", "giros_puros", "giros_con_avance_seguro",
)


def cargar(variantes, hash_tabla, configuracion, historico, *, salida=SALIDA, rocas_inicio=None):
    corridas = {}
    claves_comunes = configuracion.keys() - {"entrenamiento", "lote"}
    escenarios = [tuple(f[k] for k in ESCENARIO) for f in historico]
    fase = "REGLAS" if configuracion["politica"] == "reglas" else "EVALUACION"
    for variante in variantes:
        for archivo in sorted((salida / variante).glob("*/configuracion.json"), reverse=True):
            cfg = json.loads(archivo.read_text(encoding="utf-8"))
            if (cfg.get("prueba_borde") != variante or cfg["entrenamiento"] != 0
                    or cfg.get("tabla_congelada_sha256") != hash_tabla
                    or any(cfg.get(k) != configuracion[k] for k in claves_comunes)):
                continue
            if not all((archivo.parent / nombre).is_file()
                       for nombre in ("episodios.csv", "transiciones.csv")):
                continue
            episodios = leer_csv(archivo.parent / "episodios.csv")
            if ([tuple(f[k] for k in ESCENARIO) for f in episodios] != escenarios
                    or any(f["fase"] != fase or float(f["epsilon"]) != 0 for f in episodios)):
                continue
            trazas = defaultdict(list)
            for fila in leer_csv(archivo.parent / "transiciones.csv"):
                trazas[fila["episodio"]].append(fila)
            if set(trazas) != {f["episodio"] for f in episodios}:
                continue
            if rocas_inicio and any(
                any(not trazas[e][0][k] or not isclose(
                    float(trazas[e][0][k]), float(valor), rel_tol=0.0, abs_tol=1e-12)
                    for k, valor in posiciones.items())
                for e, posiciones in rocas_inicio.items()
            ):
                continue
            if any(
                sum(bool(t["accion"]) for t in trazas[f["episodio"]]) != int(f["pasos"])
                or trazas[f["episodio"]][-1]["terminal"] != "1"
                or trazas[f["episodio"]][-1]["motivo_terminacion"] != f["resultado"]
                for f in episodios
            ):
                continue
            corridas[variante] = archivo.parent, episodios, trazas
            break
    return corridas


def variables_evaluacion(variante, cfg, tabla):
    variables = dict(
        WEBOTS_PYTHON_COMMAND=sys.executable,
        WEBOTS_DISABLE_SAVE_SCREEN_PERSPECTIVE_ON_CLOSE="1",
        UMARS_V8_PRUEBA_BORDE=variante,
        UMARS_V8_EXPERIMENTO=cfg["experimento"],
        UMARS_V8_POLITICA=cfg["politica"],
        UMARS_V8_PENALIZACION_GIRO=str(cfg["penalizacion_giro"]),
        UMARS_V8_SEMILLA=str(cfg["semilla"]),
        UMARS_EVALUACION=str(cfg["evaluacion"]),
        UMARS_MAX_ACCIONES=str(cfg["max_acciones"]),
        UMARS_META_X=str(cfg["meta"][0]),
        UMARS_META_Y=str(cfg["meta"][1]),
        UMARS_V8_ESCALA_VELOCIDAD=str(cfg["escala_velocidad"]),
        UMARS_V8_AMPLITUD_NORTE=str(cfg["amplitud_norte"]),
        UMARS_V8_AMPLITUD_SUR_X=str(cfg["amplitud_sur_x"]),
        UMARS_V8_AMPLITUD_SUR_Y=str(cfg["amplitud_sur_y"]),
        UMARS_V8_DESFASE_NORTE=str(cfg["desfase_norte"]),
        UMARS_V8_DESFASE_SUR=str(cfg["desfase_sur"]),
        UMARS_V8_PANEL_LIDAR="0",
        UMARS_V8_SALIR="1",
    )
    if tabla is not None:
        variables["UMARS_V8_TABLA_CONGELADA"] = str(tabla)
    return variables


def ejecutar(variante, args, cfg):
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith("UMARS_")}
    entorno.update(variables_evaluacion(variante, cfg, TABLA))
    comando = [str(args.webots), "--batch", "--mode=fast", "--stdout", "--stderr",
               str(ROOT / "worlds" / "marte_v8_dinamico.wbt")]
    if not args.visible:
        comando[1:1] = ["--minimize", "--no-rendering"]
    etiqueta = f"{cfg['experimento']} {cfg['semilla']} · {variante}"
    print(f"Webots · {etiqueta}", flush=True)
    if os.name == "nt" and not args.visible:
        proceso = subprocess.Popen(comando, env=entorno, cwd=ROOT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        proceso = subprocess.Popen(comando, env=entorno, cwd=ROOT)
    try:
        codigo = proceso.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(proceso.pid), "/T", "/F"],
                           capture_output=True, check=False)
        proceso.kill()
        proceso.wait()
        raise RuntimeError(f"Tiempo agotado en {etiqueta}.") from None
    if codigo:
        raise RuntimeError(f"Webots terminó {etiqueta} con código {codigo}.")


def metricas(episodio, transiciones):
    return dict(
        llegadas=int(episodio["exito"]),
        vetos_borde=sum(t["origen_colision"] == "VETO_TRAYECTORIA"
                        and t["motivo_terminacion"] == "FUERA_DEL_TERRENO" for t in transiciones),
        contactos_rocas=sum(t["origen_colision"] == "CONTACTO_GEOMETRICO"
                            and t["motivo_terminacion"].startswith("COLISION_")
                            for t in transiciones),
        max_acciones=int(episodio["resultado"] == "MAX_ACCIONES"),
        sin_acciones_seguras=int(episodio["resultado"] == "SIN_ACCIONES_SEGURAS_BORDE"),
        acciones=int(episodio["pasos"]),
        giros_puros=int(episodio["giros_puros"]),
        giros_con_avance_seguro=int(episodio["giros_con_avance_seguro"]),
    )


def escribir_csv(nombre, campos, filas):
    with (SALIDA / nombre).open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)


def comparar(corridas, historico):
    original, corregido = (corridas[v] for v in VARIANTES)
    episodios = []
    divergencias = []
    q = [c for c in original[2]["1"][0] if c.startswith("q_")]
    decision = ["estado", "acciones_antes_filtro_borde", "acciones_permitidas", "accion",
                *q, "lidar_min_m", "origen_colision", "motivo_terminacion"]
    for previo, a, b in zip(historico, original[1], corregido[1]):
        identificacion = {k: a[k] for k in ("episodio", "semilla_escenario")}
        t_a, t_b = original[2][a["episodio"]], corregido[2][b["episodio"]]
        salida = {
            **identificacion, "resultado_historico": previo["resultado"],
            "reproduce_historico": int(all(a[k] == previo[k] for k in (
                "resultado", "pasos", "giros_puros", "vetos_trayectoria", "contactos_geometricos"
            ))),
        }
        for variante, corrida, ep, tr in zip(VARIANTES, (original, corregido), (a, b), (t_a, t_b)):
            salida[f"{variante}_corrida"] = corrida[0].relative_to(SALIDA).as_posix()
            salida[f"{variante}_resultado"] = ep["resultado"]
            salida.update({f"{variante}_{k}": v for k, v in metricas(ep, tr).items()})
        episodios.append(salida)
        primera = next(((u, v) for u, v in zip(t_a, t_b) if u["accion"] != v["accion"]), None)
        if primera:
            registro = {**identificacion, "paso": primera[0]["paso"]}
            for variante, fila in zip(VARIANTES, primera):
                registro.update({f"{variante}_{k}": fila[k] for k in decision})
            divergencias.append(registro)
    escribir_csv("comparacion.csv", episodios[0].keys(), episodios)
    escribir_csv("divergencias.csv", ["episodio", "semilla_escenario", "paso",
                                    *(f"{v}_{k}" for v in VARIANTES for k in decision)], divergencias)
    print(f"Original reproduce los resultados históricos en "
          f"{sum(e['reproduce_historico'] for e in episodios)}/{len(episodios)} escenarios.")
    for variante in VARIANTES:
        totales = " · ".join(f"{k}={sum(e[f'{variante}_{k}'] for e in episodios)}"
                             for k in METRICAS)
        print(f"{variante}: {totales}")
    print(f"Primeras divergencias: {len(divergencias)}. CSV en {SALIDA}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--webots", type=Path, default=WEBOTS)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--solo-informe", action="store_true")
    parser.add_argument("--visible", action="store_true", help="Abrir Webots con la vista 3D")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("El tiempo máximo debe ser positivo.")
    try:
        cfg = json.loads((REFERENCIA / "configuracion.json").read_text(encoding="utf-8"))
        hash_tabla = hashlib.sha256(TABLA.read_bytes()).hexdigest()
        historico = [e for e in leer_csv(REFERENCIA / "episodios.csv") if e["fase"] == "EVALUACION"]
        if len(historico) != cfg["evaluacion"] or not historico:
            raise RuntimeError("La referencia D 1042 carece de una evaluación completa.")
        corridas = cargar(VARIANTES, hash_tabla, cfg, historico)
        for variante in VARIANTES:
            if variante not in corridas and not args.solo_informe:
                ejecutar(variante, args, cfg)
                corridas.update(cargar((variante,), hash_tabla, cfg, historico))
            if variante not in corridas:
                raise RuntimeError(f"Falta una evaluación completa y comparable de D {variante}.")
        if hashlib.sha256(TABLA.read_bytes()).hexdigest() != hash_tabla:
            raise RuntimeError("La tabla Q original cambió durante la prueba.")
        comparar(corridas, historico)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
