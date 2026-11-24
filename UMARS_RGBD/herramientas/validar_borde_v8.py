"""Prepara una corrida manual de Webots o consolida la validación de borde completa."""

import argparse
import csv
from dataclasses import dataclass
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
from statistics import mean

from .comparar_cd_v8 import ESCENARIO, WEBOTS
from .evaluar_borde_v8 import (
    METRICAS, SALIDA as PILOTO, VARIANTES, cargar, metricas, variables_evaluacion,
)
from .resumir_v8 import BASE, ROOT, leer_csv, resumir
from controllers.umars_v8.control_v8 import GIROS_PUROS


LOTE = "ec6e12209a6e45d8bdc02d1b61e5d81e"
SALIDA = BASE.parent / "validacion_borde_v8"
SEMILLAS = (42, 1042, 2042)
MEDIDAS = (*METRICAS, "acciones_ejecutadas", "giros_ejecutados")


@dataclass(frozen=True)
class Caso:
    politica: str
    semilla: int
    configuracion: dict
    historico: list
    tabla: Path | None
    hash_tabla: str | None
    referencia: Path
    rocas_inicio: dict

    @property
    def carpeta(self):
        return SALIDA / f"{self.politica}_{self.semilla}"


def preparar():
    casos = {}
    for ruta, cfg, fase, filas in resumir()[0]:
        if cfg.get("lote") != LOTE or fase != "EVALUACION":
            continue
        variante, semilla = cfg["experimento"], cfg["semilla"]
        tabla = ruta / "q_table.npy"
        claves_rocas = ("roca_norte_x", "roca_norte_y", "roca_sur_x", "roca_sur_y")
        rocas_inicio = {
            t["episodio"]: {k: t[k] for k in claves_rocas}
            for t in leer_csv(ruta / "transiciones.csv")
            if t["fase"] == "EVALUACION" and t["paso"] == "1"
        }
        if set(rocas_inicio) != {f["episodio"] for f in filas}:
            raise ValueError(f"Faltan las posiciones iniciales de las rocas en {ruta}.")
        casos[variante, semilla] = Caso(
            variante, semilla, cfg, filas, tabla,
            hashlib.sha256(tabla.read_bytes()).hexdigest(), ruta, rocas_inicio,
        )
    for semilla in SEMILLAS:
        c, d = (casos[v, semilla] for v in ("C", "D"))
        if (len(c.historico) != 20 or [tuple(f[k] for k in ESCENARIO) for f in c.historico]
                != [tuple(f[k] for k in ESCENARIO) for f in d.historico]):
            raise ValueError(f"Escenarios históricos incompatibles en la semilla {semilla}.")
        casos["reglas", semilla] = Caso(
            "reglas", semilla, {**c.configuracion, "politica": "reglas"},
            c.historico, None, None, c.referencia, c.rocas_inicio,
        )
    return casos


def obtener(caso, modo):
    raices = [caso.carpeta]
    if (caso.politica, caso.semilla) == ("D", 1042):
        raices.append(PILOTO)
    for raiz in raices:
        corrida = cargar((modo,), caso.hash_tabla, caso.configuracion, caso.historico,
                         salida=raiz, rocas_inicio=caso.rocas_inicio)
        if modo in corrida:
            return corrida[modo]
    return None


def comandos_manuales(caso, modo, webots):
    variables = variables_evaluacion(modo, caso.configuracion, caso.tabla)
    variables.update(
        UMARS_V8_VALIDACION_BORDE="1", UMARS_V8_PANEL_LIDAR="1", UMARS_V8_SALIR="0",
    )

    def literal(valor):
        return "'" + str(valor).replace("'", "''") + "'"

    print(f"# {caso.politica} | semilla {caso.semilla} | {modo}")
    for nombre, valor in variables.items():
        if nombre in ("WEBOTS_PYTHON_COMMAND", "UMARS_V8_TABLA_CONGELADA"):
            ruta = literal(os.path.relpath(valor, ROOT))
            print(f"$env:{nombre} = (Resolve-Path -LiteralPath {ruta}).Path")
        else:
            print(f"$env:{nombre} = {literal(valor)}")
    mundo = literal("worlds/marte_v8_dinamico.wbt")
    print(f"& {literal(webots)} --mode=pause (Resolve-Path -LiteralPath {mundo}).Path")


def escribir(nombre, filas):
    with (SALIDA / nombre).open("w", newline="", encoding="utf-8") as archivo:
        w = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def movimientos_ejecutados(episodio, transiciones):
    """Cuenta las acciones que llegaron a cambiar la pose, incluso parcialmente."""
    pose = float(episodio["inicio_x"]), float(episodio["inicio_y"]), 0.0
    acciones = giros = 0
    for fila in transiciones:
        nueva = tuple(float(fila[k]) for k in ("x", "y", "rumbo_rad"))
        if fila["accion"] and nueva != pose:
            acciones += 1
            giros += fila["accion"] in GIROS_PUROS
        pose = nueva
    return acciones, giros


def comparar_pares(filas, etiqueta, izquierda, derecha, detalle):
    comunes = [(a, b) for a, b in filas if a["llegadas"] == b["llegadas"] == 1]
    return {
        **detalle, "comparacion": etiqueta, "izquierda": izquierda, "derecha": derecha,
        "escenarios": len(filas), "llegadas_izquierda": sum(a["llegadas"] for a, _ in filas),
        "llegadas_derecha": sum(b["llegadas"] for _, b in filas),
        "llegadas_compartidas": len(comunes),
        "recuperados": sum(a["llegadas"] == 0 and b["llegadas"] == 1 for a, b in filas),
        "perdidos": sum(a["llegadas"] == 1 and b["llegadas"] == 0 for a, b in filas),
        **{f"{m}_{lado}": round(mean(par[i][m] for par in comunes), 4) if comunes else ""
           for m in ("acciones_ejecutadas", "giros_ejecutados", "giros_con_avance_seguro")
           for i, lado in enumerate(("izquierda", "derecha"))},
    }


def informar(casos, corridas):
    registros = {}
    resumen = []
    episodios = []
    pares = []
    recuperados = []
    def alinear(clave_a, clave_b):
        a, b = (registros[k] for k in (clave_a, clave_b))
        return [(a[s], b[s]) for s in a]

    for (politica, semilla), caso in sorted(casos.items()):
        for modo in VARIANTES:
            clave = politica, semilla, modo
            ruta, filas, trazas = corridas[clave]
            resultados = {}
            historico_ok = ""
            if modo == "original" and caso.tabla is not None:
                episodios_previos = caso.historico
                trans_previas = [t for t in leer_csv(caso.referencia / "transiciones.csv")
                                 if t["fase"] == "EVALUACION"]
                trans_actuales = [t for fila in filas for t in trazas[fila["episodio"]]]
                historico_ok = int(filas == episodios_previos
                                   and len(trans_previas) == len(trans_actuales)
                                   and all(all(b[k] == v for k, v in a.items())
                                           for a, b in zip(trans_previas, trans_actuales)))
            ruta_rel = Path(os.path.relpath(ruta, SALIDA)).as_posix()
            for fila in filas:
                transiciones = trazas[fila["episodio"]]
                ejecutadas, giros = movimientos_ejecutados(fila, transiciones)
                medida = {
                    "politica": politica, "semilla": semilla, "modo": modo,
                    "semilla_escenario": int(fila["semilla_escenario"]),
                    "episodio": int(fila["episodio"]), "resultado": fila["resultado"],
                    **metricas(fila, transiciones),
                    "acciones_ejecutadas": ejecutadas, "giros_ejecutados": giros,
                }
                episodios.append(medida)
                resultados[medida["semilla_escenario"]] = medida
            registros[clave] = resultados
            resumen.append({
                "politica": politica, "semilla": semilla, "modo": modo,
                "escenarios": len(filas), **{m: sum(x[m] for x in resultados.values()) for m in MEDIDAS},
                "reproduccion_exacta_original": historico_ok, "ruta": ruta_rel,
            })

        datos = alinear((politica, semilla, "original"), (politica, semilla, "corregido"))
        pares.append(comparar_pares(datos, "efecto_filtro", "original", "corregido",
                                    {"politica": politica, "semilla": semilla, "modo": "pareado"}))
        for a, b in datos:
            if a["llegadas"] == 0 and b["llegadas"] == 1:
                recuperados.append({
                    "politica": politica, "semilla": semilla,
                    "semilla_escenario": a["semilla_escenario"], "resultado_original": a["resultado"],
                    "acciones_ejecutadas_corregido": b["acciones_ejecutadas"],
                    "giros_ejecutados_corregido": b["giros_ejecutados"],
                })

    for politica in ("C", "D", "reglas"):
        datos = [par for semilla in SEMILLAS
                 for par in alinear((politica, semilla, "original"), (politica, semilla, "corregido"))]
        pares.append(comparar_pares(datos, "efecto_filtro", "original", "corregido",
                                    {"politica": politica, "semilla": "total", "modo": "pareado"}))
    for modo in VARIANTES:
        for izq, der in combinations(("C", "D", "reglas"), 2):
            datos_totales = []
            for semilla in SEMILLAS:
                datos = alinear((izq, semilla, modo), (der, semilla, modo))
                datos_totales.extend(datos)
                pares.append(comparar_pares(datos, "entre_politicas", izq, der,
                                            {"politica": "todas", "semilla": semilla, "modo": modo}))
            pares.append(comparar_pares(datos_totales, "entre_politicas", izq, der,
                                        {"politica": "todas", "semilla": "total", "modo": modo}))

    escribir("consolidado.csv", resumen)
    escribir("episodios.csv", episodios)
    escribir("eficiencia_pareada.csv", pares)
    if recuperados:
        escribir("recuperados.csv", recuperados)
    for f in resumen:
        print(f"{f['politica']} {f['semilla']} {f['modo']}: "
              f"{f['llegadas']}/{f['escenarios']} llegadas, {f['vetos_borde']} vetos, "
              f"{f['contactos_rocas']} contactos, {f['max_acciones']} límites")
    print(f"Resultados consolidados en {SALIDA}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--webots", type=Path, default=WEBOTS)
    parser.add_argument("--solo-informe", action="store_true")
    args = parser.parse_args()
    try:
        casos = preparar()
        corridas = {}
        pendientes = []
        for clave, caso in casos.items():
            for modo in VARIANTES:
                corrida = obtener(caso, modo)
                if corrida is None:
                    pendientes.append((*clave, modo))
                else:
                    corridas[(*clave, modo)] = corrida
        if pendientes:
            if args.solo_informe:
                raise RuntimeError(f"Faltan las corridas {pendientes}.")
            politica, semilla, modo = pendientes[0]
            print(f"# {len(corridas)} de {len(casos) * len(VARIANTES)} corridas completas.")
            comandos_manuales(casos[politica, semilla], modo, args.webots)
            return
        for caso in casos.values():
            if caso.tabla and hashlib.sha256(caso.tabla.read_bytes()).hexdigest() != caso.hash_tabla:
                raise RuntimeError(f"Cambió la tabla original {caso.tabla}.")
        informar(casos, corridas)
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
