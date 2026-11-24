
from controller import Supervisor
from pathlib import Path
import sys
import math
import csv
import os
import json
import hashlib
from datetime import datetime
from uuid import uuid4
import numpy as np

# ==========================================
# 1. RUTAS DEL PROYECTO
# ==========================================

RAIZ = Path(__file__).resolve().parents[2]
MAX_ACCIONES = int(os.getenv("UMARS_MAX_ACCIONES", "120"))

MODULOS = RAIZ / "controllers" / "umars_qlearning"
sys.path.insert(0, str(MODULOS))

from agente_q import (
    AgenteQ, ACCIONES, NUM_ESTADOS, DISTANCIA_CORTE, FiltroAntibucle,
    codificar_estado, actualizar_lado,
)
from entorno import EntornoUMARS
from percepcion import analizar_regiones, fusionar_avances_lidar
from politica_reglas import PoliticaReglas
from movimientos import calcular_movimiento
from visualizar_lidar import PanelLidar

TABLA_LEJANA = RAIZ / "resultados" / f"diagnostico_ql_meta_lejana_v7_max{MAX_ACCIONES}" / "q_table.npy"
RUTA_Q = Path(os.getenv(
    "UMARS_Q_PATH",
    str(TABLA_LEJANA)
))

# ==========================================
# 2. PARAMETROS DE EVALUACION
# ==========================================

EPISODIOS = int(os.getenv("UMARS_EVALUACION", "10"))
POLITICA = os.getenv("UMARS_POLITICA", "q").lower()
GENERALIZACION = os.getenv("UMARS_GENERALIZACION", "0") == "1"
DEPURAR_PASOS = os.getenv("UMARS_DEBUG_STEPS", "0") == "1"
MOSTRAR_LIDAR = os.getenv("UMARS_LIDAR_VENTANA", "1") != "0"
if POLITICA not in ("q", "reglas"):
    raise ValueError("UMARS_POLITICA debe ser q o reglas")
if EPISODIOS < 1:
    raise ValueError("UMARS_EVALUACION debe ser al menos 1")

# Se varia la posicion, manteniendo el rumbo inicial y la geometria fijos.
INICIOS_GENERALIZACION = (
    ("base", -1.5, 0.0, 0.0),
    ("norte", -1.5, 0.5, 0.0),
    ("sur", -1.5, -0.5, 0.0),
    ("oeste", -2.0, 0.0, 0.0),
)

PASO = 0.20
GIRO = math.radians(30)

PASOS_WEBOTS = 3
EPSILON = 0.0

# ==========================================
# 3. CARGAR TABLA Q ENTRENADA
# ==========================================

if not RUTA_Q.exists():
    raise FileNotFoundError(
        f"No se encontro la tabla Q compatible. Entrena primero en "
        f"marte_qlearning.wbt:\n{RUTA_Q}"
    )

tabla = np.load(RUTA_Q, allow_pickle=False)

if tabla.shape != (NUM_ESTADOS, len(ACCIONES)):
    raise ValueError(
        f"Tabla Q incorrecta: {tabla.shape}"
    )

if not np.isfinite(tabla).all():
    raise ValueError("La tabla Q contiene valores invalidos")

agente = AgenteQ(
    alpha=0.10,
    gamma=0.95,
    semilla=42
)

agente.q = tabla.copy()

# No actualizaremos la tabla durante la evaluacion.

# ==========================================
# 4. INICIALIZAR WEBOTS
# ==========================================

robot = Supervisor()
step_ms = int(robot.getBasicTimeStep())

rgb = robot.getDevice("rgb")
depth = robot.getDevice("depth")
lidar = robot.getDevice("lidar_seguridad")

rgb.enable(step_ms)
depth.enable(step_ms)
lidar.enable(step_ms)
lidar.enablePointCloud()
panel_lidar = (
    PanelLidar(robot.getDevice("lidar_display")) if MOSTRAR_LIDAR else None
)

nodo = robot.getSelf()

posicion = nodo.getField("translation")
rotacion = nodo.getField("rotation")

entorno = EntornoUMARS(robot)

rumbo = 0.0

# ==========================================
# 5. ACTUALIZAR SIMULACION
# ==========================================

def avanzar_simulacion():

    for _ in range(PASOS_WEBOTS):
        if robot.step(step_ms) == -1:
            raise SystemExit("Simulacion finalizada")

# ==========================================
# 6. CALCULAR DIRECCION HACIA LA META
# ==========================================

def direccion_a_meta(pos):

    mx, my, _ = entorno.campo_meta.getSFVec3f()

    angulo_meta = math.atan2(
        my - pos[1],
        mx - pos[0]
    )

    diferencia = (
        (angulo_meta - rumbo + math.pi)
        % (2 * math.pi)
        - math.pi
    )

    if diferencia > math.pi / 6:
        return -1, diferencia

    if diferencia < -math.pi / 6:
        return 1, diferencia

    return 0, diferencia

# ==========================================
# 7. OBTENER ESTADO DEL AGENTE
# ==========================================

def observar():

    lectura = depth.getRangeImage()

    if lectura is None:
        raise RuntimeError(
            "No se obtuvo profundidad"
        )

    zonas = analizar_regiones(
        lectura,
        depth.getWidth(),
        depth.getHeight()
    )
    puntos_lidar = lidar.getPointCloud()
    zonas = fusionar_avances_lidar(zonas, puntos_lidar)
    zonas["_puntos_lidar"] = puntos_lidar

    pos = posicion.getSFVec3f()
    direccion, error_meta = direccion_a_meta(pos)
    distancia_meta = entorno.distancia_meta(pos)

    return zonas, direccion, error_meta, distancia_meta


# ==========================================
# 8. EJECUTAR ACCION
# ==========================================

def ejecutar_accion(accion):

    global rumbo

    antes = posicion.getSFVec3f()
    motivo = None
    destino, rumbo_nuevo, puntos = calcular_movimiento(
        antes, rumbo, accion, PASO, GIRO
    )
    permitido, motivo = entorno.validar_trayectoria(puntos)
    if permitido:
        if puntos:
            posicion.setSFVec3f(destino)
        rumbo = rumbo_nuevo
        rotacion.setSFRotation([0, 0, 1, rumbo])

    return antes, motivo

# ==========================================
# 9. INICIAR EVALUACION
# ==========================================

meta = entorno.campo_meta.getSFVec3f()
inicios = (
    INICIOS_GENERALIZACION if GENERALIZACION
    else (("base", *entorno.posicion_inicial[:2], 0.0),) * EPISODIOS
)
if GENERALIZACION:
    EPISODIOS = len(inicios)
    for nombre, x, y, _ in inicios:
        punto = [x, y, entorno.posicion_inicial[2]]
        motivo = entorno.detectar_colision(punto)
        if motivo is not None or entorno.distancia_meta(punto) <= entorno.radio_meta:
            raise ValueError(f"Inicio {nombre} invalido: {punto}, {motivo or 'dentro de meta'}")

nombre_politica = "ql" if POLITICA == "q" else POLITICA
if abs(meta[0] - 2.2) < 0.001 and abs(meta[1] - 0.75) < 0.001:
    carpeta = f"diagnostico_evaluacion_{nombre_politica}_lejana_v7_max{MAX_ACCIONES}"
else:
    def etiqueta(valor):
        return f"{valor:.2f}".replace("-", "m").replace(".", "p")

    carpeta = (
        f"diagnostico_evaluacion_{nombre_politica}_meta_"
        f"x{etiqueta(meta[0])}_y{etiqueta(meta[1])}_v7_max{MAX_ACCIONES}"
    )

if GENERALIZACION:
    base_salida = Path(os.getenv("UMARS_SALIDA", str(RAIZ / "resultados" / "generalizacion")))
    identificador = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    SALIDA = base_salida / f"meta_x{meta[0]:+.2f}_y{meta[1]:+.2f}_{nombre_politica}_{identificador}"
    SALIDA.mkdir(parents=True, exist_ok=False)
    configuracion = {
        "modo": "generalizacion",
        "politica": POLITICA,
        "meta": meta,
        "inicios": [dict(nombre=n, x=x, y=y, rumbo_deg=ang) for n, x, y, ang in inicios],
        "max_acciones": MAX_ACCIONES,
        "epsilon": EPSILON,
        "tabla_q": str(RUTA_Q.resolve()),
        "sha256_tabla_q": hashlib.sha256(RUTA_Q.read_bytes()).hexdigest(),
        "limites_terreno": entorno.limites,
        "obstaculos": entorno.obstaculos,
    }
    (SALIDA / "configuracion.json").write_text(
        json.dumps(configuracion, indent=2, ensure_ascii=False), encoding="utf-8"
    )
else:
    SALIDA = Path(os.getenv("UMARS_SALIDA", str(RAIZ / "resultados" / carpeta)))
    SALIDA.mkdir(parents=True, exist_ok=True)

print(f"\nUMARS: EVALUACION {POLITICA.upper()}", flush=True)

print("Tabla cargada:", RUTA_Q, flush=True)
print("Meta:", meta, flush=True)
print("Episodios:", EPISODIOS, flush=True)
print("Max acciones:", MAX_ACCIONES, flush=True)
print("Epsilon:", EPSILON, flush=True)
if GENERALIZACION:
    print("Inicios:", [inicio[0] for inicio in inicios], flush=True)
    print("SHA256 tabla Q:", configuracion["sha256_tabla_q"], flush=True)
print("Salida:", SALIDA, flush=True)

resumen = []

archivo_episodios = SALIDA / "episodios_evaluacion.csv"
archivo_transiciones = SALIDA / "transiciones_evaluacion.csv"

with (
    archivo_episodios.open(
        "w", newline="", encoding="utf-8"
    ) as f_ep,
    archivo_transiciones.open(
        "w", newline="", encoding="utf-8"
    ) as f_tr
):

    w_ep = csv.writer(f_ep)
    w_tr = csv.writer(f_tr)

    w_ep.writerow([
        "episodio",
        "meta_x",
        "meta_y",
        "pasos",
        "retorno",
        "resultado",
        "distancia_final",
        "epsilon", "inicio", "x_inicio", "y_inicio", "rumbo_inicio_deg"
    ])

    w_tr.writerow([
        "episodio",
        "paso",
        "estado",
        *[f"q_{accion.lower()}" for accion in ACCIONES],
        "accion",
        "recompensa",
        "estado_siguiente",
        "terminal",
        "distancia_meta", "motivo_terminacion", "avance_seguro",
        "error_meta_deg", "x_despues", "y_despues", "rumbo_deg",
        "distancia_avance_m", "d_izquierda", "d_centro", "d_derecha",
        "lado_rodeo", "distancia_clase",
        "seguro_avanzar_izquierda", "seguro_avanzar_derecha",
        "lidar_min_m", "lidar_seguro_recto", "lidar_seguro_izquierda",
        "lidar_seguro_derecha", "modo_antibucle", "acciones_permitidas",
        "inicio", "x_inicio", "y_inicio", "rumbo_inicio_deg"
    ])

    # ======================================
    # 10. CICLO DE EPISODIOS
    # ======================================

    for episodio in range(1, EPISODIOS + 1):

        nombre_inicio, x_inicio, y_inicio, rumbo_inicio_deg = inicios[episodio - 1]
        rumbo = math.radians(rumbo_inicio_deg)

        entorno.reiniciar(
            posicion,
            rotacion
        )
        if GENERALIZACION:
            posicion.setSFVec3f([x_inicio, y_inicio, entorno.posicion_inicial[2]])
            rotacion.setSFRotation([0, 0, 1, rumbo])

        avanzar_simulacion()

        lado_rodeo = 0
        zonas, direccion, error_meta, distancia_meta = observar()
        estado = codificar_estado(zonas, direccion, lado_rodeo, distancia_meta)
        reglas = PoliticaReglas()
        filtro_antibucle = FiltroAntibucle()
        retorno = 0.0
        resultado_final = "MAX_ACCIONES"

        for paso in range(1, MAX_ACCIONES + 1):

            # Elegir accion de la politica aprendida
            q_antes = agente.q[estado].copy()
            permitidas = filtro_antibucle.permitidas(zonas, error_meta)
            modo_antibucle = (
                ACCIONES[filtro_antibucle.giro_escape]
                if filtro_antibucle.giro_escape is not None else ""
            )
            indice = (
                reglas.elegir_accion(zonas, direccion)
                if POLITICA == "reglas" else
                agente.elegir_accion(estado, EPSILON, permitidas)
            )

            accion = ACCIONES[indice]
            if panel_lidar is not None:
                panel_lidar.mostrar(zonas, POLITICA.upper(), episodio, paso, accion)

            # Ejecutar movimiento
            antes, motivo = ejecutar_accion(
                accion
            )

            avanzar_simulacion()

            despues = posicion.getSFVec3f()

            # Evaluar resultado
            resultado = entorno.evaluar_transicion(
                antes,
                despues,
                motivo
            )

            recompensa = float(
                resultado["recompensa"]
            )

            if POLITICA == "q":
                filtro_antibucle.registrar(indice, antes, despues)

            retorno += recompensa

            terminal = bool(
                resultado["terminado"]
                or paso >= MAX_ACCIONES
            )

            # Leer nuevo estado
            if terminal:
                siguiente_estado = None
            else:
                zonas_siguientes, direccion_siguiente, error_siguiente, distancia_siguiente = observar()
                lado_siguiente = actualizar_lado(
                    lado_rodeo, indice, zonas, zonas_siguientes
                )
                siguiente_estado = codificar_estado(
                    zonas_siguientes, direccion_siguiente,
                    lado_siguiente, distancia_siguiente
                )

            motivo_terminacion = (
                motivo or ("META" if resultado["llego_meta"] else
                           "MAX_ACCIONES" if paso >= MAX_ACCIONES else "")
            )

            # IMPORTANTE:
            # No llamamos agente.actualizar()
            # durante la evaluacion.

            w_tr.writerow([
                episodio,
                paso,
                estado,
                *[round(float(v), 5) for v in q_antes],
                accion,
                round(recompensa, 5),
                "" if terminal else siguiente_estado,
                int(terminal),
                round(resultado["distancia_actual"], 4),
                motivo_terminacion,
                int(zonas["avance_seguro"]),
                round(math.degrees(error_meta), 2),
                round(despues[0], 4),
                round(despues[1], 4),
                round(math.degrees(rumbo), 2),
                zonas["distancia_avance_m"],
                zonas["izquierda"]["distancia_m"],
                zonas["centro"]["distancia_m"],
                zonas["derecha"]["distancia_m"],
                lado_rodeo,
                int(distancia_meta < DISTANCIA_CORTE),
                int(zonas["acciones_seguras"]["AVANZAR_IZQUIERDA"]),
                int(zonas["acciones_seguras"]["AVANZAR_DERECHA"]),
                zonas["lidar_min_m"],
                int(zonas["acciones_seguras_lidar"]["AVANZAR"]),
                int(zonas["acciones_seguras_lidar"]["AVANZAR_IZQUIERDA"]),
                int(zonas["acciones_seguras_lidar"]["AVANZAR_DERECHA"]),
                modo_antibucle,
                ";".join(ACCIONES[i] for i in permitidas),
                nombre_inicio, x_inicio, y_inicio, rumbo_inicio_deg
            ])
            if DEPURAR_PASOS:
                print(
                    f"E{episodio:02d} P{paso:02d} s={estado} "
                    f"Q={q_antes.round(3).tolist()} a={accion} "
                    f"r={recompensa:.3f} "
                    f"d={resultado['distancia_actual']:.3f} "
                    f"antibucle={modo_antibucle or '-'} "
                    f"error={math.degrees(error_meta):.1f} "
                    f"xy=({despues[0]:.2f},{despues[1]:.2f}) "
                    f"fin={motivo_terminacion or '-'}",
                    flush=True
                )

            if terminal:

                resultado_final = motivo_terminacion
                break

            estado = siguiente_estado
            zonas = zonas_siguientes
            direccion = direccion_siguiente
            error_meta = error_siguiente
            distancia_meta = distancia_siguiente
            lado_rodeo = lado_siguiente

        # ==================================
        # 11. REGISTRAR EPISODIO
        # ==================================

        resumen.append((
            resultado_final,
            paso,
            retorno,
            resultado["distancia_actual"]
        ))

        w_ep.writerow([
            episodio,
            round(meta[0], 4),
            round(meta[1], 4),
            paso,
            round(retorno, 5),
            resultado_final,
            round(resultado["distancia_actual"], 4),
            EPSILON,
            nombre_inicio, x_inicio, y_inicio, rumbo_inicio_deg
        ])

        f_ep.flush()
        f_tr.flush()

        print(
            f"E{episodio:02d} inicio={nombre_inicio} "
            f"| {resultado_final} "
            f"| pasos={paso} "
            f"| retorno={retorno:.3f} "
            f"| distancia={resultado['distancia_actual']:.3f} m",
            flush=True
        )

# ==========================================
# 12. RESUMEN FINAL
# ==========================================

exitos = sum(
    r[0] == "META"
    for r in resumen
)

colisiones = sum(
    r[0].startswith("COLISION_")
    or r[0] == "FUERA_DEL_TERRENO"
    for r in resumen
)

retornos = [
    r[2] for r in resumen
]

print("\n=== RESUMEN EVALUACION ===")

print(
    f"Tasa de exito: "
    f"{100 * exitos / EPISODIOS:.1f}%"
)

print(
    f"Colisiones: "
    f"{colisiones}/{EPISODIOS}"
)

print(
    f"Retorno promedio: "
    f"{np.mean(retornos):.3f}"
)

print(
    "Resultados guardados en:",
    SALIDA
)

print(
    "Tabla Q cargada sin modificaciones."
)
