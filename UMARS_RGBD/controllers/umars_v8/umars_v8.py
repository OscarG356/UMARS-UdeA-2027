"""Experimentos v8 aislados de v7. Ejecutar desde marte_v8_*.wbt."""

from controller import Supervisor
from pathlib import Path
from datetime import datetime
from io import BytesIO
import csv
import hashlib
import json
import math
import os
import sys
import uuid

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "umars_qlearning"))
from agente_q import (
    ACCIONES, AgenteQ, FiltroAntibucle, acciones_permitidas, codificar_estado, actualizar_lado,
)
from entorno import EntornoUMARS
from movimientos import calcular_movimiento
from percepcion import analizar_regiones, fusionar_avances_lidar
from politica_reglas import PoliticaReglas
from visualizar_lidar import PanelLidar
from control_v8 import (
    NORTE, SUR, GIROS_PUROS, RocasV8, costo_giro, giro_abre_avance,
    parametros_episodio, pose_fraccion, rectangulo, respeta_limites, validar_accion_temporal,
)


def entero(nombre, defecto, minimo=1):
    valor = int(os.getenv(nombre, str(defecto)))
    if valor < minimo:
        raise ValueError(f"{nombre} debe ser >= {minimo}")
    return valor


def real(nombre, defecto):
    valor = float(os.getenv(nombre, str(defecto)))
    if not math.isfinite(valor):
        raise ValueError(f"{nombre} debe ser finito")
    return valor


ROVER = Supervisor()
STEP_MS = int(ROVER.getBasicTimeStep())
DT = STEP_MS / 1000.0
PASOS_POR_ACCION = 3
ENTRENAMIENTO = entero("UMARS_ENTRENAMIENTO", 60)
EVALUACION = entero("UMARS_EVALUACION", 10)
MAX_ACCIONES = entero("UMARS_MAX_ACCIONES", 120)
SEMILLA = entero("UMARS_V8_SEMILLA", 42, 0)
POLITICA = os.getenv("UMARS_V8_POLITICA", "q").lower()
if POLITICA not in ("q", "reglas"):
    raise ValueError("UMARS_V8_POLITICA debe ser q o reglas")

ENTORNO = EntornoUMARS(ROVER)
NODO_NORTE = ROVER.getFromDef("UMARS_ROCA_MOVIL_NORTE")
NODO_SUR = ROVER.getFromDef("UMARS_ROCA_MOVIL_SUR")
if (NODO_NORTE is None) != (NODO_SUR is None):
    raise RuntimeError("El mundo dinamico debe definir ambas rocas moviles")
DINAMICO = NODO_NORTE is not None
PENALIZACION = real("UMARS_V8_PENALIZACION_GIRO", 0.2)
if PENALIZACION < 0:
    raise ValueError("UMARS_V8_PENALIZACION_GIRO debe ser >= 0")
EXPERIMENTO = ("B" if PENALIZACION > 0 else "A") if not DINAMICO else (
    "D" if PENALIZACION > 0 else "C"
)
ESPERADO = os.getenv("UMARS_V8_EXPERIMENTO", EXPERIMENTO).upper()
if ESPERADO != EXPERIMENTO:
    raise RuntimeError(f"Este mundo/configuracion es {EXPERIMENTO}, no {ESPERADO}")

PRUEBA_BORDE = os.getenv("UMARS_V8_PRUEBA_BORDE")
if PRUEBA_BORDE and (
    PRUEBA_BORDE not in ("original", "corregido") or not DINAMICO
):
    raise ValueError("La prueba de borde requiere el mundo dinamico")
FILTRO_BORDE = PRUEBA_BORDE == "corregido"
ESTUDIO_BORDE = os.getenv("UMARS_V8_ESTUDIO_BORDE")
if ESTUDIO_BORDE and (not FILTRO_BORDE or ESTUDIO_BORDE not in ("rescate", "entrenar", "comparar")
                     or (POLITICA != "q" and ESTUDIO_BORDE != "comparar")):
    raise ValueError("Modo de estudio de borde incompatible con esta configuración")
APRENDER_BORDE = ESTUDIO_BORDE == "entrenar"
SEMILLA_EVALUACION = entero("UMARS_V8_SEMILLA_EVALUACION", SEMILLA, 0) if ESTUDIO_BORDE else SEMILLA
PRIMER_EPISODIO_EVAL = entero("UMARS_V8_PRIMER_EPISODIO_EVAL", 1) if ESTUDIO_BORDE else 1
VALIDACION_BORDE = bool(PRUEBA_BORDE) and (
    ESTUDIO_BORDE is not None or os.getenv("UMARS_V8_VALIDACION_BORDE") == "1"
)

if os.getenv("UMARS_META_X") is not None and os.getenv("UMARS_META_Y") is not None:
    _, _, altura = ENTORNO.campo_meta.getSFVec3f()
    ENTORNO.campo_meta.setSFVec3f([
        real("UMARS_META_X", 2.2), real("UMARS_META_Y", 0.75), altura,
    ])

CAMPOS_ROCAS = ({
    NORTE: NODO_NORTE.getField("translation"),
    SUR: NODO_SUR.getField("translation"),
} if DINAMICO else {})
if VALIDACION_BORDE:
    # Webots puede guardar el mundo con las rocas en las poses del último episodio.
    # El lote de referencia definió sus trayectorias alrededor de estos centros.
    centros = {NORTE: (0.6, 1.0, NODO_NORTE), SUR: (1.3, -0.8, NODO_SUR)}
    for indice, (nombre, _) in enumerate(ENTORNO.obstaculos):
        if nombre in centros:
            x, y, nodo = centros[nombre]
            caja = nodo.getField("boundingObject").getSFNode()
            ancho, alto, _ = caja.getField("size").getSFVec3f()
            ENTORNO.obstaculos[indice] = nombre, rectangulo(x, y, ancho, alto)
ROCAS = RocasV8(ENTORNO, CAMPOS_ROCAS)
POSICION = ROVER.getSelf().getField("translation")
ROTACION = ROVER.getSelf().getField("rotation")
RGB = ROVER.getDevice("rgb")
DEPTH = ROVER.getDevice("depth")
LIDAR = ROVER.getDevice("lidar_seguridad")
RGB.enable(STEP_MS)
DEPTH.enable(STEP_MS)
LIDAR.enable(STEP_MS)
LIDAR.enablePointCloud()
PANEL = PanelLidar(ROVER.getDevice("lidar_display"))
PANEL.activa = os.getenv("UMARS_V8_PANEL_LIDAR", "1") != "0"
AGENTE = AgenteQ(alpha=0.10, gamma=0.95, semilla=SEMILLA)
TABLA_CONGELADA = None
if PRUEBA_BORDE and POLITICA == "q" and not APRENDER_BORDE:
    origen_tabla = Path(os.environ["UMARS_V8_TABLA_CONGELADA"]).resolve()
    contenido_tabla = origen_tabla.read_bytes()
    TABLA_CONGELADA = np.load(BytesIO(contenido_tabla), allow_pickle=False)
    if TABLA_CONGELADA.shape != AGENTE.q.shape or not np.isfinite(TABLA_CONGELADA).all():
        raise ValueError(f"La tabla congelada debe tener forma {AGENTE.q.shape} y valores finitos")
    AGENTE.q[:] = TABLA_CONGELADA
    AGENTE.q.setflags(write=False)

TABLA_V7 = (Path(__file__).resolve().parents[2] / "resultados" /
            "diagnostico_ql_meta_lejana_v7_max120" / "q_table.npy")
TABLA_V7_HASH = None
if EXPERIMENTO == "A" and POLITICA == "q":
    if not TABLA_V7.exists():
        raise FileNotFoundError(f"Falta la tabla historica v7: {TABLA_V7}")
    tabla = np.load(TABLA_V7)
    if tabla.shape != AGENTE.q.shape:
        raise ValueError(f"La tabla v7 debe tener forma {AGENTE.q.shape}")
    AGENTE.q[:] = tabla
    TABLA_V7_HASH = hashlib.sha256(TABLA_V7.read_bytes()).hexdigest()

ESCALA = real("UMARS_V8_ESCALA_VELOCIDAD", 1.0)
AMPLITUD_N = real("UMARS_V8_AMPLITUD_NORTE", 0.35)
AMPLITUD_SX = real("UMARS_V8_AMPLITUD_SUR_X", 0.25)
AMPLITUD_SY = real("UMARS_V8_AMPLITUD_SUR_Y", 0.25)
DESFASE_N = real("UMARS_V8_DESFASE_NORTE", 0.0)
DESFASE_S = real("UMARS_V8_DESFASE_SUR", 0.0)

SALIDA_BASE = Path(__file__).resolve().parents[2] / "resultados" / "experimentos_v8"
IDENTIFICADOR = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
SALIDA = SALIDA_BASE / EXPERIMENTO / f"{POLITICA}_{IDENTIFICADOR}"
if PRUEBA_BORDE:
    SALIDA = SALIDA_BASE.parent / "prueba_borde_v8" / PRUEBA_BORDE / IDENTIFICADOR
    if VALIDACION_BORDE:
        grupo = EXPERIMENTO if POLITICA == "q" else "reglas"
        SALIDA = (SALIDA_BASE.parent / "validacion_borde_v8" / f"{grupo}_{SEMILLA}"
                  / PRUEBA_BORDE / IDENTIFICADOR)
if ESTUDIO_BORDE:
    grupo = EXPERIMENTO if POLITICA == "q" else "reglas"
    SALIDA = SALIDA_BASE.parent / "aprendizaje_borde_v8" / ESTUDIO_BORDE / f"{grupo}_{SEMILLA}" / IDENTIFICADOR
SALIDA.mkdir(parents=True, exist_ok=False)

CONFIG = {
    "version": "v8", "experimento": EXPERIMENTO, "dinamico": DINAMICO,
    "politica": POLITICA, "semilla": SEMILLA,
    "entrenamiento": 0 if PRUEBA_BORDE and not APRENDER_BORDE else ENTRENAMIENTO,
    "evaluacion": EVALUACION, "max_acciones": MAX_ACCIONES,
    "alpha": AGENTE.alpha, "gamma": AGENTE.gamma,
    "epsilon_inicial": 1.0, "epsilon_minimo": 0.05, "decaimiento": 0.95,
    "penalizacion_giro": PENALIZACION, "basicTimeStep_ms": STEP_MS,
    "pasos_webots_por_accion": PASOS_POR_ACCION,
    "escala_velocidad": ESCALA, "amplitud_norte": AMPLITUD_N,
    "amplitud_sur_x": AMPLITUD_SX, "amplitud_sur_y": AMPLITUD_SY,
    "desfase_norte": DESFASE_N, "desfase_sur": DESFASE_S,
    "meta": ENTORNO.campo_meta.getSFVec3f(),
    "posicion_inicial": ENTORNO.posicion_inicial,
    "paneles_webots": ["rgb", "depth", "lidar_display"],
    "modelo_colision": "circulo-rectangulo temporal, rocas y rover sincronizados",
    "tabla_v7_origen": str(TABLA_V7) if TABLA_V7_HASH else None,
    "tabla_v7_sha256": TABLA_V7_HASH,
}
if PRUEBA_BORDE:
    CONFIG["prueba_borde"] = PRUEBA_BORDE
    if TABLA_CONGELADA is not None:
        CONFIG.update(tabla_congelada=str(origen_tabla),
                      tabla_congelada_sha256=hashlib.sha256(contenido_tabla).hexdigest())
if ESTUDIO_BORDE:
    CONFIG.update(estudio_borde=ESTUDIO_BORDE, semilla_evaluacion=SEMILLA_EVALUACION,
                  primer_episodio_evaluacion=PRIMER_EPISODIO_EVAL)
if os.getenv("UMARS_V8_LOTE"):
    CONFIG["lote"] = os.environ["UMARS_V8_LOTE"]
(SALIDA / "configuracion.json").write_text(
    json.dumps(CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
)


def paso_webots():
    if ROVER.step(STEP_MS) == -1:
        raise SystemExit("Webots cerro la simulacion")


def observar(rumbo):
    imagen = DEPTH.getRangeImage()
    puntos = LIDAR.getPointCloud()
    if imagen is None or puntos is None or len(puntos) == 0:
        raise RuntimeError("RGB-D o Lidar no entregaron datos")
    zonas = analizar_regiones(imagen, DEPTH.getWidth(), DEPTH.getHeight())
    if ESTUDIO_BORDE == "comparar":
        zonas["acciones_seguras_rgbd"] = zonas["acciones_seguras"].copy()
    zonas = fusionar_avances_lidar(zonas, puntos)
    zonas["_puntos_lidar"] = puntos
    pos = POSICION.getSFVec3f()
    mx, my, _ = ENTORNO.campo_meta.getSFVec3f()
    error = (math.atan2(my - pos[1], mx - pos[0]) - rumbo + math.pi) % (2 * math.pi) - math.pi
    direccion = -1 if error > math.pi / 6 else 1 if error < -math.pi / 6 else 0
    distancia = ENTORNO.distancia_meta(pos)
    return zonas, direccion, error, distancia


def reiniciar(fase, episodio):
    parametros = parametros_episodio(
        DINAMICO, SEMILLA if fase == "ENTRENAMIENTO" else SEMILLA_EVALUACION, fase, episodio, ESCALA,
        AMPLITUD_N, AMPLITUD_SX, AMPLITUD_SY, DESFASE_N, DESFASE_S,
    )
    ROCAS.configurar(parametros)
    ENTORNO.reiniciar(POSICION, ROTACION)
    tiempo = 0.0
    for _ in range(PASOS_POR_ACCION):
        tiempo += DT
        ROCAS.actualizar(tiempo)
        paso_webots()
    motivo = ENTORNO.detectar_colision(POSICION.getSFVec3f())
    if motivo:
        raise RuntimeError(f"Rover colisiona al reiniciar: {motivo}")
    return parametros, tiempo


def ejecutar(accion, rumbo, tiempo):
    antes = POSICION.getSFVec3f()
    rumbo_inicial = rumbo
    duracion = PASOS_POR_ACCION * DT
    motivo = None
    origen_colision = ""
    if DINAMICO:
        permitido, motivo, _ = validar_accion_temporal(
            antes, rumbo, accion, tiempo, duracion, ROCAS,
            ENTORNO.limites, ENTORNO.radio_rover,
        )
        if not permitido:
            origen_colision = "VETO_TRAYECTORIA"
    else:
        destino, rumbo_destino, puntos = calcular_movimiento(
            antes, rumbo, accion, 0.20, math.pi / 6
        )
        permitido, motivo = ENTORNO.validar_trayectoria(puntos)
        if not permitido:
            origen_colision = "VETO_TRAYECTORIA"
        if permitido:
            if puntos:
                POSICION.setSFVec3f(destino)
            rumbo = rumbo_destino
            ROTACION.setSFRotation([0, 0, 1, rumbo])

    for subpaso in range(1, PASOS_POR_ACCION + 1):
        tiempo += DT
        ROCAS.actualizar(tiempo)
        if DINAMICO and permitido and motivo is None:
            pose, rumbo_actual = pose_fraccion(
                antes, rumbo_inicial, accion, subpaso / PASOS_POR_ACCION
            )
            POSICION.setSFVec3f(pose)
            ROTACION.setSFRotation([0, 0, 1, rumbo_actual])
            rumbo = rumbo_actual
        paso_webots()
        actual = ENTORNO.detectar_colision(POSICION.getSFVec3f())
        if actual:
            motivo = actual
            origen_colision = "CONTACTO_GEOMETRICO"
    return antes, POSICION.getSFVec3f(), rumbo, tiempo, motivo, origen_colision


EP_FIELDS = [
    "experimento", "politica", "fase", "episodio", "semilla_escenario",
    "omega_norte", "omega_sur", "fase_norte", "fase_sur",
    "inicio_x", "inicio_y", "meta_x", "meta_y", "pasos", "giros_puros",
    "giros_con_avance_seguro", "giros_forzados", "distancia_recorrida_m",
    "retorno_entrenamiento", "retorno_base", "penalizacion_total",
    "resultado", "exito", "colision", "tiempo_simulado_s",
    "vetos_trayectoria", "contactos_geometricos",
    "intervenciones_antibucle", "epsilon", "distancia_final_meta_m",
]
TR_FIELDS = [
    "experimento", "politica", "fase", "episodio", "paso", "estado",
    *[f"q_{accion.lower()}" for accion in ACCIONES],
    "accion", "acciones_permitidas", "avance_seguro_recto",
    "avance_seguro_izquierda", "avance_seguro_derecha",
    "recompensa_base", "penalizacion_giro", "recompensa_aprendizaje",
    "distancia_meta_m", "x", "y", "rumbo_rad", "lidar_min_m",
    "roca_norte_x", "roca_norte_y", "roca_sur_x", "roca_sur_y",
    "siguiente_estado", "terminal", "motivo_terminacion",
    "origen_colision", "antibucle_activo",
]
if PRUEBA_BORDE:
    TR_FIELDS.append("acciones_antes_filtro_borde")
if APRENDER_BORDE:
    TR_FIELDS.extend(("terminal_q", "acciones_permitidas_siguiente"))
if ESTUDIO_BORDE == "comparar":
    TR_FIELDS.extend((
        "rgbd_min_franja_m", "rgbd_izquierda_m", "rgbd_centro_m", "rgbd_derecha_m",
        "avances_seguros_rgbd", "avances_seguros_lidar",
    ))


def filtrar_borde(permitidas, posicion, rumbo):
    return tuple(i for i in permitidas if respeta_limites(
        posicion, rumbo, ACCIONES[i], ENTORNO.limites, ENTORNO.radio_rover
    ))


def ejecutar_fase(fase, cantidad, ep_writer, tr_writer):
    epsilon = 1.0 if fase == "ENTRENAMIENTO" else 0.0
    resumen = []
    primero = 1 if fase == "ENTRENAMIENTO" else PRIMER_EPISODIO_EVAL
    for episodio in range(primero, primero + cantidad):
        parametros, tiempo = reiniciar(fase, episodio)
        rumbo, lado = 0.0, 0
        zonas, direccion, error, distancia = observar(rumbo)
        estado = codificar_estado(zonas, direccion, lado, distancia)
        filtro = FiltroAntibucle()
        reglas = PoliticaReglas()
        retorno_base = retorno_aprendizaje = penalizacion_total = 0.0
        giros = giros_electivos = giros_forzados = intervenciones = 0
        vetos_trayectoria = contactos_geometricos = 0
        recorrido = 0.0
        resultado_final = "MAX_ACCIONES"
        acciones_ejecutadas = 0
        inicio = ENTORNO.posicion_inicial
        meta = ENTORNO.campo_meta.getSFVec3f()
        for paso in range(1, MAX_ACCIONES + 1):
            permitidas = (acciones_permitidas(zonas) if PRUEBA_BORDE and fase == "REGLAS"
                          else filtro.permitidas(zonas, error))
            campos_borde = {}
            if PRUEBA_BORDE:
                campos_borde["acciones_antes_filtro_borde"] = ";".join(ACCIONES[i] for i in permitidas)
            if FILTRO_BORDE:
                posicion = POSICION.getSFVec3f()
                permitidas = filtrar_borde(permitidas, posicion, rumbo)
                if ESTUDIO_BORDE == "rescate" and not permitidas and filtro.giro_escape is not None:
                    # La validación temporal de la acción se mantiene en ejecutar().
                    permitidas = tuple(i for i, giro in enumerate(ACCIONES)
                                      if giro in GIROS_PUROS and giro_abre_avance(
                                          posicion, rumbo, giro, ENTORNO.limites, ENTORNO.radio_rover))
            activo = filtro.giro_escape is not None
            intervenciones += int(activo)
            fila_q = AGENTE.q[estado].copy()
            decision = {
                "experimento": EXPERIMENTO, "politica": POLITICA,
                "fase": fase, "episodio": episodio, "paso": paso, "estado": estado,
                **{f"q_{a.lower()}": float(v) for a, v in zip(ACCIONES, fila_q)},
                "acciones_permitidas": ";".join(ACCIONES[i] for i in permitidas),
                "lidar_min_m": zonas["lidar_min_m"], "antibucle_activo": int(activo),
                **campos_borde,
            }
            if ESTUDIO_BORDE == "comparar":
                decision.update(
                    rgbd_min_franja_m=zonas["distancia_avance_m"],
                    **{f"rgbd_{sector}_m": zonas[sector]["distancia_m"]
                       for sector in ("izquierda", "centro", "derecha")},
                    **{f"avances_seguros_{sensor}": ";".join(
                        a for a in ACCIONES if zonas[f"acciones_seguras_{sensor}"].get(a))
                       for sensor in ("rgbd", "lidar")},
                )
            if FILTRO_BORDE and not permitidas:
                resultado_final = "SIN_ACCIONES_SEGURAS_BORDE"
                tr_writer.writerow({
                    **decision, "terminal": 1, "motivo_terminacion": resultado_final,
                    "x": posicion[0], "y": posicion[1], "rumbo_rad": rumbo,
                    "distancia_meta_m": distancia,
                })
                break
            if fase == "REGLAS":
                lado_reglas = reglas.lado
                indice = reglas.elegir_accion(zonas, direccion)
                if FILTRO_BORDE and indice not in permitidas:
                    reglas.lado = lado_reglas
                    avances = {a: ACCIONES.index(a) in permitidas for a in zonas["acciones_seguras"]}
                    zonas_reglas = {**zonas, "acciones_seguras": avances,
                                    "avance_seguro": avances["AVANZAR"]}
                    indice = reglas.elegir_accion(zonas_reglas, direccion)
            else:
                indice = AGENTE.elegir_accion(estado, epsilon, permitidas)
            accion = ACCIONES[indice]
            seguras = zonas["acciones_seguras"]
            hay_avance = any(seguras[a] for a in (
                "AVANZAR", "AVANZAR_IZQUIERDA", "AVANZAR_DERECHA"
            ))
            if accion in GIROS_PUROS:
                giros += 1
                giros_electivos += int(hay_avance)
                giros_forzados += int(not hay_avance)
            PANEL.mostrar(zonas, fase, episodio, paso, accion)
            antes, despues, rumbo, tiempo, motivo, origen_colision = ejecutar(
                accion, rumbo, tiempo
            )
            acciones_ejecutadas += 1
            vetos_trayectoria += int(origen_colision == "VETO_TRAYECTORIA")
            contactos_geometricos += int(origen_colision == "CONTACTO_GEOMETRICO")
            recorrido += math.hypot(despues[0] - antes[0], despues[1] - antes[1])
            resultado = ENTORNO.evaluar_transicion(antes, despues, motivo)
            base = float(resultado["recompensa"])
            # Los terminos terminales quedan identicos a la referencia v7.
            coste = 0.0 if resultado["terminado"] else costo_giro(
                accion, zonas, PENALIZACION
            )
            recompensa = base + coste
            retorno_base += base
            retorno_aprendizaje += recompensa
            penalizacion_total += coste
            if fase != "REGLAS":
                filtro.registrar(indice, antes, despues)
            terminal = bool(resultado["terminado"] or paso == MAX_ACCIONES)
            fin = (motivo or "META" if resultado["terminado"] else
                   "MAX_ACCIONES" if paso == MAX_ACCIONES else "")
            if terminal:
                siguiente_estado = None
                siguientes_permitidas = None
            else:
                zonas2, direccion2, error2, distancia2 = observar(rumbo)
                lado2 = actualizar_lado(lado, indice, zonas, zonas2)
                siguiente_estado = codificar_estado(
                    zonas2, direccion2, lado2, distancia2
                )
                siguientes_permitidas = filtro.permitidas(zonas2, error2)
                if APRENDER_BORDE:
                    siguientes_permitidas = filtrar_borde(siguientes_permitidas, despues, rumbo)
            if fase == "ENTRENAMIENTO":
                terminal_q = terminal or (APRENDER_BORDE and not siguientes_permitidas)
                AGENTE.actualizar(
                    estado, indice, recompensa, siguiente_estado,
                    terminal_q, siguientes_permitidas,
                )
                if APRENDER_BORDE:
                    decision.update(
                        terminal_q=int(terminal_q),
                        acciones_permitidas_siguiente=";".join(
                            ACCIONES[i] for i in (siguientes_permitidas or ())
                        ),
                    )
            posiciones = ROCAS.posiciones(tiempo)
            tr_writer.writerow({
                **decision,
                "accion": accion,
                "avance_seguro_recto": int(seguras["AVANZAR"]),
                "avance_seguro_izquierda": int(seguras["AVANZAR_IZQUIERDA"]),
                "avance_seguro_derecha": int(seguras["AVANZAR_DERECHA"]),
                "recompensa_base": base, "penalizacion_giro": coste,
                "recompensa_aprendizaje": recompensa,
                "distancia_meta_m": resultado["distancia_actual"],
                "x": despues[0], "y": despues[1], "rumbo_rad": rumbo,
                "roca_norte_x": posiciones[NORTE][0],
                "roca_norte_y": posiciones[NORTE][1],
                "roca_sur_x": posiciones[SUR][0],
                "roca_sur_y": posiciones[SUR][1],
                "siguiente_estado": "" if terminal else siguiente_estado,
                "terminal": int(terminal), "motivo_terminacion": fin,
                "origen_colision": origen_colision,
            })
            distancia = resultado["distancia_actual"]
            if os.getenv("UMARS_DEBUG_STEPS", "0") == "1":
                print(f"{fase} E{episodio:03d} P{paso:03d} s={estado} "
                      f"Q={fila_q.round(3).tolist()} a={accion} "
                      f"r={recompensa:.3f} d={resultado['distancia_actual']:.3f} "
                      f"fin={fin or '-'}", flush=True)
            if terminal:
                resultado_final = fin
                break
            zonas, direccion, error, distancia, lado, estado = (
                zonas2, direccion2, error2, distancia2, lado2, siguiente_estado
            )
        ep_writer.writerow({
            "experimento": EXPERIMENTO, "politica": POLITICA, "fase": fase,
            "episodio": episodio, "semilla_escenario": parametros.semilla,
            "omega_norte": parametros.omega_norte, "omega_sur": parametros.omega_sur,
            "fase_norte": parametros.fase_norte, "fase_sur": parametros.fase_sur,
            "inicio_x": inicio[0], "inicio_y": inicio[1],
            "meta_x": meta[0], "meta_y": meta[1], "pasos": acciones_ejecutadas,
            "giros_puros": giros, "giros_con_avance_seguro": giros_electivos,
            "giros_forzados": giros_forzados,
            "distancia_recorrida_m": recorrido,
            "retorno_entrenamiento": retorno_aprendizaje,
            "retorno_base": retorno_base,
            "penalizacion_total": penalizacion_total,
            "resultado": resultado_final, "exito": int(resultado_final == "META"),
            "colision": int(resultado_final.startswith("COLISION_")
                             or resultado_final == "FUERA_DEL_TERRENO"),
            "tiempo_simulado_s": tiempo - PASOS_POR_ACCION * DT,
            "intervenciones_antibucle": intervenciones,
            "vetos_trayectoria": vetos_trayectoria,
            "contactos_geometricos": contactos_geometricos,
            "epsilon": epsilon, "distancia_final_meta_m": distancia,
        })
        resumen.append((resultado_final, acciones_ejecutadas, retorno_base, giros_electivos))
        print(f"{EXPERIMENTO} {POLITICA} {fase} E{episodio:03d} | {resultado_final} "
              f"| pasos={acciones_ejecutadas} | retorno_base={retorno_base:.2f} "
              f"| giros_electivos={giros_electivos} | epsilon={epsilon:.3f}",
              flush=True)
        if fase == "ENTRENAMIENTO":
            epsilon = max(0.05, epsilon * 0.95)
            if episodio % 10 == 0:
                np.save(SALIDA / "q_table.npy", AGENTE.q)
    return resumen


print(f"UMARS v8: {EXPERIMENTO} {POLITICA}; Q={AGENTE.q.shape}; "
      f"panel lidar={'activo' if PANEL.activa else 'desactivado'}; salida={SALIDA}", flush=True)
with ((SALIDA / "episodios.csv").open("w", newline="", encoding="utf-8") as ep_file,
      (SALIDA / "transiciones.csv").open("w", newline="", encoding="utf-8") as tr_file):
    ep_writer = csv.DictWriter(ep_file, fieldnames=EP_FIELDS)
    tr_writer = csv.DictWriter(tr_file, fieldnames=TR_FIELDS)
    ep_writer.writeheader()
    tr_writer.writeheader()
    fases = ([('REGLAS', EVALUACION)] if POLITICA == "reglas" else
             [('EVALUACION', EVALUACION)] if EXPERIMENTO == "A" or (PRUEBA_BORDE and not APRENDER_BORDE) else
             [('ENTRENAMIENTO', ENTRENAMIENTO), ('EVALUACION', EVALUACION)])
    if EXPERIMENTO == "A" and POLITICA == "q":
        np.save(SALIDA / "q_table.npy", AGENTE.q)
    for fase, cantidad in fases:
        if fase == "EVALUACION" and APRENDER_BORDE:
            AGENTE.q.setflags(write=False)
        datos = ejecutar_fase(fase, cantidad, ep_writer, tr_writer)
        ep_file.flush()
        tr_file.flush()
        n = len(datos)
        print(f"RESUMEN {fase}: exito={sum(x[0] == 'META' for x in datos)}/{n} "
              f"colisiones={sum(x[0].startswith('COLISION_') or x[0] == 'FUERA_DEL_TERRENO' for x in datos)}/{n} "
              f"acciones_promedio={sum(x[1] for x in datos)/n:.2f} "
              f"retorno_base_promedio={sum(x[2] for x in datos)/n:.2f}", flush=True)
        if fase == "ENTRENAMIENTO":
            np.save(SALIDA / "q_table.npy", AGENTE.q)

if os.getenv("UMARS_V8_SALIR", "0") == "1":
    ROVER.simulationQuit(0)
