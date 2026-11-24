"""Prueba del ciclo completo del controlador con Webots simulado en memoria."""

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import csv
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class Campo:
    def __init__(self, valor):
        self.valor = valor

    def getSFVec3f(self):
        return list(self.valor)

    def setSFVec3f(self, valor):
        self.valor = list(valor)

    def getSFString(self):
        return self.valor

    def getSFNode(self):
        return self.valor

    def setSFRotation(self, valor):
        self.valor = list(valor)

    def getCount(self):
        return len(self.valor)

    def getMFNode(self, i):
        return self.valor[i]


class Nodo:
    def __init__(self, **campos):
        self.campos = {nombre: Campo(valor) for nombre, valor in campos.items()}

    def getField(self, nombre):
        return self.campos.get(nombre)


class SupervisorFalso:
    def __init__(self, dinamico):
        def solido(nombre, pos, tam):
            return Nodo(name=nombre, translation=pos,
                        boundingObject=Nodo(size=tam))

        norte = solido("piedra_lateral_izquierda", [.6, 1, .17], [.38, .48, .34])
        sur = solido("piedra_lateral_derecha", [1.3, -.8, .2], [.6, .5, .4])
        self.raiz = Nodo(children=[
            solido("terreno_marciano_simplificado", [0, 0, 0], [6, 4, .12]),
            solido("roca_central", [.1, 0, .25], [.45, .55, .5]),
            norte, sur,
        ])
        self.meta = Nodo(translation=[2.2, .75, .01])
        self.rover = Nodo(translation=[-1.5, 0, .15], rotation=[0, 0, 1, 0])
        self.norte = norte if dinamico else None
        self.sur = sur if dinamico else None
        self.depth = SimpleNamespace(
            enable=lambda _: None, getRangeImage=lambda: [float("inf")] * (160 * 120),
            getWidth=lambda: 160, getHeight=lambda: 120,
        )
        self.lidar = SimpleNamespace(
            enable=lambda _: None, enablePointCloud=lambda: None,
            getPointCloud=lambda: [SimpleNamespace(x=4.0, y=0.0)],
        )
        self.rgb = SimpleNamespace(enable=lambda _: None)

    def getBasicTimeStep(self):
        return 32

    def getDevice(self, nombre):
        return {"depth": self.depth, "lidar_seguridad": self.lidar,
                "rgb": self.rgb, "lidar_display": object()}[nombre]

    def getRoot(self):
        return self.raiz

    def getFromDef(self, nombre):
        return {"UMARS_META": self.meta,
                "UMARS_ROCA_MOVIL_NORTE": self.norte,
                "UMARS_ROCA_MOVIL_SUR": self.sur}.get(nombre)

    def getSelf(self):
        return self.rover

    def step(self, _):
        return 0


class ControladorV8Tests(unittest.TestCase):
    def test_entrenamiento_evaluacion_y_rocas_con_webots_simulado(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            copia = base / "controllers"
            shutil.copytree(ROOT / "controllers" / "umars_qlearning",
                            copia / "umars_qlearning",
                            ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(ROOT / "controllers" / "umars_v8",
                            copia / "umars_v8",
                            ignore=shutil.ignore_patterns("__pycache__"))
            tabla_v7 = (base / "resultados" /
                        "diagnostico_ql_meta_lejana_v7_max120" / "q_table.npy")
            tabla_v7.parent.mkdir(parents=True)
            shutil.copy2(ROOT / "resultados" /
                         "diagnostico_ql_meta_lejana_v7_max120" / "q_table.npy",
                         tabla_v7)
            controlador = copia / "umars_v8" / "umars_v8.py"
            mod_control = ModuleType("controller")
            mod_panel = ModuleType("visualizar_lidar")
            mod_panel.PanelLidar = lambda _: SimpleNamespace(mostrar=lambda *args: None)
            entorno = {"UMARS_ENTRENAMIENTO": "1", "UMARS_EVALUACION": "1",
                       "UMARS_MAX_ACCIONES": "2", "UMARS_V8_POLITICA": "q",
                       "UMARS_V8_PENALIZACION_GIRO": "0.2"}
            for dinamico, experimento, politica, penalizacion in (
                (False, "A", "q", "0"),
                (False, "B", "q", "0.2"),
                (True, "C", "q", "0"),
                (True, "D", "q", "0.2"),
                (True, "C", "reglas", "0"),
            ):
                robot = SupervisorFalso(dinamico)
                mod_control.Supervisor = lambda: robot
                entorno["UMARS_V8_POLITICA"] = politica
                entorno["UMARS_V8_PENALIZACION_GIRO"] = penalizacion
                with patch.dict(sys.modules, {
                    "controller": mod_control, "visualizar_lidar": mod_panel,
                }), patch.dict(os.environ, entorno), patch.object(
                    sys, "path", [str(copia / "umars_v8"), *sys.path]
                ):
                    spec = importlib.util.spec_from_file_location(
                        f"prueba_v8_{experimento}", controlador
                    )
                    modulo = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(modulo)
                carpeta = sorted((base / "resultados" / "experimentos_v8" /
                                  experimento).glob(f"{politica}_*"))[-1]
                with (carpeta / "episodios.csv").open(newline="", encoding="utf-8") as f:
                    filas = list(csv.DictReader(f))
                if politica == "q":
                    self.assertEqual([f["fase"] for f in filas],
                                     ["EVALUACION"] if experimento == "A" else
                                     ["ENTRENAMIENTO", "EVALUACION"])
                    self.assertEqual(float(filas[-1]["epsilon"]), 0)
                    self.assertEqual(np.load(carpeta / "q_table.npy").shape, (144, 5))
                    # La tabla guardada al acabar entrenamiento debe ser idéntica
                    # a la tabla del controlador después de la evaluación.
                    np.testing.assert_array_equal(
                        np.load(carpeta / "q_table.npy"), modulo.AGENTE.q
                    )
                else:
                    self.assertEqual([f["fase"] for f in filas], ["REGLAS"])
                    self.assertEqual(float(filas[0]["epsilon"]), 0)
                if dinamico:
                    self.assertNotEqual(robot.norte.getField("translation").getSFVec3f()[0], .6)

            robot = SupervisorFalso(True)
            mod_control.Supervisor = lambda: robot
            tabla = base / "congelada.npy"
            np.save(tabla, np.ones((144, 5)))
            originales = tabla.read_bytes()
            entorno.update(UMARS_V8_POLITICA="q", UMARS_V8_PENALIZACION_GIRO="0.2",
                           UMARS_V8_TABLA_CONGELADA=str(tabla))
            for variante in ("original", "corregido", "entrenar"):
                entrenar = variante == "entrenar"
                entorno["UMARS_V8_PRUEBA_BORDE"] = "corregido" if entrenar else variante
                if entrenar:
                    entorno.update(UMARS_V8_ESTUDIO_BORDE="entrenar",
                                   UMARS_V8_SEMILLA_EVALUACION="200042")
                with patch.dict(sys.modules, {
                    "controller": mod_control, "visualizar_lidar": mod_panel,
                }), patch.dict(os.environ, entorno), patch.object(
                    sys, "path", [str(copia / "umars_v8"), *sys.path]
                ):
                    spec = importlib.util.spec_from_file_location(f"prueba_{variante}", controlador)
                    modulo = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(modulo)
                self.assertFalse(modulo.AGENTE.q.flags.writeable)
                with (modulo.SALIDA / "episodios.csv").open(newline="", encoding="utf-8") as f:
                    filas = list(csv.DictReader(f))
                if entrenar:
                    self.assertEqual([f["fase"] for f in filas], ["ENTRENAMIENTO", "EVALUACION"])
                    self.assertEqual(filas[-1]["semilla_escenario"], "300043")
                    self.assertEqual(modulo.SALIDA.parent.parent.name, "entrenar")
                    np.testing.assert_array_equal(modulo.AGENTE.q, np.load(modulo.SALIDA / "q_table.npy"))
                    with (modulo.SALIDA / "transiciones.csv").open(newline="", encoding="utf-8") as f:
                        pasos = list(csv.DictReader(f))
                    self.assertTrue(all(float(v) == 0 for k, v in pasos[0].items() if k.startswith("q_")))
                    self.assertTrue(pasos[0]["acciones_permitidas_siguiente"])
                else:
                    np.testing.assert_array_equal(modulo.AGENTE.q, np.ones((144, 5)))
                    self.assertEqual([(f["fase"], float(f["epsilon"])) for f in filas],
                                     [("EVALUACION", 0.0)])
                    self.assertEqual(modulo.SALIDA.parent.name, variante)
                self.assertEqual(float(filas[-1]["epsilon"]), 0)
                self.assertEqual(tabla.read_bytes(), originales)

            spec = importlib.util.spec_from_file_location(
                "resumen_v8_prueba", ROOT / "herramientas" / "resumir_v8.py"
            )
            modulo_resumen = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo_resumen)
            modulo_resumen.BASE = base / "resultados" / "experimentos_v8"
            modulo_resumen.escribir()
            self.assertTrue((modulo_resumen.BASE / "resumen_corridas.csv").exists())
            self.assertTrue((modulo_resumen.BASE / "RESUMEN.md").exists())
            self.assertTrue((modulo_resumen.BASE / "comparacion_evaluacion.png").exists())


if __name__ == "__main__":
    unittest.main()
