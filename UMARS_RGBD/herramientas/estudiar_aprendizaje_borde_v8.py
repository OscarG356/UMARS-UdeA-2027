"""Prepara una corrida manual del estudio de aprendizaje con filtro de borde."""

from argparse import ArgumentParser
from collections import defaultdict
import csv
from itertools import combinations
import json
import os
from pathlib import Path

import numpy as np
from controllers.umars_qlearning.agente_q import ACCIONES, AgenteQ

from .comparar_cd_v8 import ESCENARIO, WEBOTS
from .evaluar_borde_v8 import metricas, variables_evaluacion
from .resumir_v8 import BASE, ROOT, leer_csv
from .validar_borde_v8 import (
    MEDIDAS, SEMILLAS, comparar_pares, movimientos_ejecutados, obtener, preparar,
)

SALIDA = BASE.parent / "aprendizaje_borde_v8"
ENTRENAMIENTO = 120
EVALUACION = 20


def casos_estudio():
    referencias = preparar()
    referencia = referencias["D", 2042]
    yield "rescate", "D", 2042, referencia, 2042, 19, 1
    for modo in ("entrenar", "comparar"):
        politicas = ("C", "D") if modo == "entrenar" else ("C", "D", "reglas")
        for semilla in SEMILLAS:
            for politica in politicas:
                yield modo, politica, semilla, referencias[politica, semilla], 200000 + semilla, 1, EVALUACION


def carpeta(caso):
    modo, politica, semilla, *_ = caso
    return SALIDA / modo / f"{politica}_{semilla}"


def cargar_caso(caso):
    modo, _, semilla, ref, semilla_eval, inicio, n_eval = caso
    n_train = ENTRENAMIENTO if modo == "entrenar" else 0
    cfg_esperada = {
        **ref.configuracion, "entrenamiento": n_train, "evaluacion": n_eval,
        "estudio_borde": modo, "prueba_borde": "corregido",
        "semilla_evaluacion": semilla_eval, "primer_episodio_evaluacion": inicio,
    }
    cfg_esperada.pop("lote", None)
    fase_eval = "REGLAS" if ref.tabla is None else "EVALUACION"
    for archivo in sorted(carpeta(caso).glob("*/configuracion.json"), reverse=True):
        ruta = archivo.parent
        cfg = json.loads(archivo.read_text(encoding="utf-8"))
        hash_esperado = ref.hash_tabla if not n_train else None
        if (any(cfg.get(k) != v for k, v in cfg_esperada.items())
                or cfg.get("tabla_congelada_sha256") != hash_esperado
                or not all((ruta / x).is_file() for x in ("episodios.csv", "transiciones.csv"))
                or (n_train and not (ruta / "q_table.npy").is_file())):
            continue
        episodios = leer_csv(ruta / "episodios.csv")
        agrupadas = defaultdict(list)
        for fila in leer_csv(ruta / "transiciones.csv"):
            agrupadas[fila["fase"], fila["episodio"]].append(fila)
        plan = [("ENTRENAMIENTO", i, semilla + i) for i in range(1, n_train + 1)]
        plan.extend((fase_eval, i, semilla_eval + 100000 + i) for i in range(inicio, inicio + n_eval))
        if [(f["fase"], int(f["episodio"]), int(f["semilla_escenario"]))
                for f in episodios] != plan:
            continue
        if set(agrupadas) != {(f["fase"], f["episodio"]) for f in episodios}:
            continue
        evaluados = [f for f in episodios if f["fase"] == fase_eval]
        if any(float(f["epsilon"]) != 0 for f in evaluados):
            continue
        if any(
            sum(bool(t["accion"]) for t in agrupadas[f["fase"], f["episodio"]]) != int(f["pasos"])
            or agrupadas[f["fase"], f["episodio"]][-1]["terminal"] != "1"
            or agrupadas[f["fase"], f["episodio"]][-1]["motivo_terminacion"] != f["resultado"]
            for f in episodios
        ):
            continue
        if ref.tabla:
            tabla = np.load(ruta / "q_table.npy" if n_train else ref.tabla, allow_pickle=False)
            for f in evaluados:
                for t in agrupadas[f["fase"], f["episodio"]]:
                    q = [float(v) for k, v in t.items() if k.startswith("q_")]
                    if not np.array_equal(tabla[int(t["estado"])], q):
                        raise ValueError(f"Los valores Q cambiaron en evaluación en {ruta.name}.")
            if n_train:
                verificar_entrenamiento(cfg, episodios[:n_train], agrupadas, tabla)
        return ruta, episodios, agrupadas
    return None


def verificar_entrenamiento(cfg, episodios, trazas, tabla):
    agente = AgenteQ(cfg["alpha"], cfg["gamma"], cfg["semilla"])
    for ep in episodios:
        pasos = trazas[ep["fase"], ep["episodio"]]
        for i, fila in enumerate(pasos):
            if not fila["accion"]:
                continue
            estado = int(fila["estado"])
            disponibles = tuple(ACCIONES.index(a) for a in fila["acciones_permitidas"].split(";"))
            q = [float(v) for k, v in fila.items() if k.startswith("q_")]
            indice = agente.elegir_accion(estado, float(ep["epsilon"]), disponibles)
            if not np.array_equal(agente.q[estado], q) or ACCIONES[indice] != fila["accion"]:
                raise ValueError(f"No se reprodujo la decisión de entrenamiento en {ep['episodio']}:{fila['paso']}.")
            siguientes = fila["acciones_permitidas_siguiente"]
            terminal = fila["terminal_q"] == "1"
            if fila["terminal"] == "0" and siguientes != pasos[i + 1]["acciones_permitidas"]:
                raise ValueError(f"La máscara futura difiere de la próxima decisión en {ep['episodio']}:{fila['paso']}.")
            if terminal != (fila["terminal"] == "1" or not siguientes):
                raise ValueError(f"El objetivo Q tiene una terminación inválida en {ep['episodio']}:{fila['paso']}.")
            agente.actualizar(
                estado, indice, float(fila["recompensa_aprendizaje"]),
                None if terminal else int(fila["siguiente_estado"]), terminal,
                tuple(ACCIONES.index(a) for a in siguientes.split(";") if a),
            )
    if not np.array_equal(agente.q, tabla):
        raise ValueError("El registro de entrenamiento no reproduce la tabla Q final.")


def variables_caso(caso):
    modo, politica, semilla, ref, semilla_eval, inicio, n_eval = caso
    cfg = {**ref.configuracion, "evaluacion": n_eval}
    variables = variables_evaluacion("corregido", cfg, None if modo == "entrenar" else ref.tabla)
    variables.update(
        UMARS_ENTRENAMIENTO=str(ENTRENAMIENTO),
        UMARS_V8_ESTUDIO_BORDE=modo,
        UMARS_V8_SEMILLA_EVALUACION=str(semilla_eval),
        UMARS_V8_PRIMER_EPISODIO_EVAL=str(inicio),
        UMARS_V8_PANEL_LIDAR="1",
        UMARS_V8_SALIR="0",
    )
    return variables


def comandos(caso, webots):
    modo, politica, semilla, *_ = caso
    variables = variables_caso(caso)
    print(f"# {modo} | {politica} | semilla {semilla}")
    for clave, valor in variables.items():
        if clave in ("WEBOTS_PYTHON_COMMAND", "UMARS_V8_TABLA_CONGELADA"):
            ruta = os.path.relpath(valor, ROOT).replace("'", "''")
            print(f"$env:{clave} = (Resolve-Path -LiteralPath '{ruta}').Path")
        else:
            print(f"$env:{clave} = '{valor}'")
    webots = str(webots).replace("'", "''")
    print(f"& '{webots}' --mode=pause (Resolve-Path -LiteralPath 'worlds/marte_v8_dinamico.wbt').Path")


def csv_resultado(nombre, campos, filas):
    with (SALIDA / nombre).open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)


def informar_rescate(caso, corrida):
    ref = caso[3]
    base = obtener(ref, "corregido")
    if base is None:
        raise ValueError("Falta la referencia congelada de D 2042.")
    previo = next(f for f in base[1] if f["semilla_escenario"] == "102061")
    ruta, [f], trazas = corrida
    despues = trazas[f["fase"], f["episodio"]]
    antes = base[2][previo["episodio"]]
    comunes = (set(antes[0]) & set(despues[0])) - {"acciones_permitidas", "accion"}
    if len(despues) < 19 or any(
           a["accion"] != b["accion"] or any(a[k] != b[k] for k in comunes)
           for a, b in zip(antes[:18], despues[:18])):
        raise ValueError("La prueba de rescate divergió antes del bloqueo de referencia.")
    medidas = [{"variante": v, "resultado": ep["resultado"], **metricas(ep, t)}
               for v, ep, t in (("referencia", previo, antes), ("rescate", f, despues))]
    csv_resultado("rescate_102061.csv", list(medidas[0]), medidas)
    print(f"102061 · referencia {previo['resultado']} · rescate {f['resultado']} · "
          f"paso 19: {despues[18]['accion'] or 'sin acción'} · datos en {ruta}")


def informar_comparacion(corridas):
    grupos = defaultdict(dict)
    registros = []
    consolidado = []
    referencia_escenarios = {}
    referencia_train = {}
    for (modo, politica, semilla), (ruta, episodios, trazas) in corridas.items():
        if modo == "rescate":
            continue
        nombre = f"{politica}_{'nuevo' if modo == 'entrenar' else 'histórico'}" if politica != "reglas" else politica
        train = [tuple(f[k] for k in ESCENARIO) for f in episodios if f["fase"] == "ENTRENAMIENTO"]
        if modo == "entrenar" and referencia_train.setdefault(semilla, train) != train:
            raise ValueError(f"C y D entrenaron en escenarios distintos para {semilla}.")
        evaluados = [f for f in episodios if f["fase"] != "ENTRENAMIENTO"]
        escenarios = [tuple(f[k] for k in ESCENARIO) for f in evaluados]
        if referencia_escenarios.setdefault(semilla, escenarios) != escenarios:
            raise ValueError(f"Las políticas evaluaron escenarios distintos para {semilla}.")
        incluido = {}
        for ep in evaluados:
            trans = trazas[ep["fase"], ep["episodio"]]
            acciones, giros = movimientos_ejecutados(ep, trans)
            fila = dict(politica=nombre, semilla=semilla, semilla_escenario=ep["semilla_escenario"],
                        resultado=ep["resultado"], **metricas(ep, trans),
                        acciones_ejecutadas=acciones, giros_ejecutados=giros)
            registros.append(fila)
            incluido[ep["semilla_escenario"]] = fila
        grupos[semilla][nombre] = incluido
        consolidado.append(dict(
            politica=nombre, semilla=semilla, escenarios=len(evaluados),
            **{m: sum(e[m] for e in incluido.values()) for m in MEDIDAS},
            corrida=ruta.relative_to(SALIDA).as_posix(),
        ))

    comparaciones, unicos = [], []
    acumulados = defaultdict(list)
    for semilla, politicas in grupos.items():
        for a, b in combinations(sorted(politicas), 2):
            datos = [(p, politicas[b][k]) for k, p in politicas[a].items()]
            acumulados[a,b].extend(datos)
            comparaciones.append(comparar_pares(datos, "evaluacion", a, b, {"semilla": semilla}))
            for x, y in datos:
                if x["llegadas"] != y["llegadas"]:
                    unicos.append(dict(
                        semilla=semilla, semilla_escenario=x["semilla_escenario"],
                        politica_izquierda=a, politica_derecha=b,
                        resultado_izquierda=x["resultado"], resultado_derecha=y["resultado"],
                    ))
    comparaciones.extend(comparar_pares(datos, "evaluacion", a, b, {"semilla": "total"})
                         for (a, b), datos in acumulados.items())
    csv_resultado("consolidado.csv", list(consolidado[0]), consolidado)
    csv_resultado("episodios.csv", list(registros[0]), registros)
    csv_resultado("eficiencia_pareada.csv", list(comparaciones[0]), comparaciones)
    csv_resultado("llegadas_exclusivas.csv",
                  ["semilla", "semilla_escenario", "politica_izquierda", "politica_derecha",
                   "resultado_izquierda", "resultado_derecha"], unicos)
    informe = SALIDA / "informe.md"
    texto = informe.read_text(encoding="utf-8")
    encabezado = "## Resultados medidos de la evaluación"
    texto = texto.split(encabezado)[0].split("**Estado de la comparación.**")[0].rstrip()
    lineas = [
        encabezado, "",
        "| Política | Semilla | Llegadas | Vetos de borde | Contactos | Sin acciones | Límite | Acciones ejecutadas | Giros ejecutados |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for f in consolidado:
        lineas.append(f"| {f['politica']} | {f['semilla']} | {f['llegadas']}/{f['escenarios']} | "
                       f"{f['vetos_borde']} | {f['contactos_rocas']} | {f['sin_acciones_seguras']} | "
                       f"{f['max_acciones']} | {f['acciones_ejecutadas']} | {f['giros_ejecutados']} |")
    lineas.extend([
        "", "### Eficiencia en llegadas compartidas", "",
        "| Políticas | Llegadas compartidas | Acciones medias | Giros medios | Llegadas exclusivas |",
        "|---|---:|---:|---:|---:|",
    ])
    for f in comparaciones:
        if f["semilla"] == "total":
            lineas.append(f"| {f['izquierda']} y {f['derecha']} | {f['llegadas_compartidas']} | "
                           f"{f['acciones_ejecutadas_izquierda']} / {f['acciones_ejecutadas_derecha']} | "
                           f"{f['giros_ejecutados_izquierda']} / {f['giros_ejecutados_derecha']} | "
                           f"{f['perdidos']} / {f['recuperados']} |")
    lineas.extend([
        "", "Los resultados describen las tres semillas y los escenarios de evaluación ejecutados.",
        "", "[Consolidado](consolidado.csv) · [Episodios](episodios.csv) · "
        "[Eficiencia pareada](eficiencia_pareada.csv) · [Llegadas exclusivas](llegadas_exclusivas.csv)",
    ])
    informe.write_text(texto + "\n\n" + "\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Comparación completa en {SALIDA}")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--webots", type=Path, default=WEBOTS)
    args = parser.parse_args()
    corridas = {}
    casos = list(casos_estudio())
    for caso in casos:
        corrida = cargar_caso(caso)
        if corrida is None:
            print(f"# {len(corridas)} de {len(casos)} corridas completas.")
            comandos(caso, args.webots)
            return
        corridas[caso[:3]] = corrida
        if caso[0] == "rescate":
            informar_rescate(caso, corrida)
    informar_comparacion(corridas)


if __name__ == "__main__":
    main()
