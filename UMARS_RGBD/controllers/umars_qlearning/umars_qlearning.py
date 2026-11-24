
from controller import Supervisor
from pathlib import Path
import csv
import math
import os
import numpy as np

from percepcion import analizar_regiones, fusionar_avances_lidar
from entorno import EntornoUMARS
from agente_q import (
    AgenteQ, ACCIONES, DISTANCIA_CORTE, FiltroAntibucle, codificar_estado,
    actualizar_lado,
)
from politica_reglas import PoliticaReglas
from movimientos import calcular_movimiento
from visualizar_lidar import PanelLidar

# ==========================================
# 1. CONFIGURACION
# ==========================================

EPISODIOS_ENTRENAMIENTO = int(os.getenv("UMARS_ENTRENAMIENTO", "60"))
EPISODIOS_EVALUACION = int(os.getenv("UMARS_EVALUACION", "10"))
MAX_ACCIONES = int(os.getenv("UMARS_MAX_ACCIONES", "120"))
POLITICA = os.getenv("UMARS_POLITICA", "q").lower()
DEPURAR_PASOS = os.getenv("UMARS_DEBUG_STEPS", "0") == "1"
MOSTRAR_LIDAR = os.getenv("UMARS_LIDAR_VENTANA", "1") != "0"
if POLITICA not in ("q", "reglas"):
    raise ValueError("UMARS_POLITICA debe ser q o reglas")

PASOS_WEBOTS_POR_ACCION = 3

PASO = 0.20
GIRO = math.radians(30)

EPSILON_INICIAL = 1.0
EPSILON_MINIMO = 0.05
DECAIMIENTO = 0.95

# ==========================================
# 2. WEBOTS
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

nodo = robot.getSelf()
posicion = nodo.getField("translation")
rotacion = nodo.getField("rotation")

entorno = EntornoUMARS(robot)
if os.getenv("UMARS_META_X") is not None and os.getenv("UMARS_META_Y") is not None:
    _, _, altura = entorno.campo_meta.getSFVec3f()
    entorno.campo_meta.setSFVec3f([
        float(os.environ["UMARS_META_X"]),
        float(os.environ["UMARS_META_Y"]), altura
    ])

mx, my, _ = entorno.campo_meta.getSFVec3f()
meta_cercana = abs(mx + 0.5) < 0.001 and abs(my - 0.75) < 0.001
carpeta = "diagnostico_ql" if POLITICA == "q" else "diagnostico_reglas"
if not meta_cercana:
    carpeta += "_meta_lejana"
carpeta += f"_v7_max{MAX_ACCIONES}"
SALIDA = Path(os.getenv(
    "UMARS_SALIDA",
    str(Path(__file__).resolve().parents[2] / "resultados" / carpeta)
))
SALIDA.mkdir(parents=True, exist_ok=True)
panel_lidar = (
    PanelLidar(robot.getDevice("lidar_display")) if MOSTRAR_LIDAR else None
)

agente = AgenteQ(
    alpha=0.10,
    gamma=0.95,
    semilla=42
)

rumbo = 0.0


# ==========================================
# 3. ACTUALIZAR SIMULACION
# ==========================================

def avanzar_simulacion():

    for _ in range(PASOS_WEBOTS_POR_ACCION):
        if robot.step(step_ms) == -1:
            raise SystemExit(
                "Webots cerro la simulacion"
            )


# ==========================================
# 4. DIRECCION HACIA LA META
# ==========================================

def direccion_a_meta(pos):

    mx, my, _ = entorno.campo_meta.getSFVec3f()

    angulo_objetivo = math.atan2(
        my - pos[1],
        mx - pos[0]
    )

    diferencia = (
        (angulo_objetivo - rumbo + math.pi)
        % (2 * math.pi)
        - math.pi
    )

    if diferencia > math.pi / 6:
        return -1, diferencia

    if diferencia < -math.pi / 6:
        return 1, diferencia

    return 0, diferencia


# ==========================================
# 5. OBSERVAR ESTADO
# ==========================================

def observar():

    lectura = depth.getRangeImage()

    if lectura is None:
        raise RuntimeError(
            "El sensor de profundidad no responde"
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
# 6. EJECUTAR ACCION
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
# 7. ENTRENAR Y EVALUAR
# ==========================================

resumen = []
epsilon = EPSILON_INICIAL

print(
    "UMARS: experimento v7 iniciado (5 acciones, RGB-D + Lidar)",
    flush=True
)

print(
    "Tabla Q:", agente.q.shape,
    "| MAX_ACCIONES:", MAX_ACCIONES,
    "| META:",
    entorno.campo_meta.getSFVec3f(),
    flush=True
)

with (
    (SALIDA / "episodios.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f_ep,
    (SALIDA / "transiciones.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f_tr
):

    w_ep = csv.writer(f_ep)
    w_tr = csv.writer(f_tr)

    w_ep.writerow([
        "fase", "episodio", "pasos", "retorno",
        "resultado", "epsilon", "distancia_final"
    ])

    w_tr.writerow([
        "fase", "episodio", "paso",
        "estado", *[f"q_{accion.lower()}" for accion in ACCIONES],
        "accion", "recompensa", "distancia_meta",
        "siguiente_estado", "terminal", "motivo_terminacion",
        "avance_seguro", "error_meta_deg", "x_despues", "y_despues",
        "rumbo_deg", "distancia_avance_m", "d_izquierda", "d_centro", "d_derecha",
        "lado_rodeo", "distancia_clase",
        "seguro_avanzar_izquierda", "seguro_avanzar_derecha",
        "lidar_min_m", "lidar_seguro_recto", "lidar_seguro_izquierda",
        "lidar_seguro_derecha", "modo_antibucle", "acciones_permitidas"
    ])

    fases = (
        [("REGLAS", EPISODIOS_EVALUACION)] if POLITICA == "reglas"
        else [("ENTRENAMIENTO", EPISODIOS_ENTRENAMIENTO),
              ("EVALUACION", EPISODIOS_EVALUACION)]
    )

    for fase, cantidad in fases:

        print(
            f"\n=== {fase}: {cantidad} episodios ===",
            flush=True
        )

        for episodio in range(1, cantidad + 1):

            # Reiniciar rover
            rumbo = 0.0
            entorno.reiniciar(
                posicion,
                rotacion
            )

            avanzar_simulacion()

            lado_rodeo = 0
            zonas, direccion, error_meta, distancia_meta = observar()
            estado = codificar_estado(zonas, direccion, lado_rodeo, distancia_meta)
            reglas = PoliticaReglas()
            filtro_antibucle = FiltroAntibucle()
            retorno = 0.0

            resultado_final = "MAX_ACCIONES"

            # En evaluacion no se explora
            epsilon_usado = (
                epsilon
                if fase == "ENTRENAMIENTO"
                else 0.0
            )

            for paso in range(
                1, MAX_ACCIONES + 1
            ):

                # 1. Elegir accion
                q_antes = agente.q[estado].copy()
                permitidas = filtro_antibucle.permitidas(zonas, error_meta)
                modo_antibucle = (
                    ACCIONES[filtro_antibucle.giro_escape]
                    if filtro_antibucle.giro_escape is not None else ""
                )
                indice = (
                    reglas.elegir_accion(zonas, direccion)
                    if fase == "REGLAS" else
                    agente.elegir_accion(estado, epsilon_usado, permitidas)
                )

                accion = ACCIONES[indice]
                if panel_lidar is not None:
                    panel_lidar.mostrar(zonas, fase, episodio, paso, accion)

                # 2. Ejecutar movimiento
                antes, motivo = ejecutar_accion(
                    accion
                )

                # 3. Actualizar simulacion
                avanzar_simulacion()

                despues = posicion.getSFVec3f()

                # 4. Recompensa
                resultado = entorno.evaluar_transicion(
                    antes,
                    despues,
                    motivo
                )

                recompensa = float(
                    resultado["recompensa"]
                )

                if fase != "REGLAS":
                    filtro_antibucle.registrar(indice, antes, despues)

                retorno += recompensa

                # 5. Comprobar terminacion
                terminal = bool(
                    resultado["terminado"]
                    or paso == MAX_ACCIONES
                )

                # 6. Nueva observacion
                if terminal:
                    siguiente_estado = None
                    siguientes_permitidas = None
                else:
                    zonas_siguientes, direccion_siguiente, error_siguiente, distancia_siguiente = observar()
                    lado_siguiente = actualizar_lado(
                        lado_rodeo, indice, zonas, zonas_siguientes
                    )
                    siguiente_estado = codificar_estado(
                        zonas_siguientes, direccion_siguiente,
                        lado_siguiente, distancia_siguiente
                    )
                    siguientes_permitidas = filtro_antibucle.permitidas(
                        zonas_siguientes, error_siguiente
                    )

                # 7. Actualizar Q solamente
                #    durante el entrenamiento
                if fase == "ENTRENAMIENTO":

                    agente.actualizar(
                        estado,
                        indice,
                        recompensa,
                        siguiente_estado,
                        terminal,
                        siguientes_permitidas
                    )

                motivo_terminacion = (
                    motivo or ("META" if resultado["llego_meta"] else
                               "MAX_ACCIONES" if paso == MAX_ACCIONES else "")
                )

                # 8. Registrar transicion
                w_tr.writerow([
                    fase,
                    episodio,
                    paso,
                    estado,
                    *[round(float(v), 5) for v in q_antes],
                    accion,
                    round(recompensa, 5),
                    round(resultado["distancia_actual"], 4),
                    (
                        ""
                        if terminal
                        else siguiente_estado
                    ),
                    int(terminal),
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
                    ";".join(ACCIONES[i] for i in permitidas)
                ])
                if DEPURAR_PASOS:
                    print(
                        f"{fase} E{episodio:03d} P{paso:02d} "
                        f"s={estado} Q={q_antes.round(3).tolist()} "
                        f"a={accion} r={recompensa:.3f} "
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
            # FINAL DEL EPISODIO
            # ==================================

            resumen.append((
                fase,
                episodio,
                paso,
                retorno,
                resultado_final
            ))

            w_ep.writerow([
                fase,
                episodio,
                paso,
                round(retorno, 5),
                resultado_final,
                round(epsilon_usado, 5),
                round(
                    resultado["distancia_actual"],
                    4
                )
            ])

            f_ep.flush()
            f_tr.flush()

            # Reducir exploracion
            if fase == "ENTRENAMIENTO":

                epsilon = max(
                    EPSILON_MINIMO,
                    epsilon * DECAIMIENTO
                )

                if episodio % 10 == 0:
                    np.save(
                        SALIDA / "q_table.npy",
                        agente.q
                    )

            if (
                episodio % 10 == 0
                or episodio == 1
                or resultado_final == "META"
            ):

                print(
                    f"{fase} E{episodio:03d} "
                    f"| {resultado_final} "
                    f"| pasos={paso} "
                    f"| retorno={retorno:.3f} "
                    f"| epsilon={epsilon_usado:.3f}",
                    flush=True
                )

    if POLITICA == "q":
        np.save(SALIDA / "q_table.npy", agente.q)


# ==========================================
# 8. RESUMEN FINAL
# ==========================================

print("\n=== RESUMEN FINAL ===")

for fase, _ in fases:

    registros = [
        r for r in resumen
        if r[0] == fase
    ]
    if not registros:
        continue

    exitos = sum(
        r[4] == "META"
        for r in registros
    )

    colisiones = sum(
        r[4].startswith("COLISION_")
        or r[4] == "FUERA_DEL_TERRENO"
        for r in registros
    )

    retornos = [
        r[3] for r in registros
    ]

    print(
        f"{fase}: "
        f"exito={100 * exitos / len(registros):.1f}% "
        f"| colisiones={colisiones}/{len(registros)} "
        f"| retorno_promedio={np.mean(retornos):.3f}",
        flush=True
    )

print(
    "Valores Q distintos de cero:",
    int(np.count_nonzero(agente.q)),
    flush=True
)

print(
    "Resultados:",
    SALIDA,
    flush=True
)
