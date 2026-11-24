
import math
import numpy as np

from movimientos import calcular_movimiento

UMBRAL = 1.50
ALCANCE_MAXIMO = 5.0
MOSTRAR_DIAGNOSTICO = False

REGIONES = {
    "izquierda": (0.00, 0.40),
    "centro": (0.30, 0.70),
    "derecha": (0.60, 1.00),
}

# Configuracion del RangeFinder en los mundos de navegacion.
CAMPO_VISUAL = 2.1
SENSOR_X = 0.19
PASO = 0.20
GIRO = math.pi / 6
RADIO_SEGURIDAD = 0.27  # radio geometrico 0.25 m + margen 0.02 m
AVANCES = ("AVANZAR", "AVANZAR_IZQUIERDA", "AVANZAR_DERECHA")


def _avances_seguros(franja, width):
    """Contrasta puntos RGB-D con el barrido del chasis de cada avance."""
    lectura = np.where(np.isposinf(franja), ALCANCE_MAXIMO, franja)
    validos = np.isfinite(lectura) & (lectura > 0)
    if np.count_nonzero(validos) < 0.10 * lectura.size:
        return {accion: False for accion in AVANCES}

    distancias = lectura[validos]
    columnas = np.broadcast_to(np.arange(width), lectura.shape)[validos]
    # Webots devuelve profundidad axial; la imagen planar usa una proyeccion
    # de perspectiva. +Y queda a la izquierda del rover.
    lateral = (
        1 - 2 * (columnas + 0.5) / width
    ) * math.tan(CAMPO_VISUAL / 2) * distancias
    x = SENSOR_X + distancias
    return _seguridad_puntos(x, lateral)


def _seguridad_puntos(x, lateral):
    """Evalua los mismos tres barridos con puntos del sensor disponible."""
    radio_cuadrado = RADIO_SEGURIDAD ** 2

    seguras = {}
    for accion in AVANCES:
        _, _, trayectoria = calcular_movimiento(
            [0.0, 0.0, 0.0], 0.0, accion, PASO, GIRO
        )
        seguras[accion] = all(
            not np.any((x - punto[0]) ** 2 + (lateral - punto[1]) ** 2
                       <= radio_cuadrado)
            for punto in trayectoria
        )
    return seguras


def fusionar_avances_lidar(zonas, puntos):
    """Completa la seguridad RGB-D con puntos laterales del Lidar."""
    if puntos is None or len(puntos) == 0:
        raise RuntimeError("El Lidar no entrego una nube de puntos")

    xy = np.array([(p.x, p.y) for p in puntos], dtype=float)
    distancias = np.hypot(xy[:, 0], xy[:, 1])
    validos = np.isfinite(distancias) & (distancias > 0)
    zonas["lidar_min_m"] = (
        float(np.min(distancias[validos])) if np.any(validos) else None
    )
    seguras_lidar = _seguridad_puntos(xy[validos, 0], xy[validos, 1])
    zonas["acciones_seguras_lidar"] = seguras_lidar
    zonas["acciones_seguras"] = {
        accion: zonas["acciones_seguras"][accion] and seguras_lidar[accion]
        for accion in AVANCES
    }
    zonas["avance_seguro"] = zonas["acciones_seguras"]["AVANZAR"]
    return zonas


def analizar_regiones(datos, width, height):

    profundidad = np.asarray(
        datos, dtype=float
    ).reshape(height, width)

    y0 = int(0.38 * height)
    y1 = int(0.58 * height)

    estado = {}

    for nombre, (inicio, fin) in REGIONES.items():

        x0 = int(inicio * width)
        x1 = int(fin * width)

        zona = profundidad[y0:y1, x0:x1]

        sin_retorno = np.isposinf(zona)

        zona_procesada = zona.copy()
        zona_procesada[sin_retorno] = ALCANCE_MAXIMO

        validos = zona_procesada[
            np.isfinite(zona_procesada)
            & (zona_procesada > 0)
        ]

        porcentaje = float(
            100 * np.mean(sin_retorno)
        )

        if MOSTRAR_DIAGNOSTICO:
            print(
                f"{nombre}: "
                f"sin retorno = {porcentaje:.1f}%"
            )

        if validos.size < 0.10 * zona.size:
            estado[nombre] = {
                "distancia_m": None,
                "estado": "DESCONOCIDO",
                "sin_retorno_pct": round(porcentaje, 1)
            }
            continue

        distancia = float(
            np.percentile(validos, 20)
        )

        estado[nombre] = {
            "distancia_m": round(distancia, 3),
            "estado": (
                "OCUPADO"
                if distancia < UMBRAL
                else "LIBRE"
            ),
            "sin_retorno_pct": round(porcentaje, 1)
        }

    franja = profundidad[y0:y1, :]
    franja_medible = np.where(np.isposinf(franja), ALCANCE_MAXIMO, franja)
    cercanos = franja_medible[np.isfinite(franja_medible) & (franja_medible > 0)]
    estado["distancia_avance_m"] = (
        float(np.min(cercanos)) if cercanos.size else None
    )
    estado["acciones_seguras"] = _avances_seguros(franja, width)
    estado["avance_seguro"] = estado["acciones_seguras"]["AVANZAR"]

    return estado


def politica_heuristica(estado):

    if estado["centro"]["estado"] == "LIBRE":
        return "AVANZAR"

    if estado["centro"]["estado"] == "DESCONOCIDO":
        return "DETENERSE"

    opciones = [
        (
            nombre,
            estado[nombre]["distancia_m"]
        )
        for nombre in ["izquierda", "derecha"]
        if estado[nombre]["estado"] == "LIBRE"
    ]

    if not opciones:
        return "DETENERSE"

    mejor = max(
        opciones,
        key=lambda item: item[1]
    )[0]

    return (
        "GIRAR_IZQUIERDA"
        if mejor == "izquierda"
        else "GIRAR_DERECHA"
    )
