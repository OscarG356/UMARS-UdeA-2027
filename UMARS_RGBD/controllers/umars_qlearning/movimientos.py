"""Trayectorias discretas del rover en el plano XY de Webots."""

import math


def calcular_movimiento(posicion, rumbo, accion, paso, giro):
    """Devuelve destino, nuevo rumbo y muestras de la trayectoria real."""
    if accion == "GIRAR_IZQUIERDA":
        return list(posicion), rumbo + giro, []
    if accion == "GIRAR_DERECHA":
        return list(posicion), rumbo - giro, []

    cambios = {
        "AVANZAR": 0.0,
        "AVANZAR_IZQUIERDA": giro,
        "AVANZAR_DERECHA": -giro,
    }
    if accion not in cambios:
        raise ValueError(f"Accion desconocida: {accion}")

    cambio = cambios[accion]
    muestras = max(1, math.ceil(paso / 0.025))
    puntos = []
    for i in range(1, muestras + 1):
        fraccion = i / muestras
        if cambio == 0:
            x = posicion[0] + paso * fraccion * math.cos(rumbo)
            y = posicion[1] + paso * fraccion * math.sin(rumbo)
        else:
            radio = paso / cambio
            angulo = rumbo + cambio * fraccion
            x = posicion[0] + radio * (math.sin(angulo) - math.sin(rumbo))
            y = posicion[1] - radio * (math.cos(angulo) - math.cos(rumbo))
        puntos.append([x, y, posicion[2]])

    return puntos[-1], rumbo + cambio, puntos
