"""Compara las corridas completas de Q y reglas por meta e inicio."""

import csv
import json
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados" / "generalizacion"


def leer_corridas():
    corridas = {}
    if not RESULTADOS.exists():
        return corridas

    for archivo in RESULTADOS.glob("*/configuracion.json"):
        carpeta = archivo.parent
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        episodios = carpeta / "episodios_evaluacion.csv"
        if not episodios.exists():
            print(f"INCOMPLETA (sin CSV): {carpeta}")
            continue
        with episodios.open(newline="", encoding="utf-8") as f:
            filas = list(csv.DictReader(f))

        nombres = [inicio["nombre"] for inicio in datos["inicios"]]
        if [fila["inicio"] for fila in filas] != nombres:
            print(f"INCOMPLETA ({len(filas)}/{len(nombres)} inicios): {carpeta}")
            continue

        meta = tuple(round(float(v), 2) for v in datos["meta"][:2])
        clave = (meta, datos["politica"])
        if clave not in corridas or archivo.stat().st_mtime > corridas[clave][0]:
            corridas[clave] = (archivo.stat().st_mtime, datos, filas, carpeta)
    return corridas


def resumen():
    corridas = leer_corridas()
    if not corridas:
        print(f"No hay corridas completas en {RESULTADOS}")
        print("Abre marte_generalizacion_norte.wbt y "
              "marte_generalizacion_sur.wbt; espera el resumen de Q y reglas "
              "en cada mundo.")
        return

    metas = sorted({meta for meta, _ in corridas})
    for meta in metas:
        print(f"\nMETA ({meta[0]:.2f}, {meta[1]:.2f})")
        par = {politica: corridas.get((meta, politica)) for politica in ("q", "reglas")}
        for politica, corrida in par.items():
            print(f"  {politica}: {corrida[3] if corrida else 'SIN CORRIDA COMPLETA'}")
        if par["q"] and par["reglas"]:
            if par["q"][1]["sha256_tabla_q"] != par["reglas"][1]["sha256_tabla_q"]:
                print("  ADVERTENCIA: se cargaron tablas Q diferentes")

        nombres = list(dict.fromkeys(
            fila["inicio"] for corrida in par.values() if corrida
            for fila in corrida[2]
        ))
        print("  inicio    politica  resultado                pasos  retorno")
        for nombre in nombres:
            for politica, corrida in par.items():
                if corrida is None:
                    continue
                fila = next((r for r in corrida[2] if r["inicio"] == nombre), None)
                if fila is None:
                    continue
                print(f"  {nombre:<9} {politica:<9} {fila['resultado']:<24} "
                      f"{fila['pasos']:>5}  {float(fila['retorno']):>8.3f}")

        for politica, corrida in par.items():
            if corrida is None:
                continue
            filas = corrida[2]
            exitos = sum(f["resultado"] == "META" for f in filas)
            colisiones = sum(f["resultado"].startswith("COLISION_") or
                            f["resultado"] == "FUERA_DEL_TERRENO" for f in filas)
            retorno = sum(float(f["retorno"]) for f in filas) / len(filas)
            print(f"  {politica}: metas={exitos}/{len(filas)}, "
                  f"colisiones={colisiones}/{len(filas)}, "
                  f"retorno_medio={retorno:.3f}")


if __name__ == "__main__":
    resumen()
