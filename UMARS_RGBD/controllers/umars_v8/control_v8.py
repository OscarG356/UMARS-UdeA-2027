"""Funciones puras de recompensa y geometria temporal para la version v8."""

from dataclasses import dataclass
import math
import random


GIROS_PUROS = {"GIRAR_IZQUIERDA", "GIRAR_DERECHA"}
AVANCES = {"AVANZAR", "AVANZAR_IZQUIERDA", "AVANZAR_DERECHA"}
NORTE = "piedra_lateral_izquierda"
SUR = "piedra_lateral_derecha"


def costo_giro(accion, zonas, penalizacion):
    """Devuelve la penalizacion negativa solo si un giro puro era opcional."""
    if penalizacion < 0 or not math.isfinite(penalizacion):
        raise ValueError("La penalizacion de giro debe ser finita y no negativa")
    if accion not in GIROS_PUROS:
        return 0.0
    seguras = zonas["acciones_seguras"]
    return -penalizacion if any(seguras[a] for a in AVANCES) else 0.0


def pose_fraccion(origen, rumbo, accion, fraccion, paso=0.20, giro=math.pi / 6):
    """Pose del rover durante una accion; fraccion en [0, 1]."""
    if not 0 <= fraccion <= 1:
        raise ValueError("Fraccion fuera de [0, 1]")
    x, y, z = origen
    if accion == "GIRAR_IZQUIERDA":
        return [x, y, z], rumbo + giro * fraccion
    if accion == "GIRAR_DERECHA":
        return [x, y, z], rumbo - giro * fraccion
    if accion == "AVANZAR":
        return [x + paso * fraccion * math.cos(rumbo),
                y + paso * fraccion * math.sin(rumbo), z], rumbo
    if accion not in ("AVANZAR_IZQUIERDA", "AVANZAR_DERECHA"):
        raise ValueError(f"Accion desconocida: {accion}")
    delta = giro if accion == "AVANZAR_IZQUIERDA" else -giro
    radio = paso / delta
    angulo = rumbo + delta * fraccion
    return [x + radio * (math.sin(angulo) - math.sin(rumbo)),
            y - radio * (math.cos(angulo) - math.cos(rumbo)), z], angulo


def rectangulo(x, y, ancho, alto):
    return (x - ancho / 2, x + ancho / 2, y - alto / 2, y + alto / 2)


def fuera_del_terreno(posicion, limites, radio_rover):
    x, y = posicion[:2]
    xmin, xmax, ymin, ymax = limites
    return (x - radio_rover < xmin or x + radio_rover > xmax or
            y - radio_rover < ymin or y + radio_rover > ymax)


def respeta_limites(origen, rumbo, accion, limites, radio_rover):
    """Comprueba los extremos de la trayectoria con la proyeccion del validador."""
    fracciones = [0.0, 1.0]
    _, rumbo_final = pose_fraccion(origen, rumbo, accion, 1.0)
    if accion in ("AVANZAR_IZQUIERDA", "AVANZAR_DERECHA"):
        # Entre dos rumbos cardinales cada coordenada del arco es monotona.
        menor, mayor = sorted((rumbo, rumbo_final))
        cuadrante = math.pi / 2
        for indice in range(math.floor(menor / cuadrante) + 1,
                            math.ceil(mayor / cuadrante)):
            fracciones.append((indice * cuadrante - rumbo) / (rumbo_final - rumbo))
    return all(
        not fuera_del_terreno(pose_fraccion(origen, rumbo, accion, f)[0], limites, radio_rover)
        for f in fracciones
    )


def giro_abre_avance(origen, rumbo, giro, limites, radio_rover):
    """Comprueba si girar deja alguna trayectoria de avance dentro del terreno."""
    if not respeta_limites(origen, rumbo, giro, limites, radio_rover):
        return False
    posicion, orientacion = pose_fraccion(origen, rumbo, giro, 1.0)
    return any(respeta_limites(posicion, orientacion, avance, limites, radio_rover)
               for avance in AVANCES)


def detectar_colision(posicion, limites, obstaculos, radio_rover=0.25):
    """Misma prueba circulo-rectangulo del entorno v7, con cajas suministradas."""
    if fuera_del_terreno(posicion, limites, radio_rover):
        return "FUERA_DEL_TERRENO"
    x, y = posicion[:2]
    for nombre, (ax, bx, ay, by) in obstaculos:
        px = max(ax, min(x, bx))
        py = max(ay, min(y, by))
        if math.hypot(x - px, y - py) <= radio_rover:
            return f"COLISION_{nombre}"
    return None


@dataclass(frozen=True)
class ParametrosRocas:
    dinamico: bool
    semilla: int
    fase: str
    episodio: int
    omega_norte: float
    omega_sur: float
    fase_norte: float
    fase_sur: float
    amplitud_norte: float
    amplitud_sur_x: float
    amplitud_sur_y: float


def parametros_episodio(dinamico, semilla, fase, episodio, escala_velocidad=1.0,
                       amplitud_norte=0.35, amplitud_sur_x=0.25,
                       amplitud_sur_y=0.25, desfase_norte=0.0,
                       desfase_sur=0.0):
    """Entrenamiento y evaluacion usan pares de velocidades distintos."""
    if fase not in ("ENTRENAMIENTO", "EVALUACION", "REGLAS"):
        raise ValueError("Fase invalida")
    if episodio < 1 or not math.isfinite(escala_velocidad) or escala_velocidad <= 0:
        raise ValueError("Episodio o escala de velocidad invalidos")
    amplitudes = (amplitud_norte, amplitud_sur_x, amplitud_sur_y)
    if any(not math.isfinite(v) or v < 0 for v in amplitudes):
        raise ValueError("Amplitudes invalidas")
    if amplitud_norte > 0.6 or amplitud_sur_x > 0.6 or amplitud_sur_y > 0.5:
        raise ValueError("Amplitud excede la zona segura definida para las rocas")
    if not dinamico:
        return ParametrosRocas(False, semilla, fase, episodio, 0.0, 0.0,
                               0.0, 0.0, 0.0, 0.0, 0.0)
    entrenamiento = fase == "ENTRENAMIENTO"
    pares = ((0.42, 0.34), (0.60, 0.48)) if entrenamiento else (
        (0.50, 0.40), (0.68, 0.55))
    omega_norte, omega_sur = pares[(episodio - 1) % len(pares)]
    # La politica no cambia el escenario: Q y reglas comparten la semilla.
    semilla_episodio = semilla + (0 if entrenamiento else 100000) + episodio
    rng = random.Random(semilla_episodio)
    return ParametrosRocas(
        True, semilla_episodio, fase, episodio,
        omega_norte * escala_velocidad, omega_sur * escala_velocidad,
        (rng.uniform(0, 2 * math.pi) + desfase_norte) % (2 * math.pi),
        (rng.uniform(0, 2 * math.pi) + desfase_sur) % (2 * math.pi),
        amplitud_norte, amplitud_sur_x, amplitud_sur_y,
    )


class RocasV8:
    """Sincroniza pose visual de las rocas y rectangulos del evaluador."""

    def __init__(self, entorno, campos=None):
        self.entorno = entorno
        self.campos = campos or {}
        self.base = {}
        for nombre, (ax, bx, ay, by) in entorno.obstaculos:
            self.base[nombre] = ((ax + bx) / 2, (ay + by) / 2, bx - ax, by - ay)
        self.alturas = {nombre: campo.getSFVec3f()[2]
                        for nombre, campo in self.campos.items()}
        self.parametros = None

    def configurar(self, parametros):
        if parametros.dinamico and set(self.campos) != {NORTE, SUR}:
            raise RuntimeError("El mundo dinamico debe tener las dos rocas moviles")
        self.parametros = parametros
        self.actualizar(0.0)

    def posiciones(self, tiempo):
        p = self.parametros
        if p is None:
            raise RuntimeError("Configura las rocas antes de leerlas")
        posiciones = {nombre: (x, y) for nombre, (x, y, _, _) in self.base.items()}
        if p.dinamico:
            x, y = posiciones[NORTE]
            posiciones[NORTE] = (x + p.amplitud_norte * math.sin(
                p.omega_norte * tiempo + p.fase_norte), y)
            x, y = posiciones[SUR]
            angulo = p.omega_sur * tiempo + p.fase_sur
            posiciones[SUR] = (x + p.amplitud_sur_x * math.cos(angulo),
                               y + p.amplitud_sur_y * math.sin(angulo))
        return posiciones

    def rectangulos(self, tiempo):
        posiciones = self.posiciones(tiempo)
        return [(nombre, rectangulo(*posiciones[nombre], ancho, alto))
                for nombre, (_, _, ancho, alto) in self.base.items()]

    def actualizar(self, tiempo):
        posiciones = self.posiciones(tiempo)
        for nombre, campo in self.campos.items():
            x, y = posiciones[nombre]
            campo.setSFVec3f([x, y, self.alturas[nombre]])
        self.entorno.obstaculos = self.rectangulos(tiempo)
        return posiciones


def validar_accion_temporal(origen, rumbo, accion, tiempo, duracion,
                           rocas, limites, radio_rover=0.25, muestras=20):
    """Muestrea simultaneamente rover y rocas durante toda la accion."""
    if muestras < 2 or duracion <= 0:
        raise ValueError("Duracion o numero de muestras invalidos")
    p = getattr(rocas, "parametros", None)
    if p is not None and p.dinamico:
        velocidad_max = max(
            p.omega_norte * p.amplitud_norte,
            p.omega_sur * math.hypot(p.amplitud_sur_x, p.amplitud_sur_y),
        )
        frecuencia_max = max(p.omega_norte, p.omega_sur)
        muestras = max(
            muestras,
            math.ceil((0.20 + velocidad_max * duracion) / 0.02),
            math.ceil(frecuencia_max * duracion * 20 / (2 * math.pi)),
        )
    for i in range(muestras + 1):
        fraccion = i / muestras
        pose, _ = pose_fraccion(origen, rumbo, accion, fraccion)
        motivo = detectar_colision(pose, limites,
                                   rocas.rectangulos(tiempo + duracion * fraccion),
                                   radio_rover)
        if motivo:
            return False, motivo, fraccion
    return True, None, 1.0
