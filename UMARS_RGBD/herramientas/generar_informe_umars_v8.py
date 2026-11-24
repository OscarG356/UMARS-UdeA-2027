"""Exporta los resultados verificados y regenera las figuras del informe UMARS v8."""

from collections import Counter, defaultdict
import csv
from hashlib import sha256
from itertools import combinations
import json
import os
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from .comparar_cd_v8 import ESCENARIO
from .estudiar_aprendizaje_borde_v8 import casos_estudio, cargar_caso
from .resumir_v8 import ROOT, leer_csv
from .validar_borde_v8 import comparar_pares, movimientos_ejecutados
from .evaluar_borde_v8 import metricas

BASE = ROOT / "resultados"
SALIDA = BASE / "informe_preliminar_umars_v8"
DATOS = SALIDA / "datos"
GRAFICAS = SALIDA / "graficas"
POLITICAS = ("C histórica", "D histórica", "C nueva", "D nueva", "Reglas")
SEMILLAS = (42, 1042, 2042)
AVANCES = ("avance_seguro_recto", "avance_seguro_izquierda", "avance_seguro_derecha")
COLORES = dict(zip(POLITICAS, ("#49728e", "#8476ae", "#196d65", "#b14b32", "#8c7625")))


def csv_guardar(nombre, filas, campos=None):
    with (DATOS / nombre).open("w", newline="", encoding="utf-8") as archivo:
        if campos is None:
            campos = list(dict.fromkeys(k for f in filas for k in f))
        w = csv.DictWriter(archivo, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def figura(fig, nombre):
    fig.savefig(GRAFICAS / nombre, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def reunir():
    episodios, transiciones, configuraciones, pendientes = [], [], [], []
    historial, actual = set(), {}

    def registrar(etapa, politica, semilla, ruta, ep, tr):
        origen = ruta.relative_to(ROOT).as_posix()
        identidad = dict(etapa=etapa, politica_informe=politica, semilla_corrida=semilla, fuente=origen)
        cfg = json.loads((ruta / "configuracion.json").read_text(encoding="utf-8"))
        tabla = ruta / "q_table.npy"
        if not tabla.is_file() and cfg.get("tabla_congelada"):
            tabla = ruta / cfg["tabla_congelada"]
        configuraciones.append({**identidad, **cfg,
            "sha256_tabla_disponible": sha256(tabla.read_bytes()).hexdigest() if tabla.is_file() else ""})
        agrupadas = defaultdict(list)
        for t in tr:
            agrupadas[t["fase"], t["episodio"]].append(t)
        for f in ep:
            filas = agrupadas[f["fase"], f["episodio"]]
            acciones, giros = movimientos_ejecutados(f, filas)
            bloqueados = [sum(t[k] == "0" for k in AVANCES) for t in filas if all(t.get(k) in ("0", "1") for k in AVANCES)]
            borde = [
                len(set(t["acciones_antes_filtro_borde"].split(";")) -
                    set(t["acciones_permitidas"].split(";")))
                for t in filas if t.get("acciones_antes_filtro_borde")
            ]
            fila = {**identidad, **f, **metricas(f, filas),
                    "acciones_ejecutadas": acciones, "giros_ejecutados": giros,
                    "observaciones_con_mascara_sensor": len(bloqueados),
                    "avances_descartados_por_percepcion": sum(bloqueados),
                    "observaciones_con_mascara_borde": len(borde),
                    "candidatos_descartados_por_borde": sum(borde) if borde else "",
                    "estados_visitados": len({t["estado"] for t in filas if t["estado"]})}
            episodios.append(fila)
            for t in filas:
                transiciones.append({**identidad, "semilla_escenario": f["semilla_escenario"], **t})
            if etapa == "estudio" and f["fase"] != "ENTRENAMIENTO":
                actual.setdefault((politica, semilla), {})[f["semilla_escenario"]] = (fila, filas)

    for caso in casos_estudio():
        modo, p, semilla, ref, *_ = caso
        if ref.tabla is not None and (p, semilla) not in historial:
            historial.add((p, semilla))
            registrar("v8 histórico", p + " histórica", semilla, ref.referencia,
                      leer_csv(ref.referencia / "episodios.csv"),
                      leer_csv(ref.referencia / "transiciones.csv"))
        corrida = cargar_caso(caso)
        etiqueta = "Reglas" if p == "reglas" else p + (" nueva" if modo == "entrenar" else " histórica")
        if corrida is None:
            pendientes.append(dict(politica=etiqueta, semilla=semilla, modo=modo))
            continue
        ruta, ep, trazas = corrida
        registrar("rescate aislado" if modo == "rescate" else "estudio", etiqueta, semilla, ruta,
                  ep, [t for grupo in trazas.values() for t in grupo])
    for semilla in SEMILLAS:
        grupos = [
            [tuple(f[k] for k in ESCENARIO) for f in episodios if f["fase"] == "ENTRENAMIENTO"
             and f["semilla_corrida"] == semilla and f["politica_informe"] == p]
            for p in POLITICAS[:4]
        ]
        if any(g != grupos[0] for g in grupos[1:]):
            raise ValueError(f"Escenarios de entrenamiento distintos para la semilla {semilla}.")
    return episodios, transiciones, configuraciones, actual, pendientes


def cambios_q(episodios, transiciones):
    filas = defaultdict(list)
    datos = {(f["fuente"], f["fase"], f["episodio"]): f for f in episodios}
    for t in transiciones:
        if t["fase"] == "ENTRENAMIENTO":
            filas[t["fuente"], t["fase"], t["episodio"]].append(t)
    for clave, pasos in filas.items():
        for i, t in enumerate(pasos):
            if not t["accion"]:
                continue
            valor = float(t["q_" + t["accion"].lower()])
            terminal = t.get("terminal_q") or t["terminal"]
            if terminal == "1":
                futuro = None
            else:
                sig = pasos[i+1]
                permitidas = (t.get("acciones_permitidas_siguiente") or sig["acciones_permitidas"]).split(";")
                valores_siguientes = t if t["estado"] == sig["estado"] else sig
                futuro = max(float(valores_siguientes["q_" + a.lower()]) for a in permitidas)
            objetivo = float(t["recompensa_aprendizaje"]) + (.95 * futuro if futuro is not None else 0)
            yield dict(fuente=t["fuente"], etapa=t["etapa"], politica=t["politica_informe"],
                       semilla=t["semilla_corrida"], episodio=t["episodio"], paso=t["paso"],
                       estado=t["estado"], accion=t["accion"], terminal_q=terminal,
                       epsilon=datos[clave]["epsilon"], q_previo=valor, max_q_siguiente=futuro,
                       objetivo=objetivo, delta_q=.1*(objetivo-valor), q_actualizado=valor+.1*(objetivo-valor))


def comparar(actual):
    resumen, pares, exclusivos = [], [], []
    acumulados = defaultdict(list)
    for (p,s), episodios in sorted(actual.items()):
        ff = [f for f,_ in episodios.values()]
        fila = dict(politica=p, semilla=s, escenarios=len(ff))
        for k in ("llegadas", "vetos_borde", "contactos_rocas", "sin_acciones_seguras", "max_acciones",
                  "acciones", "acciones_ejecutadas", "giros_puros", "giros_ejecutados",
                  "avances_descartados_por_percepcion"):
            fila[k] = sum(f[k] for f in ff)
        fila["observaciones_con_mascara_sensor"] = sum(f["observaciones_con_mascara_sensor"] for f in ff)
        for k in ("distancia_recorrida_m", "tiempo_simulado_s", "retorno_base", "retorno_entrenamiento"):
            fila[k+"_medio"] = mean(float(f[k]) for f in ff)
        resumen.append(fila)
    for s in SEMILLAS:
        for a,b in combinations(POLITICAS,2):
            x,y = actual.get((a,s)), actual.get((b,s))
            if not x or not y:
                continue
            if x.keys()!=y.keys() or any(tuple(x[k][0][c] for c in ESCENARIO)!=
                                        tuple(y[k][0][c] for c in ESCENARIO) for k in x):
                raise ValueError(f"Escenarios incompatibles para {a}, {b}, semilla {s}")
            datos=[(x[k][0],y[k][0]) for k in x]
            pares.append(comparar_pares(datos,"estudio",a,b,{"semilla":s}))
            acumulados[a,b].extend(datos)
            exclusivos.extend(dict(semilla=s, escenario=u["semilla_escenario"], izquierda=a,
                                   derecha=b, resultado_izquierda=u["resultado"],
                                   resultado_derecha=v["resultado"])
                               for u,v in datos if u["llegadas"]!=v["llegadas"])
    pares.extend(comparar_pares(f,"estudio",a,b,{"semilla":"total"})
                 for (a,b),f in acumulados.items())
    return resumen, pares, exclusivos


def aprendizaje(episodios):
    grupos=defaultdict(list)
    for e in episodios:
        if e["fase"]=="ENTRENAMIENTO":
            grupos[e["politica_informe"], e["semilla_corrida"]].append(e)
    f,axes=plt.subplots(2,2,figsize=(14,9),layout="constrained")
    for p in POLITICAS[:4]:
        es=[grupos[p,s] for s in SEMILLAS if grupos[p,s]]
        if not es: continue
        color=COLORES[p]
        retornos=np.array([[float(x["retorno_base"]) for x in g] for g in es])
        ex=np.array([[float(x["exito"]) for x in g] for g in es])
        xs=np.arange(1,retornos.shape[1]+1)
        for r in retornos: axes[0,0].plot(xs,r,color=color,alpha=.19,lw=.8)
        axes[0,0].plot(xs,retornos.mean(axis=0),color=color,lw=1,label=p)
        ventana=np.ones(20)/20
        axes[0,1].plot(xs[19:],np.convolve(retornos.mean(axis=0),ventana,"valid"),color=color,label=p)
        axes[1,0].plot(xs[19:],100*np.convolve(ex.mean(axis=0),ventana,"valid"),color=color,label=p)
    eps=next(iter(grupos.values()))
    axes[1,1].plot([int(e["episodio"]) for e in eps],[float(e["epsilon"]) for e in eps],color="#304969")
    for ax,t,y in zip(axes.flat,("Retorno por episodio","Retorno móvil · 20 episodios",
                               "Llegadas móviles · 20 episodios","Programa de exploración"),
                     ("Retorno base [puntos]","Retorno base [puntos]","Llegadas [%]","ε [sin unidad]")):
        ax.set(title=t,xlabel="Episodio de entrenamiento",ylabel=y)
    axes[0,0].legend(fontsize=8,ncol=2)
    figura(f,"aprendizaje_retorno_exito_epsilon.png")
    f,axes=plt.subplots(1,2,figsize=(13,4.6),layout="constrained")
    for p in POLITICAS[:4]:
        es=[grupos[p,s] for s in SEMILLAS if grupos[p,s]]
        if not es: continue
        for ax,k in zip(axes,("acciones_ejecutadas","giros_ejecutados")):
            datos=np.mean([[e[k] for e in g] for g in es],axis=0)
            ax.plot(np.arange(1,len(datos)+1),datos,color=COLORES[p],label=p,alpha=.9,lw=1)
    for ax,t in zip(axes,("Acciones con cambio de pose","Giros puros con cambio de rumbo")):
        ax.set(title=t,xlabel="Episodio de entrenamiento",ylabel="Conteo medio por episodio")
    axes[0].legend(fontsize=8,ncol=2)
    figura(f,"aprendizaje_acciones_giros.png")


def evaluacion(resumen, pares):
    f,axes=plt.subplots(1,2,figsize=(13,4.8),layout="constrained")
    for j,p in enumerate(POLITICAS):
        ff=[r for r in resumen if r["politica"]==p]
        if not ff: continue
        n=sum(r["escenarios"] for r in ff); x=sum(r["llegadas"] for r in ff)
        axes[0].bar(j,100*x/n,color=COLORES[p]);axes[0].text(j,100*x/n+1,f"{x}/{n}",ha="center",fontsize=8)
        axes[1].bar([SEMILLAS.index(r["semilla"])+(j-2)*.16 for r in ff],
                    [r["llegadas"] for r in ff],width=.15,color=COLORES[p],label=p)
    axes[0].set(xticks=range(5),xticklabels=POLITICAS,title="Llegadas en escenarios medidos",ylabel="Tasa de llegada [%]",ylim=(0,110))
    axes[1].set(xticks=range(3),xticklabels=SEMILLAS,xlabel="Bloque de semilla",ylabel="Llegadas de 20",title="Comparación por semilla",ylim=(0,21))
    axes[1].legend(fontsize=8,ncol=2)
    figura(f,"evaluacion_llegadas.png")
    pp=[r for r in pares if r["semilla"]=="total" and r["llegadas_compartidas"]]
    if pp:
        f,axes=plt.subplots(2,1,figsize=(14,8),layout="constrained")
        xs=np.arange(len(pp))
        for ax,k,title in zip(axes,("acciones_ejecutadas","giros_ejecutados"),("Acciones medias","Giros puros medios")):
            for i,l in enumerate(("izquierda","derecha")):
                ax.bar(xs+(i-.5)*.36,[r[k+"_"+l] for r in pp],width=.36,
                       color=[COLORES[r[l]] for r in pp],alpha=1.0 if i==0 else .72)
            ax.set(xticks=xs,xticklabels=[f"{r['izquierda']} / {r['derecha']}\nn={r['llegadas_compartidas']}" for r in pp],
                   ylabel="Conteo medio por llegada",title=title)
            ax.tick_params(axis="x",labelsize=8,rotation=19)
        figura(f,"evaluacion_eficiencia_pareada.png")
    f,axes=plt.subplots(1,2,figsize=(13,4.8),layout="constrained")
    for j,p in enumerate(POLITICAS):
        ff=[r for r in resumen if r["politica"]==p]
        if not ff:continue
        n=sum(r["escenarios"] for r in ff); acum=0
        for k,t,c in (("llegadas","Meta","#469667"),("contactos_rocas","Contacto","#c35b48"),
                     ("sin_acciones_seguras","Bloqueo","#806caf"),("vetos_borde","Veto borde","#d3a04b"),
                     ("max_acciones","Límite","#656b74")):
            v=100*sum(r[k] for r in ff)/n
            axes[0].bar(j,v,bottom=acum,color=c,label=t if j==0 else None);acum+=v
        den=sum(r["observaciones_con_mascara_sensor"] for r in ff)
        axes[1].bar(j,100*sum(r["avances_descartados_por_percepcion"] for r in ff)/(3*den),
                    color=COLORES[p])
    for ax,title,y in zip(axes,("Resultados finales","Avances rechazados por percepción fusionada"),
                          ("Episodios medidos [%]","Candidatos de avance [%]")):
        ax.set(xticks=range(5),xticklabels=POLITICAS,title=title,ylabel=y)
    axes[0].legend(fontsize=8)
    figura(f,"evaluacion_terminaciones_percepcion.png")

    entrenado = [r for r in pares if r["semilla"] != "total" and
                 (r["izquierda"], r["derecha"]) in (("C histórica", "C nueva"), ("D histórica", "D nueva"))]
    if entrenado:
        f,ax=plt.subplots(figsize=(11,4.4),layout="constrained")
        x=np.arange(len(entrenado))
        base=np.zeros(len(entrenado),dtype=int)
        for nombre,color,funcion in (
            ("Llegan ambas","#538d68",lambda r:r["llegadas_compartidas"]),
            ("Solo histórica","#7185a3",lambda r:r["perdidos"]),
            ("Solo nueva","#af6545",lambda r:r["recuperados"]),
            ("Faltan ambas","#b7b7ad",lambda r:r["escenarios"]-r["llegadas_compartidas"]-r["perdidos"]-r["recuperados"]),
        ):
            valores=[funcion(r) for r in entrenado]
            ax.bar(x,valores,bottom=base,color=color,label=nombre)
            base+=valores
        ax.set(xticks=x,xticklabels=[f"{r['izquierda'][0]}, semilla {r['semilla']}" for r in entrenado],
               title="Mismos escenarios · entrenamiento con y sin filtro previo",
               ylabel="Escenarios de evaluación",ylim=(0,21))
        ax.legend(ncol=2,fontsize=8)
        figura(f,"evaluacion_entrenamiento_contra_historico.png")


def seguridad_validada():
    filas=leer_csv(BASE/"validacion_borde_v8"/"consolidado.csv")
    f,axes=plt.subplots(1,3,figsize=(13,4.2),layout="constrained")
    xs=np.arange(3)
    for j,modo in enumerate(("original","corregido")):
        for ax,k,t in zip(axes,("vetos_borde","contactos_rocas","sin_acciones_seguras"),
                          ("Vetos por borde","Contactos con rocas","Sin acciones seguras")):
            ax.bar(xs+(j-.5)*.34,[sum(int(r[k]) for r in filas if r["politica"]==p and r["modo"]==modo)
                                  for p in ("C","D","reglas")],width=.34,
                   label=("Sin filtro previo","Con filtro previo")[j],color=("#6b8193","#a85639")[j])
            ax.set(xticks=xs,xticklabels=("C","D","Reglas"),title=t,ylabel="Eventos en 60 episodios")
    axes[0].legend(fontsize=8)
    figura(f,"seguridad_validacion_borde.png")
    csv_guardar("validacion_borde_previa.csv",filas)


def navegacion(actual):
    ejemplares=[(p,s,ep,tr) for (p,s),ee in actual.items() for ep,tr in ee.values()]
    exitos=[x for x in ejemplares if x[2]["exito"]=="1"]
    fallos=[x for x in ejemplares if x[2]["exito"]=="0"]
    if not exitos or not fallos:return
    corto=min(exitos,key=lambda x:int(x[2]["pasos"]))
    largo=max(exitos,key=lambda x:int(x[2]["pasos"]))
    fallo=next((x for x in fallos if x[2]["contactos_rocas"]),fallos[0])
    ejes=[("Llegada con menos acciones",corto),("Llegada con más acciones",largo),("Fallo registrado",fallo)]
    f,axes=plt.subplots(2,3,figsize=(14,8),layout="constrained")
    descripciones=[]
    for j,(titulo,(p,s,e,tr)) in enumerate(ejes):
        ax=axes[0,j];ax.add_patch(Rectangle((-.125,-.275),.45,.55,color="#665c52",alpha=.45))
        mov=[t for t in tr if t["accion"]]
        xx=[float(e["inicio_x"])]+[float(t["x"]) for t in mov]
        yy=[float(e["inicio_y"])]+[float(t["y"]) for t in mov]
        ax.plot(xx,yy,color="#156375",label="Rover",marker=".",ms=3)
        for nombre,color in (("norte","#c55a48"),("sur","#957346")):
            pts=[(float(t[f"roca_{nombre}_x"]),float(t[f"roca_{nombre}_y"])) for t in mov
                 if t.get(f"roca_{nombre}_x") and t.get(f"roca_{nombre}_y")]
            if pts:ax.plot(*zip(*pts),color=color,lw=2,label=f"Roca {nombre}")
        ax.scatter([float(e["meta_x"])],[float(e["meta_y"])],marker="*",color="#536d34",label="Meta")
        ax.set(title=f"{titulo}\n{p}, escenario {e['semilla_escenario']}",xlabel="x [m]",ylabel="y [m]",
               xlim=(-3,3),ylim=(-2,2),aspect="equal")
        if j==0:ax.legend(fontsize=7,loc="lower right")
        ax=axes[1,j]; t=np.arange(1,len(mov)+1)*.096
        ax.plot(t,[float(x["distancia_meta_m"]) for x in mov],label="Distancia a meta",color="#156375")
        ax.plot(t,[float(x["lidar_min_m"]) if x["lidar_min_m"] else np.nan for x in mov],
                label="Mínimo LiDAR",color="#a85639")
        if any(x.get("rgbd_min_franja_m") for x in mov):
            ax.plot(t,[float(x["rgbd_min_franja_m"]) if x.get("rgbd_min_franja_m") else np.nan for x in mov],
                    label="Mínimo RGB-D franja",color="#62518a",alpha=.7)
        ax.axhline(.35,color="#69737e",ls=":",lw=1,label="Radio de meta")
        ax.set(xlabel="Tiempo tras el reinicio [s]",ylabel="Distancia [m]")
        ax.legend(fontsize=7)
        descripciones.append(dict(caso=titulo,politica=p,semilla=s,semilla_escenario=e["semilla_escenario"],
                                  resultado=e["resultado"],acciones=e["acciones"],giros=e["giros_puros"],
                                  distancia_recorrida_m=e["distancia_recorrida_m"],
                                  tiempo_simulado_s=e["tiempo_simulado_s"],fuente=e["fuente"]))
    figura(f,"navegacion_casos_y_distancias.png")
    csv_guardar("casos_representativos.csv",descripciones)

    por_escenario=defaultdict(list)
    for p,s,e,tr in ejemplares:por_escenario[s,e["semilla_escenario"]].append((p,e,tr))
    bloque=max(por_escenario.values(),key=lambda z:(len(z),len({e["resultado"] for _,e,_ in z})))
    f,ax=plt.subplots(figsize=(10,6),layout="constrained")
    ax.add_patch(Rectangle((-.125,-.275),.45,.55,color="#665c52",alpha=.45))
    ax.scatter([2.2],[.75],color="black",marker="*",label="Meta")
    for p,e,tr in bloque:
        ts=[t for t in tr if t["accion"]]
        ax.plot([float(e["inicio_x"])]+[float(t["x"]) for t in ts],
                [float(e["inicio_y"])]+[float(t["y"]) for t in ts],
                color=COLORES[p],marker=".",ms=3,label=f"{p} · {e['resultado']}")
    ax.set(xlabel="x [m]",ylabel="y [m]",title=f"Trayectorias en el escenario compartido {bloque[0][1]['semilla_escenario']}",
           xlim=(-3,3),ylim=(-2,2),aspect="equal")
    ax.legend(fontsize=8,loc="lower right")
    figura(f,"navegacion_politicas_escenario_compartido.png")

    instrumentados=[x for x in ejemplares if any(t.get("rgbd_min_franja_m") for t in x[3])]
    if instrumentados:
        p,s,ep,tr=next((x for x in instrumentados if x[2]["exito"]=="1"), instrumentados[0])
        tr=[t for t in tr if t["accion"]]
        f,ax=plt.subplots(figsize=(11,4.5),layout="constrained")
        for k,l in (("rgbd_izquierda_m","RGB-D izquierda"),("rgbd_centro_m","RGB-D centro"),
                    ("rgbd_derecha_m","RGB-D derecha"),("rgbd_min_franja_m","Mínimo RGB-D en franja"),
                    ("lidar_min_m","Mínimo LiDAR")):
            ax.plot(np.arange(len(tr))*.096,[float(t[k]) if t.get(k) else np.nan for t in tr],label=l)
        ax.set(title=f"Lecturas antes de decidir · {p}, escenario {ep['semilla_escenario']}",
               xlabel="Tiempo desde primera observación [s]",ylabel="Distancia [m]")
        ax.legend(ncol=3,fontsize=8)
        figura(f,"navegacion_lecturas_rgbd_lidar.png")


def resumir_sensores(transiciones):
    grupos=defaultdict(list)
    for t in transiciones:
        grupos[t["fuente"],t["fase"]].append(t)
    for (fuente,fase),filas in sorted(grupos.items()):
        for k in ("lidar_min_m","rgbd_min_franja_m","rgbd_izquierda_m","rgbd_centro_m","rgbd_derecha_m"):
            valores=[float(f[k]) for f in filas if f.get(k)]
            yield dict(fuente=fuente,fase=fase,medida=k,decisiones=len(filas),
                       lecturas=len(valores),minimo_m=min(valores) if valores else "",
                       mediana_m=float(np.median(valores)) if valores else "",
                       maximo_m=max(valores) if valores else "")


def actualizar_tablas(episodios, resumen, pares, pendientes, transiciones):
    def decimal(x, n=2):
        return f"{float(x):.{n}f}".replace(".", ",") if x != "" else "—"

    def tabla(lineas, encabezado, filas):
        lineas.extend(("| " + " | ".join(encabezado) + " |",
                       "|" + "|".join("---" for _ in encabezado) + "|"))
        lineas.extend("| " + " | ".join(map(str, f)) + " |" for f in filas)
        lineas.append("")

    def sumar(ff, k):
        return sum(int(f[k]) for f in ff)

    archivo = SALIDA / "INFORME_COMPLETO_UMARS.md"
    if not archivo.exists():
        return
    datos = {(f["politica"], f["semilla"]): f for f in resumen}
    lineas = [
        f"**Evaluación en escenarios nuevos:** {len(resumen)} de 15 corridas completas, "
        f"{sum(f['escenarios'] for f in resumen)} episodios observados; "
        f"{len(pendientes)} corridas pendientes.", "",
        "### Entrenamiento registrado", "",
    ]
    entrenamientos = []
    for p in POLITICAS[:4]:
        for s in SEMILLAS:
            ff = [f for f in episodios if f["politica_informe"]==p and f["semilla_corrida"]==s
                  and f["fase"]=="ENTRENAMIENTO"]
            if not ff:
                continue
            entrenamientos.append((
                p,s,len(ff),sumar(ff,"llegadas"),sumar(ff,"vetos_borde"),
                sumar(ff,"contactos_rocas"),sumar(ff,"sin_acciones_seguras"),
                sumar(ff,"max_acciones"),decimal(mean(float(f["retorno_base"]) for f in ff)),
                decimal(mean(float(f["retorno_entrenamiento"]) for f in ff)),
            ))
    tabla(lineas, ("Política","Semilla","Episodios","Metas","Vetos borde","Contactos",
                   "Bloqueos","Límites","Retorno base medio","Retorno Q medio"), entrenamientos)
    lineas.extend(["### Evaluación por política y semilla", ""])
    filas = []
    for p in POLITICAS:
        for s in SEMILLAS:
            d=datos.get((p,s))
            filas.append((p,s,*((
                f"{d['llegadas']}/{d['escenarios']}", d["vetos_borde"], d["contactos_rocas"],
                d["sin_acciones_seguras"],d["max_acciones"],d["acciones_ejecutadas"],
                d["giros_ejecutados"],decimal(d["distancia_recorrida_m_medio"]),
                decimal(d["tiempo_simulado_s_medio"]),decimal(d["retorno_base_medio"]),
            ) if d else ("pendiente",*("—",)*9))))
    tabla(lineas, ("Política","Semilla","Llegadas","Vetos borde","Contactos","Bloqueos","Límites",
                   "Acciones ejecutadas","Giros puros ejecutados","Distancia media (m)",
                   "Tiempo medio (s)","Retorno base medio"),filas)
    totales=[]
    for p in POLITICAS:
        ff=[f for f in resumen if f["politica"]==p]
        if ff:
            totales.append((p,len(ff), f"{sumar(ff,'llegadas')}/{sumar(ff,'escenarios')}",
                            sumar(ff,"contactos_rocas"),sumar(ff,"sin_acciones_seguras")))
    tabla(lineas, ("Política","Semillas medidas","Llegadas observadas","Contactos","Bloqueos"),totales)
    lineas.extend(["### Eficiencia y llegadas exclusivas", ""])
    filas = [
        (f["izquierda"],f["derecha"],f["escenarios"],f["llegadas_compartidas"],
         f"{decimal(f['acciones_ejecutadas_izquierda'])} / {decimal(f['acciones_ejecutadas_derecha'])}",
         f"{decimal(f['giros_ejecutados_izquierda'])} / {decimal(f['giros_ejecutados_derecha'])}",
         f"{f['perdidos']} / {f['recuperados']}")
        for f in pares if f["semilla"]=="total"
    ]
    tabla(lineas, ("Primera política","Segunda política","Escenarios comparables","Llegadas compartidas",
                   "Acciones medias","Giros medios","Llegadas exclusivas"),filas)
    lineas.extend([
        "Los promedios y las llegadas exclusivas siguen el orden primera / segunda. El CSV pareado incluye "
        "el desglose por semilla. Los totales de políticas con distinto número de escenarios no se usan para atribuir diferencias.",
        "", "### Cobertura de sensores y casos seleccionados", "",
    ])
    cobertura = Counter(t["fuente"] for t in transiciones if t.get("rgbd_min_franja_m"))
    lineas.extend([
        f"Hay {len(transiciones)} filas de transición exportadas y {sum(cobertura.values())} con mínimo RGB-D "
        f"registrado, de {len(cobertura)} corridas. Las banderas fusionadas y el mínimo LiDAR se conservan de acuerdo con el CSV original.",
        "",
    ])
    casos=DATOS/"casos_representativos.csv"
    if casos.is_file():
        tabla(lineas, ("Caso","Política","Semilla de escenario","Resultado","Acciones","Giros",
                       "Distancia (m)","Tiempo (s)"),
              ((f["caso"],f["politica"],f["semilla_escenario"],f["resultado"],f["acciones"],f["giros"],
                decimal(f["distancia_recorrida_m"]),decimal(f["tiempo_simulado_s"])) for f in leer_csv(casos)))
    lineas.extend([
        "[Evaluación consolidada](datos/consolidado_evaluacion.csv) · "
        "[Eficiencia por semilla](datos/eficiencia_pareada.csv) · "
        "[Casos pendientes](datos/pendientes.csv) · [Estados visitados](datos/estados_visitados.csv)", "",
    ])
    texto=archivo.read_text(encoding="utf-8")
    inicio, fin = "<!-- RESULTADOS_INICIO -->", "<!-- RESULTADOS_FIN -->"
    cabecera, resto = texto.split(inicio,1)
    _, pie = resto.split(fin,1)
    analisis = []
    clave_pares = {(r["izquierda"],r["derecha"]):r for r in pares if r["semilla"]=="total"}
    for a,b in (("C histórica","C nueva"),("D histórica","D nueva"),("C nueva","D nueva"),
                ("C nueva","Reglas"),("D nueva","Reglas")):
        r=clave_pares.get((a,b))
        if r is None:
            continue
        analisis.append(f"- **{a} y {b}.** En {r['escenarios']} escenarios pareados, "
                        f"llegaron {r['llegadas_izquierda']} y {r['llegadas_derecha']} veces. "
                        f"Las llegadas exclusivas fueron {r['perdidos']} y {r['recuperados']}. "
                        f"En las {r['llegadas_compartidas']} llegadas compartidas, "
                        f"los promedios de acciones fueron {decimal(r['acciones_ejecutadas_izquierda'])} y "
                        f"{decimal(r['acciones_ejecutadas_derecha'])}, y los de giros puros "
                        f"{decimal(r['giros_ejecutados_izquierda'])} y {decimal(r['giros_ejecutados_derecha'])}.")
    ini_a,fin_a="<!-- ANALISIS_INICIO -->","<!-- ANALISIS_FIN -->"
    if ini_a in pie:
        antes_a,resto_a=pie.split(ini_a,1)
        _,despues_a=resto_a.split(fin_a,1)
        pie=antes_a+ini_a+"\n"+"\n".join(analisis)+"\n"+fin_a+despues_a
    archivo.write_text(cabecera+inicio+"\n"+"\n".join(lineas)+fin+pie,encoding="utf-8")


def main():
    DATOS.mkdir(parents=True,exist_ok=True);GRAFICAS.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"axes.spines.top":False,"axes.spines.right":False,"axes.grid":True,
                         "grid.alpha":.20,"axes.axisbelow":True,"font.size":10})
    episodios,transiciones,configs,actual,pendientes=reunir()
    resumen,pares,exclusivos=comparar(actual)
    csv_guardar("episodios.csv",episodios);csv_guardar("transiciones.csv",transiciones)
    csv_guardar("configuraciones.csv",configs)
    csv_guardar("cambios_q_entrenamiento.csv",cambios_q(episodios,transiciones),
                ("fuente","etapa","politica","semilla","episodio","paso","estado","accion",
                 "terminal_q","epsilon","q_previo","max_q_siguiente","objetivo","delta_q","q_actualizado"))
    csv_guardar("consolidado_evaluacion.csv",resumen);csv_guardar("eficiencia_pareada.csv",pares)
    csv_guardar("llegadas_exclusivas.csv",exclusivos,
                ("semilla","escenario","izquierda","derecha","resultado_izquierda","resultado_derecha"))
    csv_guardar("pendientes.csv",pendientes,("politica","semilla","modo"))
    visitas=Counter((t["fuente"],t["fase"],t["estado"]) for t in transiciones if t["estado"])
    csv_guardar("estados_visitados.csv",[dict(fuente=f,fase=p,estado=s,visitas=n)
                                       for (f,p,s),n in sorted(visitas.items())])
    csv_guardar("cobertura_sensores.csv",resumir_sensores(transiciones),
                ("fuente","fase","medida","decisiones","lecturas","minimo_m","mediana_m","maximo_m"))
    seguridad_validada();aprendizaje(episodios);evaluacion(resumen,pares);navegacion(actual)
    for nombre, origen in (
        ("rescate_102061.csv", BASE/"aprendizaje_borde_v8"/"rescate_102061.csv"),
        ("experimentos_pre_v8.csv", BASE/"resumen_experimentos_umars.csv"),
        ("experimentos_v8_iniciales.csv", BASE/"experimentos_v8"/"resumen_corridas.csv"),
        ("validacion_borde_previa_episodios.csv", BASE/"validacion_borde_v8"/"episodios.csv"),
        ("validacion_borde_previa_recuperados.csv", BASE/"validacion_borde_v8"/"recuperados.csv"),
    ):
        (DATOS / nombre).write_bytes(origen.read_bytes())
    actualizar_tablas(episodios,resumen,pares,pendientes,transiciones)
    print(f"{len(episodios)} episodios, {len(transiciones)} transiciones y {len(pendientes)} corridas pendientes.")
    print(SALIDA)

if __name__ == "__main__":
    main()
