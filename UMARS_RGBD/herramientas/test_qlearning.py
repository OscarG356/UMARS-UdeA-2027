"""Pruebas locales de la logica de navegacion; no requieren Webots."""

from pathlib import Path
import math
import sys
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controllers" / "umars_qlearning"))

from agente_q import (
    AgenteQ, ACCIONES, NUM_ESTADOS, FiltroAntibucle, codificar_estado,
    acciones_permitidas, actualizar_lado,
)
from entorno import EntornoUMARS
from movimientos import calcular_movimiento
from percepcion import analizar_regiones, fusionar_avances_lidar
from politica_reglas import PoliticaReglas
from visualizar_lidar import PanelLidar


class NavegacionTests(unittest.TestCase):
    def test_144_estados(self):
        estados = set()
        for bits in range(8):
            zonas = {
                nombre: {"estado": "OCUPADO" if bits & mascara else "LIBRE"}
                for nombre, mascara in (("izquierda", 4), ("centro", 2), ("derecha", 1))
            }
            for direccion in (-1, 0, 1):
                for lado in (0, 1, 2):
                    for distancia in (3.0, 2.0):
                        estados.add(codificar_estado(zonas, direccion, lado, distancia))
        self.assertEqual(estados, set(range(NUM_ESTADOS)))

    def test_profundidad_y_veto_de_avance(self):
        imagen = np.full((120, 160), np.inf)
        libre = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertTrue(libre["avance_seguro"])
        self.assertEqual(libre["centro"]["estado"], "LIBRE")

        # Un obstaculo estrecho puede quedar diluido en el percentil 20.
        imagen[50:55, 100:105] = 0.2
        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertFalse(zonas["avance_seguro"])
        self.assertEqual(zonas["centro"]["estado"], "LIBRE")

    def test_avances_segun_trayectoria_y_obstaculo_lateral(self):
        imagen = np.full((120, 160), np.inf)
        imagen[50:55, 0:3] = 0.258
        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertLess(zonas["distancia_avance_m"], 0.35)
        self.assertEqual(
            zonas["acciones_seguras"],
            {"AVANZAR": True, "AVANZAR_IZQUIERDA": True,
             "AVANZAR_DERECHA": True},
        )

        imagen[50:55, 0:3] = 0.15
        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertEqual(acciones_permitidas(zonas), (0, 1, 2, 4))
        self.assertFalse(zonas["acciones_seguras"]["AVANZAR_IZQUIERDA"])

        imagen[:] = np.inf
        imagen[50:55, 157:160] = 0.15
        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertEqual(acciones_permitidas(zonas), (0, 1, 2, 3))

        imagen[:] = np.nan
        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertEqual(acciones_permitidas(zonas), (1, 2))

    def test_lidar_detecta_piedra_en_punto_ciego_lateral(self):
        imagen = np.full((120, 160), np.inf)
        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        self.assertEqual(acciones_permitidas(zonas), tuple(range(5)))
        punto = SimpleNamespace(x=0.164, y=-0.232, z=0.0)
        fusionar_avances_lidar(zonas, [punto])
        self.assertEqual(
            zonas["acciones_seguras_lidar"],
            {"AVANZAR": False, "AVANZAR_IZQUIERDA": False,
             "AVANZAR_DERECHA": False},
        )
        self.assertEqual(acciones_permitidas(zonas), (1, 2))
        self.assertAlmostEqual(zonas["lidar_min_m"], math.hypot(0.164, -0.232))

        zonas = analizar_regiones(imagen.ravel(), 160, 120)
        fusionar_avances_lidar(
            zonas, [SimpleNamespace(x=0.19, y=-0.26, z=0.0)]
        )
        self.assertEqual(acciones_permitidas(zonas), (1, 2, 3))

    def test_panel_lidar_escribe_en_display_de_webots(self):
        class DisplaySimulado:
            RGB = 3

            def getWidth(self):
                return 640

            def getHeight(self):
                return 360

            def imageNew(self, datos, formato, ancho, alto):
                self.imagen = (datos, formato, ancho, alto)
                return 7

            def imagePaste(self, imagen, x, y, mezclar):
                self.pegado = (imagen, x, y, mezclar)

            def imageDelete(self, imagen):
                self.borrado = imagen

        display = DisplaySimulado()
        panel = PanelLidar(display)
        zonas = {
            "_puntos_lidar": [SimpleNamespace(x=0.3, y=0.1, z=0.0)],
            "lidar_min_m": math.hypot(0.3, 0.1),
            "acciones_seguras": {
                "AVANZAR": False,
                "AVANZAR_IZQUIERDA": True,
                "AVANZAR_DERECHA": False,
            },
        }
        panel.mostrar(zonas, "EVALUACION", 1, 1, "GIRAR_IZQUIERDA")
        self.assertTrue(panel.activa)
        self.assertEqual(display.imagen[1:], (3, 640, 360))
        self.assertEqual(len(display.imagen[0]), 640 * 360 * 3)
        self.assertEqual(display.pegado, (7, 0, 0, False))
        self.assertEqual(display.borrado, 7)

    def test_epsilon_y_actualizacion(self):
        agente = AgenteQ(alpha=0.1, gamma=0.95, semilla=42)
        agente.q[1] = [5.0, 2.0, 1.0, 0.0, 0.0]
        self.assertEqual(agente.q.shape, (NUM_ESTADOS, 5))
        self.assertEqual([agente.elegir_accion(1, 0.0) for _ in range(20)], [0] * 20)
        self.assertEqual(agente.elegir_accion(1, 0.0, (1, 2)), 1)
        self.assertEqual(set(agente.elegir_accion(1, 1.0) for _ in range(100)), set(range(5)))

        agente.q[2] = [100.0, 4.0, 3.0, 2.0, 1.0]
        agente.actualizar(1, 1, -1.0, 2, False, (1, 2))
        self.assertAlmostEqual(agente.q[1, 1], 2.0 + 0.1 * (-1.0 + 0.95 * 4.0 - 2.0))
        agente.actualizar(1, 2, -50.0, None, True)
        self.assertAlmostEqual(agente.q[1, 2], 1.0 + 0.1 * (-50.0 - 1.0))

    def test_permite_elegir_giro_si_avance_sigue_bloqueado(self):
        zonas = {"avance_seguro": False}
        self.assertEqual(acciones_permitidas(zonas), (1, 2))
        self.assertEqual(acciones_permitidas(zonas, error_meta=0), (1, 2))
        zonas["avance_seguro"] = True
        self.assertEqual(acciones_permitidas(zonas), tuple(range(5)))

    def test_antibucle_mantiene_giro_hasta_hallar_avance(self):
        filtro = FiltroAntibucle()
        origen = [0.0, 0.0, 0.15]
        bloqueado = {
            "avance_seguro": False,
            "acciones_seguras": {
                "AVANZAR": False,
                "AVANZAR_IZQUIERDA": False,
                "AVANZAR_DERECHA": False,
            },
        }
        ajuste = FiltroAntibucle()
        ajuste.registrar(1, origen, origen)
        ajuste.registrar(2, origen, origen)
        self.assertEqual(ajuste.permitidas(bloqueado), (1, 2))
        self.assertEqual(filtro.permitidas(bloqueado), (1, 2))
        filtro.registrar(2, origen, origen)
        self.assertEqual(filtro.permitidas(bloqueado), (1, 2))
        filtro.registrar(2, origen, origen)
        filtro.registrar(1, origen, origen)
        self.assertEqual(filtro.permitidas(bloqueado), (1,))
        agente = AgenteQ(semilla=42)
        agente.q[71, 1] = -6.2749
        agente.q[71, 2] = -5.5691
        self.assertEqual(agente.elegir_accion(71, 0.0, (1, 2)), 2)
        self.assertEqual(
            agente.elegir_accion(71, 0.0, filtro.permitidas(bloqueado)), 1
        )

        salida = {
            "avance_seguro": False,
            "acciones_seguras": dict(
                bloqueado["acciones_seguras"], AVANZAR_IZQUIERDA=True
            ),
        }
        self.assertEqual(filtro.permitidas(salida), (3,))
        filtro.registrar(3, origen, [0.18, 0.05, 0.15])
        self.assertEqual(filtro.permitidas(bloqueado), (1, 2))

        filtro.registrar(1, origen, origen)
        filtro.registrar(1, origen, origen)
        filtro.registrar(2, origen, origen)
        self.assertEqual(filtro.permitidas(bloqueado), (2,))

    def test_lado_de_rodeo_persiste_hasta_dejar_atras_obstaculo(self):
        antes = {
            "centro": {"estado": "OCUPADO"},
            "derecha": {"estado": "LIBRE"},
            "izquierda": {"estado": "LIBRE"},
        }
        al_costado = {
            "centro": {"estado": "LIBRE"},
            "derecha": {"estado": "OCUPADO"},
            "izquierda": {"estado": "LIBRE"},
        }
        despejado = {
            "centro": {"estado": "LIBRE"},
            "derecha": {"estado": "LIBRE"},
            "izquierda": {"estado": "LIBRE"},
        }
        self.assertEqual(actualizar_lado(0, 1, antes, al_costado), 1)
        antes_centro_libre = dict(al_costado, avance_seguro=False)
        self.assertEqual(actualizar_lado(0, 1, antes_centro_libre, al_costado), 1)
        self.assertEqual(actualizar_lado(1, 0, al_costado, al_costado), 1)
        self.assertEqual(actualizar_lado(1, 0, al_costado, despejado), 0)
        self.assertNotEqual(
            codificar_estado(al_costado, 1, 1, 2.6),
            codificar_estado(al_costado, 1, 0, 2.6),
        )
        self.assertNotEqual(
            codificar_estado(al_costado, 1, 1, 2.6),
            codificar_estado(al_costado, 1, 1, 2.4),
        )

    def test_meta_detras_obliga_a_orientar(self):
        zonas = {"avance_seguro": True}
        self.assertEqual(acciones_permitidas(zonas, error_meta=math.radians(170)), (1,))
        self.assertEqual(acciones_permitidas(zonas, error_meta=math.radians(-170)), (2,))
        self.assertEqual(acciones_permitidas(zonas, error_meta=math.radians(45)), tuple(range(5)))

    def test_arcos_y_seleccion_hacia_meta(self):
        zonas = {
            "avance_seguro": True,
            "izquierda": {"estado": "LIBRE"},
            "centro": {"estado": "LIBRE"},
            "derecha": {"estado": "LIBRE"},
        }
        self.assertEqual(acciones_permitidas(zonas, error_meta=math.radians(80)), (3, 1))
        self.assertEqual(acciones_permitidas(zonas, error_meta=math.radians(-80)), (4, 2))

        origen = [0.0, 0.0, 0.15]
        izquierda, rumbo_izq, puntos = calcular_movimiento(
            origen, 0.0, ACCIONES[3], 0.2, math.pi / 6
        )
        derecha, rumbo_der, _ = calcular_movimiento(
            origen, 0.0, ACCIONES[4], 0.2, math.pi / 6
        )
        self.assertAlmostEqual(rumbo_izq, math.pi / 6)
        self.assertAlmostEqual(rumbo_der, -math.pi / 6)
        self.assertGreater(izquierda[1], 0)
        self.assertLess(derecha[1], 0)
        self.assertEqual(len(puntos), 8)

        entorno = EntornoUMARS.__new__(EntornoUMARS)
        entorno.radio_rover = 0.005
        entorno.limites = (-3, 3, -2, 2)
        x, y, _ = puntos[3]
        entorno.obstaculos = [("roca", (x - 0.001, x + 0.001, y - 0.001, y + 0.001))]
        self.assertEqual(entorno.validar_trayectoria(puntos), (False, "COLISION_roca"))

    def test_reglas_usa_las_mismas_acciones(self):
        zonas = {
            "izquierda": {"estado": "LIBRE", "distancia_m": 5.0},
            "centro": {"estado": "OCUPADO", "distancia_m": 0.4},
            "derecha": {"estado": "OCUPADO", "distancia_m": 0.3},
            "avance_seguro": True,
        }
        reglas = PoliticaReglas()
        self.assertEqual(reglas.elegir_accion(zonas, 0), 1)
        zonas["centro"]["estado"] = "LIBRE"
        self.assertEqual(reglas.elegir_accion(zonas, 0), 0)
        zonas["derecha"]["estado"] = "LIBRE"
        self.assertEqual(PoliticaReglas().elegir_accion(zonas, -1), 3)
        self.assertEqual(PoliticaReglas().elegir_accion(zonas, 1), 4)
        zonas["acciones_seguras"] = {
            "AVANZAR": True,
            "AVANZAR_IZQUIERDA": False,
            "AVANZAR_DERECHA": True,
        }
        self.assertEqual(PoliticaReglas().elegir_accion(zonas, -1), 0)

    def test_colision_del_trayecto_no_salta_obstaculo(self):
        entorno = EntornoUMARS.__new__(EntornoUMARS)
        entorno.radio_rover = 0.25
        entorno.limites = (-3, 3, -2, 2)
        entorno.obstaculos = [("roca", (-0.125, 0.325, -0.275, 0.275))]
        permitido, motivo = entorno.validar_avance([-0.5, 0, 0.15], [-0.3, 0, 0.15])
        self.assertFalse(permitido)
        self.assertEqual(motivo, "COLISION_roca")

    def test_recompensa_usa_distancia_despues_del_movimiento(self):
        class Meta:
            def getSFVec3f(self):
                return [2.0, 0.0, 0.01]

        entorno = EntornoUMARS.__new__(EntornoUMARS)
        entorno.campo_meta = Meta()
        entorno.radio_meta = 0.35
        resultado = entorno.evaluar_transicion([0.0, 0.0, 0.15], [0.2, 0.0, 0.15])
        self.assertAlmostEqual(resultado["progreso"], 0.2)
        self.assertAlmostEqual(resultado["recompensa"], -0.6)
        self.assertFalse(resultado["terminado"])

        choque = entorno.evaluar_transicion(
            [0.2, 0.0, 0.15], [0.2, 0.0, 0.15], "COLISION_roca"
        )
        self.assertEqual(choque["recompensa"], -51.0)
        self.assertTrue(choque["terminado"])


if __name__ == "__main__":
    unittest.main()
