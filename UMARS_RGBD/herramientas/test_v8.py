"""Pruebas locales de v8; no requieren iniciar Webots."""

from pathlib import Path
import math
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "umars_v8"))
sys.path.insert(0, str(ROOT / "controllers" / "umars_qlearning"))

from control_v8 import (  # noqa: E402
    NORTE, SUR, RocasV8, costo_giro, parametros_episodio,
    fuera_del_terreno, giro_abre_avance, pose_fraccion, respeta_limites,
    validar_accion_temporal,
)
from movimientos import calcular_movimiento  # noqa: E402


class Campo:
    def __init__(self, valor):
        self.valor = list(valor)

    def getSFVec3f(self):
        return self.valor[:]

    def setSFVec3f(self, valor):
        self.valor = list(valor)


class V8Tests(unittest.TestCase):
    def test_costo_giro_condicional_y_terminos_base(self):
        zonas = {"acciones_seguras": {
            "AVANZAR": False, "AVANZAR_IZQUIERDA": True,
            "AVANZAR_DERECHA": False,
        }}
        self.assertEqual(costo_giro("GIRAR_IZQUIERDA", zonas, .2), -.2)
        self.assertEqual(costo_giro("AVANZAR_IZQUIERDA", zonas, .2), 0)
        zonas["acciones_seguras"]["AVANZAR_IZQUIERDA"] = False
        self.assertEqual(costo_giro("GIRAR_DERECHA", zonas, .2), 0)
        with self.assertRaises(ValueError):
            costo_giro("GIRAR_DERECHA", zonas, -.1)

    def test_pose_fraccion_coincide_con_movimiento_v7(self):
        origen = [-1.5, .2, .15]
        for accion in ("AVANZAR", "GIRAR_IZQUIERDA", "GIRAR_DERECHA",
                       "AVANZAR_IZQUIERDA", "AVANZAR_DERECHA"):
            esperado, rumbo, _ = calcular_movimiento(
                origen, .37, accion, .2, math.pi / 6
            )
            real, angulo = pose_fraccion(origen, .37, accion, 1.0)
            for x, y in zip(real, esperado):
                self.assertAlmostEqual(x, y)
            self.assertAlmostEqual(angulo, rumbo)

    def test_fases_reproducibles_y_velocidades_reservadas(self):
        train = parametros_episodio(True, 42, "ENTRENAMIENTO", 1)
        test = parametros_episodio(True, 42, "EVALUACION", 1)
        reglas = parametros_episodio(True, 42, "REGLAS", 1)
        self.assertEqual(test, parametros_episodio(True, 42, "EVALUACION", 1))
        self.assertEqual((test.fase_norte, test.fase_sur),
                         (reglas.fase_norte, reglas.fase_sur))
        self.assertNotEqual(train.omega_norte, test.omega_norte)
        self.assertNotEqual(train.semilla, test.semilla)

    def test_filtro_borde_rechaza_arco_que_sale_y_regresa(self):
        terreno = (-3, 3, -2, 2)
        radio = .25
        for rumbo, accion in ((math.pi / 12, "AVANZAR_DERECHA"),
                              (11 * math.pi / 12, "AVANZAR_IZQUIERDA")):
            origen = [0, 1.74, .15]
            destino, _ = pose_fraccion(origen, rumbo, accion, 1.0)
            self.assertFalse(fuera_del_terreno(origen, terreno, radio))
            self.assertFalse(fuera_del_terreno(destino, terreno, radio))
            self.assertFalse(respeta_limites(origen, rumbo, accion, terreno, radio))
        self.assertTrue(respeta_limites([0, 1.75, .15], 0, "GIRAR_DERECHA", terreno, radio))
        self.assertFalse(respeta_limites([0, 1.750001, .15], 0, "GIRAR_DERECHA", terreno, radio))

    def test_rescate_borde_102061_abre_avance_al_girar_derecha(self):
        terreno = (-3, 3, -2, 2)
        origen = (0.5558873375664568, 1.7160759320236556, .15)
        rumbo = math.pi / 6
        self.assertFalse(giro_abre_avance(origen, rumbo, "GIRAR_IZQUIERDA", terreno, .25))
        self.assertTrue(giro_abre_avance(origen, rumbo, "GIRAR_DERECHA", terreno, .25))

    def test_rectangulos_y_campos_sincronizados(self):
        entorno = SimpleNamespace(obstaculos=[
            ("roca_central", (-.1, .1, -.1, .1)),
            (NORTE, (.4, .8, .8, 1.2)),
            (SUR, (1.0, 1.6, -1.05, -.55)),
        ])
        campos = {NORTE: Campo([.6, 1, .17]), SUR: Campo([1.3, -.8, .2])}
        rocas = RocasV8(entorno, campos)
        rocas.configurar(parametros_episodio(True, 42, "ENTRENAMIENTO", 1))
        rocas.actualizar(3.0)
        posiciones = rocas.posiciones(3.0)
        for nombre in (NORTE, SUR):
            self.assertAlmostEqual(campos[nombre].valor[0], posiciones[nombre][0])
            self.assertAlmostEqual(campos[nombre].valor[1], posiciones[nombre][1])
            caja = dict(entorno.obstaculos)[nombre]
            self.assertAlmostEqual((caja[0] + caja[1]) / 2, posiciones[nombre][0])

    def test_colision_temporal_entre_extremos_libres(self):
        # Roca cruza por el rover en medio de un giro sin desplazarlo.
        class Cruce:
            def rectangulos(self, t):
                x = -.8 + 1.6 * t
                return [("movil", (x - .05, x + .05, -.05, .05))]

        permitido, motivo, fraccion = validar_accion_temporal(
            [0, 0, .15], 0, "GIRAR_IZQUIERDA", 0, 1,
            Cruce(), (-3, 3, -2, 2), muestras=20,
        )
        self.assertFalse(permitido)
        self.assertEqual(motivo, "COLISION_movil")
        self.assertGreater(fraccion, 0)
        self.assertLess(fraccion, 1)

    def test_cruce_de_rover_y_roca_en_movimiento(self):
        class Cruce:
            def rectangulos(self, t):
                y = -0.5 + t
                return [("movil", (.08, .12, y - .05, y + .05))]

        permitido, motivo, fraccion = validar_accion_temporal(
            [0, 0, .15], 0, "AVANZAR", 0, 1,
            Cruce(), (-3, 3, -2, 2), muestras=40,
        )
        self.assertFalse(permitido)
        self.assertEqual(motivo, "COLISION_movil")
        self.assertGreater(fraccion, 0)
        self.assertLess(fraccion, 1)

    def test_mundos_preservan_paneles_y_v7(self):
        for nombre in ("marte_v8_estatico", "marte_v8_dinamico"):
            mundo = (ROOT / "worlds" / f"{nombre}.wbt").read_text(encoding="utf-8")
            proyecto = (ROOT / "worlds" / f".{nombre}.wbproj").read_text(encoding="utf-8")
            self.assertIn('controller "umars_v8"', mundo)
            for dispositivo in ("rgb", "depth", "lidar_seguridad", "lidar_display"):
                self.assertIn(f'name "{dispositivo}"', mundo)
            for panel in ("rgb", "depth", "lidar_display"):
                self.assertIn(f"UMARS_rover_Q:{panel};1;", proyecto)
        original = (ROOT / "worlds" / "marte_qlearning.wbt").read_text(encoding="utf-8")
        self.assertIn('controller "umars_qlearning"', original)


if __name__ == "__main__":
    unittest.main()
