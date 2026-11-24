"""Panel del Lidar dentro de la vista 3D de Webots."""

import math
import os

import numpy as np

from movimientos import calcular_movimiento
from percepcion import AVANCES, GIRO, PASO, RADIO_SEGURIDAD


class PanelLidar:

    def __init__(self, display):
        if display is None:
            raise RuntimeError("Falta el dispositivo Display 'lidar_display'")
        self.display = display
        self.cv2 = None
        self.activa = True
        self.cada = max(1, int(os.getenv("UMARS_LIDAR_CADA", "2")))

    @staticmethod
    def _pixel(x, y, centro, escala):
        return (int(centro[0] - y * escala), int(centro[1] - x * escala))

    def _panel(self, imagen, centro, radio_px, alcance, puntos, seguras, elegida):
        cv2 = self.cv2
        escala = radio_px / alcance
        cv2.circle(imagen, centro, radio_px, (65, 65, 65), 1, cv2.LINE_AA)
        for distancia in (0.5, 1.0, 2.0, 3.0, 4.0):
            if distancia < alcance:
                cv2.circle(imagen, centro, int(distancia * escala),
                           (42, 42, 42), 1, cv2.LINE_AA)
        cv2.line(imagen, (centro[0], centro[1] - radio_px),
                 (centro[0], centro[1] + radio_px), (38, 38, 38), 1)
        cv2.line(imagen, (centro[0] - radio_px, centro[1]),
                 (centro[0] + radio_px, centro[1]), (38, 38, 38), 1)

        for x, y in puntos:
            if math.hypot(x, y) > alcance:
                continue
            destino = self._pixel(x, y, centro, escala)
            cv2.line(imagen, centro, destino, (45, 65, 65), 1, cv2.LINE_AA)
            cv2.circle(imagen, destino, 2, (0, 220, 245), -1, cv2.LINE_AA)

        colores = {
            "AVANZAR": (70, 215, 70),
            "AVANZAR_IZQUIERDA": (245, 170, 50),
            "AVANZAR_DERECHA": (210, 100, 245),
        }
        for accion in AVANCES:
            _, _, trayectoria = calcular_movimiento(
                [0.0, 0.0, 0.0], 0.0, accion, PASO, GIRO
            )
            vertices = [centro] + [
                self._pixel(p[0], p[1], centro, escala) for p in trayectoria
            ]
            color = colores[accion] if seguras[accion] else (65, 65, 210)
            cv2.polylines(imagen, [np.array(vertices, dtype=np.int32)],
                          False, color, 4 if accion == elegida else 2,
                          cv2.LINE_AA)

        cv2.circle(imagen, centro, max(2, int(RADIO_SEGURIDAD * escala)),
                   (155, 155, 155), 1, cv2.LINE_AA)
        cv2.circle(imagen, centro, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.line(imagen, centro, (centro[0], centro[1] - 15),
                 (255, 255, 255), 2, cv2.LINE_AA)

    def mostrar(self, zonas, fase, episodio, paso, accion):
        if not self.activa or (paso - 1) % self.cada:
            return
        try:
            if self.cv2 is None:
                import cv2
                self.cv2 = cv2
            cv2 = self.cv2

            puntos = [
                (float(p.x), float(p.y)) for p in zonas["_puntos_lidar"]
                if math.isfinite(p.x) and math.isfinite(p.y)
            ]
            imagen = np.full((560, 980, 3), 20, dtype=np.uint8)
            cv2.putText(imagen, f"{fase} E{episodio:03d} P{paso:03d} | {accion}",
                        (22, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (235, 235, 235), 2, cv2.LINE_AA)
            minimo = zonas["lidar_min_m"]
            texto_min = "sin retorno" if minimo is None else f"{minimo:.2f} m"
            cv2.putText(imagen, f"Punto mas cercano: {texto_min} | 270 grados | frente arriba, izquierda a la izquierda",
                        (22, 59), cv2.FONT_HERSHEY_SIMPLEX, 0.54,
                        (190, 190, 190), 1, cv2.LINE_AA)

            self._panel(imagen, (245, 295), 205, 0.8, puntos,
                        zonas["acciones_seguras"], accion)
            self._panel(imagen, (735, 295), 205, 5.0, puntos,
                        zonas["acciones_seguras"], accion)
            cv2.putText(imagen, "CERCA: 0.8 m", (174, 524),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 210, 210), 1)
            cv2.putText(imagen, "PANORAMA: 5 m", (645, 524),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 210, 210), 1)
            cv2.putText(imagen, "Puntos amarillos: Lidar | verde: recto | naranja: izq | violeta: der | rojo: bloqueado",
                        (110, 548), cv2.FONT_HERSHEY_SIMPLEX, 0.40,
                        (180, 180, 180), 1)
            ancho = self.display.getWidth()
            alto = self.display.getHeight()
            imagen = cv2.resize(imagen, (ancho, alto),
                                interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
            recurso = self.display.imageNew(rgb.tobytes(), self.display.RGB,
                                            ancho, alto)
            self.display.imagePaste(recurso, 0, 0, False)
            self.display.imageDelete(recurso)
        except Exception as exc:
            self.activa = False
            print(f"Panel Lidar desactivado: {exc}", flush=True)
