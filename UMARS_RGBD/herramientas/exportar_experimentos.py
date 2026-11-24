"""Reune los episodios historicos sin confundir formatos ni corridas repetidas.

Genera un resumen por carpeta/fase y otro CSV con una fila por episodio.
Los valores ausentes en los archivos originales permanecen vacios.
"""

from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import csv
import json
import re

import numpy as np


RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados"
RESUMEN = RESULTADOS / "resumen_experimentos_umars.csv"
DETALLE = RESULTADOS / "episodios_experimentos_umars.csv"
AVANCES = {"AVANZAR", "AVANZAR_IZQUIERDA", "AVANZAR_DERECHA"}

DETALLE_CAMPOS = (
    "experimento", "version_nombre", "politica", "fase", "episodio",
    "meta_x", "meta_y", "meta_fuente", "inicio", "x_inicio", "y_inicio",
    "rumbo_inicio_deg", "epsilon", "max_pasos_config", "pasos", "retorno", "resultado",
    "exito", "colision_geometrica_o_borde", "distancia_final_m",
    "transiciones_registradas", "transiciones_coinciden_pasos",
    "avanzar", "girar_izquierda", "girar_derecha",
    "avanzar_izquierda", "avanzar_derecha", "giros_total",
    "giros_con_avance_permitido", "giros_sin_avance_permitido",
    "pasos_modo_antibucle", "lidar_en_registro", "huella_trayectoria_sha256",
    "tabla_q_ruta", "tabla_q_filas", "tabla_q_acciones",
    "tabla_q_valores_no_cero", "tabla_q_sha256",
    "archivo_episodios", "archivo_transiciones", "fecha_archivo_local",
    "estado_registro",
)

RESUMEN_CAMPOS = (
    "experimento", "version_nombre", "politica", "fase", "meta_x",
    "meta_y", "meta_fuente", "max_pasos_config", "episodios", "exitos", "colisiones_o_borde",
    "max_acciones", "otros_resultados", "tasa_exito_pct", "retorno_medio",
    "pasos_medios", "distancia_final_media_m", "giros_totales",
    "giros_por_episodio", "pasos_modo_antibucle_total",
    "trayectorias_distintas_registradas", "tabla_q_ruta", "tabla_q_filas",
    "tabla_q_acciones", "tabla_q_valores_no_cero", "tabla_q_sha256",
    "lidar_en_registro", "archivo_episodios", "archivo_transiciones",
    "fecha_archivo_local", "estado_registro",
)


def leer_csv(ruta):
    if not ruta.exists():
        return [], []
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        return list(lector), lector.fieldnames or []


def version_nombre(nombre):
    if nombre.startswith("meta_x+"):
        return "v7_generalizacion"
    match = re.search(r"_v([0-9]+)", nombre)
    if match:
        return "v" + match.group(1)
    if nombre == "diagnostico_ql_meta_lejana":
        return "v1_meta_lejana"
    if nombre == "diagnostico_ql":
        return "meta_cercana_24x3"
    return "sin_version_verificada"


def meta_de(row, config, nombre):
    if row.get("meta_x") and row.get("meta_y"):
        return row["meta_x"], row["meta_y"], "csv"
    if config and config.get("meta"):
        return config["meta"][0], config["meta"][1], "configuracion.json"
    if "meta_lejana" in nombre or "_lejana_" in nombre:
        return 2.2, 0.75, "nombre_carpeta_y_diagnostico"
    if nombre == "diagnostico_ql":
        return -0.5, 0.75, "diagnostico_historico"
    return "", "", ""


def fase_de(row, ruta):
    if row.get("fase"):
        return row["fase"].upper()
    if ruta.parent == RESULTADOS and row.get("epsilon"):
        return "ENTRENAMIENTO"
    return "EVALUACION"


def politica_de(row, config, nombre):
    if row.get("fase", "").upper() == "REGLAS" or "reglas" in nombre:
        return "reglas"
    if config and config.get("politica"):
        return config["politica"]
    if "ql" in nombre or nombre == "resultados":
        return "q"
    return "no_verificada"


def ruta_relativa(ruta):
    if not ruta:
        return ""
    try:
        return ruta.resolve().relative_to(RAIZ.resolve()).as_posix()
    except ValueError:
        return str(ruta)


def tabla_de(carpeta, config):
    if config and config.get("tabla_q"):
        ruta = Path(config["tabla_q"])
    else:
        rutas = list(carpeta.glob("q_table*.npy"))
        ruta = rutas[0] if len(rutas) == 1 else None
    if ruta is None or not ruta.exists():
        return {campo: "" for campo in (
            "tabla_q_ruta", "tabla_q_filas", "tabla_q_acciones",
            "tabla_q_valores_no_cero", "tabla_q_sha256")}
    tabla = np.load(ruta, allow_pickle=False)
    forma = tabla.shape if len(tabla.shape) == 2 else ("", "")
    return {
        "tabla_q_ruta": ruta_relativa(ruta),
        "tabla_q_filas": forma[0],
        "tabla_q_acciones": forma[1],
        "tabla_q_valores_no_cero": int(np.count_nonzero(tabla)),
        "tabla_q_sha256": sha256(ruta.read_bytes()).hexdigest(),
    }


def limite_de(nombre, config):
    if config and config.get("max_acciones") is not None:
        return config["max_acciones"]
    if "max120" in nombre:
        return 120
    if nombre.startswith("diagnostico_") and re.search(r"_v[234](?:$|_)", nombre):
        return 60
    if nombre == "diagnostico_ql_meta_lejana":
        return 60
    return ""


def promedio(valores):
    presentes = [float(v) for v in valores if v not in (None, "")]
    return round(sum(presentes) / len(presentes), 5) if presentes else ""


def registros_de(archivo):
    episodios, _ = leer_csv(archivo)
    transiciones_ruta = archivo.with_name(archivo.name.replace("episodios", "transiciones", 1))
    transiciones, columnas_tr = leer_csv(transiciones_ruta)
    config_ruta = archivo.parent / "configuracion.json"
    config = json.loads(config_ruta.read_text(encoding="utf-8")) if config_ruta.exists() else None
    nombre = archivo.parent.name
    tabla = tabla_de(archivo.parent, config)
    fecha = datetime.fromtimestamp(archivo.stat().st_mtime).isoformat(timespec="seconds")
    grupos = defaultdict(list)
    for t in transiciones:
        clave = (t.get("fase", "").upper(), t.get("episodio", ""))
        grupos[clave].append(t)

    base = {
        "experimento": archivo.parent.relative_to(RESULTADOS).as_posix()
        if archivo.parent != RESULTADOS else "resultados_raiz",
        "version_nombre": version_nombre(nombre),
        "archivo_episodios": ruta_relativa(archivo),
        "archivo_transiciones": ruta_relativa(transiciones_ruta) if transiciones_ruta.exists() else "",
        "fecha_archivo_local": fecha,
        "lidar_en_registro": int("lidar_min_m" in columnas_tr),
        "max_pasos_config": limite_de(nombre, config),
        **tabla,
    }
    if not episodios:
        x, y, origen = meta_de({}, config, nombre)
        return [{
            **base, "meta_x": x, "meta_y": y, "meta_fuente": origen,
            "politica": politica_de({}, config, nombre),
            "transiciones_registradas": len(transiciones),
            "estado_registro": "sin_episodios_con_transiciones" if transiciones else "sin_episodios",
        }]

    salida = []
    for e in episodios:
        fase = fase_de(e, archivo)
        pasos = int(e["pasos"])
        clave = (fase if "fase" in columnas_tr else "", e["episodio"])
        trs = grupos[clave]
        conteo = Counter(t.get("accion", "") for t in trs)
        giros = conteo["GIRAR_IZQUIERDA"] + conteo["GIRAR_DERECHA"]
        if "acciones_permitidas" in columnas_tr:
            con_avance = sum(
                t.get("accion", "").startswith("GIRAR_")
                and bool(AVANCES.intersection(t.get("acciones_permitidas", "").split(";")))
                for t in trs
            )
            sin_avance = giros - con_avance
        else:
            con_avance = sin_avance = ""
        filtro = sum(bool(t.get("modo_antibucle")) for t in trs) if "modo_antibucle" in columnas_tr else ""
        huella = ""
        if trs and {"x_despues", "y_despues", "rumbo_deg"}.issubset(columnas_tr):
            secuencia = [(t.get("accion"), t.get("x_despues"), t.get("y_despues"),
                         t.get("rumbo_deg")) for t in trs]
            huella = sha256(json.dumps(secuencia).encode("utf-8")).hexdigest()
        x, y, origen = meta_de(e, config, nombre)
        resultado = e["resultado"]
        salida.append({
            **base,
            "politica": politica_de(e, config, nombre), "fase": fase,
            "episodio": e["episodio"], "meta_x": x, "meta_y": y,
            "meta_fuente": origen, "inicio": e.get("inicio", ""),
            "x_inicio": e.get("x_inicio", ""), "y_inicio": e.get("y_inicio", ""),
            "rumbo_inicio_deg": e.get("rumbo_inicio_deg", ""),
            "epsilon": e.get("epsilon", ""), "pasos": pasos,
            "retorno": e.get("retorno", ""), "resultado": resultado,
            "exito": int(resultado == "META"),
            "colision_geometrica_o_borde": int(resultado.startswith("COLISION_")
                                                 or resultado == "FUERA_DEL_TERRENO"),
            "distancia_final_m": e.get("distancia_final", e.get("distancia_meta", "")),
            "transiciones_registradas": len(trs),
            "transiciones_coinciden_pasos": int(len(trs) == pasos),
            "avanzar": conteo["AVANZAR"] if trs else "",
            "girar_izquierda": conteo["GIRAR_IZQUIERDA"] if trs else "",
            "girar_derecha": conteo["GIRAR_DERECHA"] if trs else "",
            "avanzar_izquierda": conteo["AVANZAR_IZQUIERDA"] if trs else "",
            "avanzar_derecha": conteo["AVANZAR_DERECHA"] if trs else "",
            "giros_total": giros if trs else "",
            "giros_con_avance_permitido": con_avance,
            "giros_sin_avance_permitido": sin_avance,
            "pasos_modo_antibucle": filtro,
            "huella_trayectoria_sha256": huella,
            "estado_registro": "completo" if len(trs) == pasos else "transiciones_incompletas",
        })
    return salida


def resumir(registros):
    grupos = defaultdict(list)
    for r in registros:
        grupos[(r["experimento"], r.get("fase", ""))].append(r)
    salida = []
    for _, filas in sorted(grupos.items()):
        r = filas[0]
        eps = [f for f in filas if f.get("episodio") not in (None, "")]
        resultados = Counter(f["resultado"] for f in eps)
        exitos = resultados["META"]
        colisiones = sum(int(f["colision_geometrica_o_borde"]) for f in eps)
        huellas = {f["huella_trayectoria_sha256"] for f in eps
                   if f["huella_trayectoria_sha256"]}
        salida.append({
            **{k: r.get(k, "") for k in RESUMEN_CAMPOS},
            "episodios": len(eps), "exitos": exitos,
            "colisiones_o_borde": colisiones,
            "max_acciones": resultados["MAX_ACCIONES"],
            "otros_resultados": len(eps) - exitos - colisiones - resultados["MAX_ACCIONES"],
            "tasa_exito_pct": round(100 * exitos / len(eps), 3) if eps else "",
            "retorno_medio": promedio(f.get("retorno") for f in eps),
            "pasos_medios": promedio(f.get("pasos") for f in eps),
            "distancia_final_media_m": promedio(f.get("distancia_final_m") for f in eps),
            "giros_totales": sum(int(f["giros_total"]) for f in eps
                                  if f.get("giros_total") not in (None, "")),
            "giros_por_episodio": promedio(f.get("giros_total") for f in eps),
            "pasos_modo_antibucle_total": sum(int(f["pasos_modo_antibucle"]) for f in eps
                                               if f.get("pasos_modo_antibucle") not in (None, ""))
            if any(f.get("pasos_modo_antibucle") not in (None, "") for f in eps) else "",
            "trayectorias_distintas_registradas": len(huellas) if huellas else "",
            "estado_registro": "completo" if eps and all(
                f["estado_registro"] == "completo" for f in eps)
            else r["estado_registro"] if not eps else "transiciones_incompletas",
        })
    return salida


def guardar(ruta, campos, filas):
    with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def main():
    fuentes = sorted(p for p in RESULTADOS.rglob("episodios*.csv")
                     if p.resolve() != DETALLE.resolve())
    registros = [r for archivo in fuentes for r in registros_de(archivo)]
    resumen = resumir(registros)
    guardar(DETALLE, DETALLE_CAMPOS, registros)
    guardar(RESUMEN, RESUMEN_CAMPOS, resumen)
    print(f"Fuentes: {len(fuentes)} | filas de detalle: {len(registros)} "
          f"| filas de resumen: {len(resumen)}")
    print(RESUMEN)
    print(DETALLE)


if __name__ == "__main__":
    main()
