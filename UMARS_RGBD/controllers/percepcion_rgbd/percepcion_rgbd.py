"""Controlador inicial de percepción RGB-D para Webots R2025a.

Este primer hito NO entrena Q-learning ni mueve ruedas: obtiene profundidad,
clasifica tres regiones y registra evidencia para un análisis posterior.
Solo necesita la biblioteca estándar de Python y la API 'controller' de Webots.
"""
from controller import Robot
from pathlib import Path
import csv
import math
import numpy as np
import cv2

robot = Robot()
step_ms = int(robot.getBasicTimeStep())
rgb = robot.getDevice('rgb')
depth = robot.getDevice('depth')
rgb.enable(step_ms)
depth.enable(step_ms)

threshold_m = 1.50
output = Path(__file__).resolve().parents[2] / 'capturas'
output.mkdir(parents=True, exist_ok=True)



def analizar_regiones(datos, width, height):

    # Regiones de interés de la imagen de profundidad
    regiones = {
        "izquierda": (0.05, 0.27),
        "centro": (0.40, 0.60),
        "derecha": (0.73, 0.95)
    }

    y_inicio = int(0.38 * height)
    y_fin = int(0.58 * height)

    estado = {}

    for nombre, (x_inicio, x_fin) in regiones.items():

        x0 = int(x_inicio * width)
        x1 = int(x_fin * width)

        valores = []

        for y in range(y_inicio, y_fin):
            for x in range(x0, x1):

                d = float(datos[y * width + x])

                if math.isfinite(d) and d > 0:
                    valores.append(d)

        pixeles_totales = (y_fin - y_inicio) * (x1 - x0)

        if len(valores) < 0.1 * pixeles_totales:
            estado[nombre] = {
                "distancia_m": None,
                "estado": "DESCONOCIDO"
            }
            continue

        valores.sort()
        indice = int(0.20 * (len(valores) - 1))
        distancia = valores[indice]

        estado[nombre] = {
            "distancia_m": round(distancia, 3),
            "estado": (
                "OCUPADO"
                if distancia < threshold_m
                else "LIBRE"
            )
        }

    return estado


def heuristica(estado):

    if estado["centro"]["estado"] == "LIBRE":
        return "AVANZAR"

    candidatos = []

    for nombre in ["izquierda", "derecha"]:

        if estado[nombre]["estado"] == "LIBRE":

            distancia = estado[nombre]["distancia_m"]

            candidatos.append((nombre, distancia))

    if not candidatos:
        return "DETENERSE / REVISAR"

    mejor_region = max(
        candidatos,
        key=lambda x: x[1]
    )[0]

    if mejor_region == "izquierda":
        return "GIRAR IZQUIERDA"

    return "GIRAR DERECHA"


contador = 0
captura_guardada = False
print('UMARS: controlador RGB-D iniciado. Esperando imagenes ...')
while robot.step(step_ms) != -1:
    contador += 1
    if contador % 12 != 0 and captura_guardada:
        continue
    lectura = depth.getRangeImage()
    if lectura is None:
        continue
    w, h = depth.getWidth(), depth.getHeight()
    zonas = analizar_regiones(lectura, w, h)
    if contador % 12 == 0:
        print('UMARS zonas:', zonas, '|', heuristica(zonas), flush=True)
    if not captura_guardada and contador >= 15:
        try:
            ruta_rgb = output / 'rgb.png'
            ruta_depth = output / 'depth.csv'
            # Webots entrega cada pixel como BGRA (4 bytes).
            # Guardamos con Python para admitir rutas Unicode en Windows.
            raw = rgb.getImage()
            rgb_w, rgb_h = rgb.getWidth(), rgb.getHeight()
            if raw is None or len(raw) != rgb_w * rgb_h * 4:
                raise RuntimeError('No se obtuvo una imagen RGB valida.')
            imagen_bgra = np.frombuffer(raw, dtype=np.uint8).reshape(rgb_h, rgb_w, 4)
            imagen_bgr = cv2.cvtColor(imagen_bgra, cv2.COLOR_BGRA2BGR)
            ok, png_bytes = cv2.imencode('.png', imagen_bgr)
            if not ok:
                raise RuntimeError('OpenCV no pudo codificar la imagen PNG.')
            ruta_rgb.write_bytes(png_bytes.tobytes())
            if not ruta_rgb.is_file() or ruta_rgb.stat().st_size == 0:
                raise RuntimeError('rgb.png no pudo guardarse.')
            with ruta_depth.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['width', w, 'height', h])
                for fila in range(h):
                    writer.writerow(lectura[fila * w:(fila + 1) * w])
            captura_guardada = True
            print('UMARS: RGB guardado:', ruta_rgb, f'({ruta_rgb.stat().st_size} bytes)', flush=True)
            print('UMARS: profundidad guardada:', ruta_depth, flush=True)
        except Exception as exc:
            print('UMARS: error guardando capturas:', repr(exc), flush=True)
            # Intentara guardar de nuevo en una iteracion posterior.
