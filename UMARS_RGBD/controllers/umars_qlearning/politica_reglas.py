"""Referencia simple con las mismas observaciones y acciones que Q-learning."""

from agente_q import ACCIONES


class PoliticaReglas:
    def __init__(self):
        self.lado = None

    def elegir_accion(self, zonas, direccion_meta):
        seguras = zonas.get("acciones_seguras", {})

        def puede_avanzar(accion):
            return seguras.get(accion, zonas["avance_seguro"])

        if self.lado is not None:
            if not puede_avanzar("AVANZAR"):
                return ACCIONES.index(self.lado)

            # Mantener el obstaculo al costado hasta que quede atras.
            costado = (
                "derecha" if self.lado == "GIRAR_IZQUIERDA"
                else "izquierda"
            )
            if zonas[costado]["estado"] != "LIBRE":
                return ACCIONES.index("AVANZAR")
            self.lado = None

        if not puede_avanzar("AVANZAR") or zonas["centro"]["estado"] != "LIBRE":
            izquierda = zonas["izquierda"]["distancia_m"] or 0.0
            derecha = zonas["derecha"]["distancia_m"] or 0.0
            self.lado = (
                "GIRAR_IZQUIERDA" if izquierda >= derecha
                else "GIRAR_DERECHA"
            )
            return ACCIONES.index(self.lado)

        if direccion_meta == -1 and puede_avanzar("AVANZAR_IZQUIERDA"):
            return ACCIONES.index("AVANZAR_IZQUIERDA")
        if direccion_meta == 1 and puede_avanzar("AVANZAR_DERECHA"):
            return ACCIONES.index("AVANZAR_DERECHA")
        return ACCIONES.index("AVANZAR")
