
import random
import math
import numpy as np

ACCIONES = (
    "AVANZAR",
    "GIRAR_IZQUIERDA",
    "GIRAR_DERECHA",
    "AVANZAR_IZQUIERDA",
    "AVANZAR_DERECHA",
)

DISTANCIA_CORTE = 2.5
NUM_ESTADOS = 8 * 3 * 3 * 2

def acciones_permitidas(zonas, error_meta=None):
    """Aplica limites de avance sin imponer la direccion del giro."""
    seguras = zonas.get("acciones_seguras")
    if seguras is None:
        seguras = {accion: zonas["avance_seguro"] for accion in
                   ("AVANZAR", "AVANZAR_IZQUIERDA", "AVANZAR_DERECHA")}
    permitidas = tuple(
        i for i, accion in enumerate(ACCIONES)
        if i in (1, 2) or seguras[accion]
    )
    if permitidas == (1, 2):
        return (1, 2)

    # Los tres sectores de meta no distinguen entre un objetivo lateral y
    # uno casi detras. En espacio libre, orientar primero el rover.
    if error_meta is not None and abs(error_meta) > math.pi / 2:
        return (1,) if error_meta > 0 else (2,)

    despejado = all(
        zonas.get(nombre, {}).get("estado") == "LIBRE"
        for nombre in ("izquierda", "centro", "derecha")
    )
    if despejado and error_meta is not None:
        if error_meta > math.pi / 3:
            return tuple(i for i in (3, 1) if i in permitidas)
        if error_meta < -math.pi / 3:
            return tuple(i for i in (4, 2) if i in permitidas)
        if error_meta > math.pi / 6:
            return tuple(i for i in (0, 3, 1) if i in permitidas)
        if error_meta < -math.pi / 6:
            return tuple(i for i in (0, 4, 2) if i in permitidas)

    return permitidas


class FiltroAntibucle:
    """Evita deshacer giros en el sitio y busca una salida segura."""

    def __init__(self):
        self.ultimo_giro = None
        self.giro_escape = None
        self.giros_sin_avance = 0

    def permitidas(self, zonas, error_meta=None):
        if self.giro_escape is None:
            return acciones_permitidas(zonas, error_meta)

        seguras = zonas.get("acciones_seguras")
        if seguras is None:
            seguras = {ACCIONES[i]: zonas["avance_seguro"] for i in (0, 3, 4)}
        avances = tuple(i for i in (0, 3, 4) if seguras[ACCIONES[i]])
        return avances if avances else (self.giro_escape,)

    def registrar(self, accion, antes, despues):
        desplazamiento = math.hypot(
            despues[0] - antes[0], despues[1] - antes[1]
        )
        if desplazamiento > 1e-4 or accion not in (1, 2):
            self.ultimo_giro = None
            self.giro_escape = None
            self.giros_sin_avance = 0
            return

        self.giros_sin_avance += 1
        if (self.giro_escape is None and self.giros_sin_avance >= 3
                and self.ultimo_giro is not None
                and accion != self.ultimo_giro):
            self.giro_escape = accion
        self.ultimo_giro = accion


def actualizar_lado(lado, accion, zonas_antes, zonas_despues):
    """Recuerda por que lado se empezo a rodear hasta dejar atras la roca."""
    if lado not in (0, 1, 2):
        raise ValueError("Lado de rodeo invalido")

    if lado == 0 and (
        zonas_antes["centro"]["estado"] != "LIBRE"
        or not zonas_antes.get("avance_seguro", True)
    ):
        if accion in (1, 3):
            lado = 1
        elif accion in (2, 4):
            lado = 2

    if lado:
        costado_obstaculo = "derecha" if lado == 1 else "izquierda"
        if (
            zonas_despues["centro"]["estado"] == "LIBRE"
            and zonas_despues[costado_obstaculo]["estado"] == "LIBRE"
        ):
            lado = 0

    return lado


def codificar_estado(zonas, direccion_meta, lado_rodeo, distancia_meta):
    """
    Convierte la percepcion en un estado entero de 0 a 143.

    Ocupacion:
      LIBRE = 0
      OCUPADO o DESCONOCIDO = 1

    Rumbo aproximado a la meta:
      -1 = izquierda
       0 = frente
       1 = derecha

    Lado de rodeo: 0 = ninguno, 1 = izquierda, 2 = derecha.
    Distancia a la meta: 0 = >= 2.5 m, 1 = < 2.5 m.
    """
    if direccion_meta not in (-1, 0, 1):
        raise ValueError("Direccion de meta invalida")
    if lado_rodeo not in (0, 1, 2):
        raise ValueError("Lado de rodeo invalido")
    if not math.isfinite(distancia_meta) or distancia_meta < 0:
        raise ValueError("Distancia a la meta invalida")

    bits = 0

    for nombre in ("izquierda", "centro", "derecha"):
        ocupado = int(zonas[nombre]["estado"] != "LIBRE")
        bits = (bits << 1) | ocupado

    distancia_cerca = int(distancia_meta < DISTANCIA_CORTE)
    return (((bits * 3 + (direccion_meta + 1)) * 3 + lado_rodeo) * 2
            + distancia_cerca)


class AgenteQ:

    def __init__(self, alpha=0.1, gamma=0.95, semilla=42):

        self.alpha = alpha
        self.gamma = gamma

        # Ocupacion (8), rumbo (3), lado de rodeo (3), distancia (2).
        self.q = np.zeros((NUM_ESTADOS, len(ACCIONES)), dtype=np.float64)

        self.rng = random.Random(semilla)

    def elegir_accion(self, estado, epsilon, permitidas=None):
        """
        Epsilon-greedy:
        - Con probabilidad epsilon, explora.
        - En otro caso, elige una accion de mayor Q.
        """

        if not 0 <= epsilon <= 1:
            raise ValueError("epsilon debe estar entre 0 y 1")

        permitidas = tuple(range(len(ACCIONES))) if permitidas is None else tuple(permitidas)
        if not permitidas or any(i not in range(len(ACCIONES)) for i in permitidas):
            raise ValueError("Acciones permitidas invalidas")

        if self.rng.random() < epsilon:
            return self.rng.choice(permitidas)

        fila = self.q[estado]
        mejor = max(fila[i] for i in permitidas)
        # Desempate fijo: la evaluacion con epsilon=0 es reproducible.
        return next(i for i in permitidas if np.isclose(fila[i], mejor))

    def actualizar(
        self,
        estado,
        accion,
        recompensa,
        siguiente_estado,
        terminal,
        siguientes_permitidas=None
    ):
        objetivo = float(recompensa)

        if not terminal:
            siguientes_permitidas = (
                range(len(ACCIONES))
                if siguientes_permitidas is None
                else siguientes_permitidas
            )
            objetivo += (
                self.gamma
                * max(float(self.q[siguiente_estado, i]) for i in siguientes_permitidas)
            )

        self.q[estado, accion] += self.alpha * (
            objetivo - self.q[estado, accion]
        )
