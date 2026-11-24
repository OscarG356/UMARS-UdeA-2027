
import math


class EntornoUMARS:
    """
    Evalua navegacion 2D usando la geometria del mundo Webots.

    La informacion de los obstaculos se utiliza SOLO para
    verificar colisiones, calcular recompensas y finalizar
    episodios. Nunca se entrega directamente a la politica.
    """

    NOMBRES_ROCAS = {
        "roca_central",
        "piedra_lateral_izquierda",
        "piedra_lateral_derecha",
    }

    NOMBRE_TERRENO = "terreno_marciano_simplificado"

    def __init__(self, robot):

        self.robot = robot

        # Aproximacion circular del chasis + margen
        self.radio_rover = 0.25

        # Radio para considerar alcanzada la meta
        self.radio_meta = 0.35

        # Posicion inicial del rover
        self.posicion_inicial = [-1.5, 0.0, 0.15]

        # ==========================================
        # 1. OBTENER LA META
        # ==========================================

        meta = robot.getFromDef("UMARS_META")

        if meta is None:
            raise RuntimeError(
                "Falta DEF UMARS_META en marte_qlearning.wbt"
            )

        self.campo_meta = meta.getField("translation")

        # ==========================================
        # 2. OBTENER OBSTACULOS Y TERRENO
        # ==========================================

        self.obstaculos = []
        self.limites = None

        hijos = robot.getRoot().getField("children")

        for i in range(hijos.getCount()):

            nodo = hijos.getMFNode(i)
            campo_nombre = nodo.getField("name")

            if campo_nombre is None:
                continue

            nombre = campo_nombre.getSFString()

            if (
                nombre not in self.NOMBRES_ROCAS
                and nombre != self.NOMBRE_TERRENO
            ):
                continue

            campo_pos = nodo.getField("translation")
            campo_caja = nodo.getField("boundingObject")

            if campo_pos is None or campo_caja is None:
                raise RuntimeError(
                    f"Faltan coordenadas o boundingObject: {nombre}"
                )

            caja = campo_caja.getSFNode()

            if caja is None or caja.getField("size") is None:
                raise RuntimeError(
                    f"Se esperaba boundingObject Box en {nombre}"
                )

            x, y, _ = campo_pos.getSFVec3f()
            sx, sy, _ = caja.getField("size").getSFVec3f()

            # Limites del rectangulo
            rect = (
                x - sx / 2,
                x + sx / 2,
                y - sy / 2,
                y + sy / 2
            )

            if nombre == self.NOMBRE_TERRENO:
                self.limites = rect
            else:
                self.obstaculos.append((nombre, rect))

        if self.limites is None or len(self.obstaculos) != 3:
            raise RuntimeError(
                "No se encontraron el terreno y las 3 rocas. "
                "Revisa los campos name de los Solid del mundo."
            )

    # ==========================================
    # 3. REINICIAR ROVER
    # ==========================================

    def reiniciar(self, campo_posicion, campo_rotacion):

        campo_posicion.setSFVec3f(
            self.posicion_inicial[:]
        )

        campo_rotacion.setSFRotation([
            0, 0, 1, 0
        ])

    # ==========================================
    # 4. DISTANCIA A LA META
    # ==========================================

    def distancia_meta(self, pos):

        mx, my, _ = self.campo_meta.getSFVec3f()

        return math.hypot(
            pos[0] - mx,
            pos[1] - my
        )

    # ==========================================
    # 5. DETECTAR COLISION
    # ==========================================

    def detectar_colision(self, pos):
        """
        Aproximacion circulo vs rectangulos en 2D.

        Retorna:
          None si no hay colision.
          Un texto indicando la colision si existe.
        """

        x, y = pos[:2]

        xmin, xmax, ymin, ymax = self.limites

        r = self.radio_rover

        # Comprobar limites del terreno
        if (
            x - r < xmin
            or x + r > xmax
            or y - r < ymin
            or y + r > ymax
        ):
            return "FUERA_DEL_TERRENO"

        # Comprobar obstaculos
        for nombre, (ax, bx, ay, by) in self.obstaculos:

            # Punto mas cercano del rectangulo al rover
            cerca_x = max(ax, min(x, bx))
            cerca_y = max(ay, min(y, by))

            distancia = math.hypot(
                x - cerca_x,
                y - cerca_y
            )

            if distancia <= r:
                return f"COLISION_{nombre}"

        return None

    # ==========================================
    # 6. VALIDAR AVANCE
    # ==========================================

    def validar_avance(self, origen, destino):
        """
        Comprueba puntos intermedios entre origen
        y destino para evitar saltar obstaculos.
        """

        dx = destino[0] - origen[0]
        dy = destino[1] - origen[1]

        distancia = math.hypot(dx, dy)

        # Una muestra aproximadamente cada 2.5 cm
        muestras = max(
            1,
            math.ceil(distancia / 0.025)
        )

        puntos = []
        for i in range(1, muestras + 1):

            t = i / muestras

            p = [
                origen[0] + t * dx,
                origen[1] + t * dy,
                origen[2]
            ]

            puntos.append(p)

        return self.validar_trayectoria(puntos)

    def validar_trayectoria(self, puntos):
        """Comprueba cada muestra de una recta o de un arco."""
        for punto in puntos:
            motivo = self.detectar_colision(punto)
            if motivo is not None:
                return False, motivo
        return True, None

    # ==========================================
    # 7. EVALUAR TRANSICION
    # ==========================================

    def evaluar_transicion(
        self,
        antes,
        despues,
        motivo_colision=None
    ):

        d_antes = self.distancia_meta(antes)
        d_despues = self.distancia_meta(despues)

        progreso = d_antes - d_despues

        # Penalizacion por paso y recompensa por progreso
        recompensa = -1.0 + 2.0 * progreso

        # Comprobar llegada a la meta
        llego_meta = (
            motivo_colision is None
            and d_despues <= self.radio_meta
        )

        # Penalizacion por colision
        if motivo_colision is not None:
            recompensa -= 50.0

        # Recompensa por alcanzar la meta
        elif llego_meta:
            recompensa += 100.0

        terminado = (
            motivo_colision is not None
            or llego_meta
        )

        return {
            "distancia_actual": d_despues,
            "progreso": progreso,
            "recompensa": recompensa,
            "llego_meta": llego_meta,
            "motivo_colision": motivo_colision,
            "terminado": terminado,
        }
