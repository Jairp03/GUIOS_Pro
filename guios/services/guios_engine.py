"""Lógica de GUIOS (pasos 1 a 6), tomada del programa original GUIOS PRO.

Niveles de importancia: 0 Irrelevante, 1 Opcional, 2 Importante, 3 Fundamental.
Subfactores: puntaje de 1 (No cumple) a 4 (Cumple).
"""
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
from statistics import median_low

from django.db import transaction
from django.utils import timezone

from ..models import (AccionSugerida, Factor, Evaluacion, ResultadoEvaluacion, ResultadoFactor, Subfactor,
                      ValoracionFactor, ValoracionSubfactor, NIVELES)

RECOMENDACIONES = {
    "C": ("Recomendación C: La organización debe proporcionar los recursos necesarios que garanticen una "
          "adopción satisfactoria. Si se trata de factores internos deben ser aspectos a mejorar dentro de la "
          "organización y si son factores externos, dedicar recursos de ingeniería para mejorar el software."),
    "B": ("Recomendación B: Es posible adoptar. A pesar de que se han detectado amenazas y/o debilidades en "
          "factores cuya importancia relativa es opcional, se sugiere revisar los criterios que no cumplen con "
          "lo mínimo requerido para adoptar."),
    "A": ("Recomendación A: Adoptar. Todos los factores han sido identificados como oportunidades y/o "
          "fortalezas. Esto quiere decir que la organización cumple satisfactoriamente con la mayoría de "
          "requisitos para adoptar la solución FLOSS."),
}


# ---- Pasos 1 y 2 ---------------------------------------------------------
def importancia_relativa(sugerida: int, decisor: int) -> int:
    """Paso 1: promedio de la IS y de la importancia del decisor, redondeado hacia abajo."""
    return (int(sugerida) + int(decisor)) // 2


def es_relevante(ir: int) -> bool:
    """Paso 2: un factor es relevante si su importancia relativa no es Irrelevante."""
    return int(ir) > 0


# ---- Pasos 3 a 5 ---------------------------------------------------------
def ponderacion_media(puntajes):
    puntajes = list(puntajes)
    return sum(puntajes) / len(puntajes) if puntajes else None


def clasificar_foda(alcance: str, pm: float) -> str:
    positivo = pm >= 3
    if alcance == "Interno":
        return "Fortaleza" if positivo else "Debilidad"
    return "Oportunidad" if positivo else "Amenaza"


def _agregar(valores, criterio):
    valores = list(valores)
    if not valores:
        return None
    if criterio == "MEDIANA":
        return median_low(valores)
    return sum(valores) / len(valores)


def _redondear(x):
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---- Paso 6 --------------------------------------------------------------
def decision_por_conteo(buenos: int, malos: int) -> str:
    if buenos > malos:
        return (f"Adoptar, pues la cantidad de factores identificados como Fortalezas u Oportunidades "
                f"({buenos}) supera a los identificados como Debilidades o Amenazas ({malos}).")
    if buenos < malos:
        return (f"No adoptar, pues la cantidad de factores identificados como Debilidades o Amenazas "
                f"({malos}) supera a los identificados como Fortalezas u Oportunidades ({buenos}).")
    return (f"Se deben considerar otros factores no analizados por GUIOS, pues existe la misma cantidad "
            f"({buenos}) de factores identificados como Fortalezas u Oportunidades y como Debilidades o Amenazas.")


def tipo_recomendacion(filas) -> str:
    """C si hay debilidad/amenaza con importancia Importante o Fundamental; B si solo Opcional; A si no hay."""
    tipo = "A"
    for f in filas:
        if f["clasificacion"] in ("Debilidad", "Amenaza"):
            if f["ir"] >= 2:
                return "C"
            tipo = "B"
    return tipo


# ---- Consolidación -------------------------------------------------------
def usuarios_considerados(evaluacion, solo_enviados=True, preliminar_de=None):
    """Decisores cuyas valoraciones cuentan: los que ya enviaron; si nadie envió y se pide un resultado
    preliminar, solo el decisor indicado; y si no, todos los participantes."""
    ps = list(evaluacion.participantes.values_list("usuario_id", "enviado"))
    enviados = [u for u, e in ps if e]
    if solo_enviados and enviados:
        return enviados
    if preliminar_de is not None:
        return [preliminar_de]
    return [u for u, _ in ps]


def calcular(evaluacion: Evaluacion, usuarios=None, preliminar_de=None):
    """Calcula (sin guardar) el resultado de una evaluación para los usuarios indicados."""
    usuarios = list(usuarios) if usuarios is not None else usuarios_considerados(evaluacion, preliminar_de=preliminar_de)
    vf = ValoracionFactor.objects.filter(evaluacion=evaluacion, usuario_id__in=usuarios)
    por_factor = {}
    for v in vf:
        por_factor.setdefault(v.factor_id, []).append(v)
    vs = ValoracionSubfactor.objects.filter(evaluacion=evaluacion, usuario_id__in=usuarios).select_related("subfactor")
    sub_por_usuario = {}
    for v in vs:
        sub_por_usuario.setdefault((v.subfactor.factor_id, v.usuario_id), []).append(v.puntaje)

    filas, buenos, malos = [], 0, 0
    cuentas = OrderedDict((k, 0) for k in ("Fortaleza", "Oportunidad", "Debilidad", "Amenaza"))
    factores = Factor.objects.filter(activo=True).select_related("dimension")
    for factor in factores:
        regs = por_factor.get(factor.id)
        fila = {"factor": factor, "dimension": factor.dimension.nombre, "alcance": factor.alcance,
                "sugerida": factor.importancia_sugerida, "decisor": None, "ir": None,
                "relevante": False, "pm": None, "clasificacion": "", "estado": "sin_valorar"}
        if regs:
            fila["sugerida"] = regs[0].importancia_sugerida_usada
            dec = _redondear(_agregar([r.importancia_decisor for r in regs], evaluacion.criterio))
            fila["decisor"] = dec
            fila["ir"] = importancia_relativa(fila["sugerida"], dec)
            fila["relevante"] = es_relevante(fila["ir"])
            if factor.alcance == "Ambos":
                elegidos = [r.alcance_definido for r in regs if r.alcance_definido]
                fila["alcance"] = max(set(elegidos), key=elegidos.count) if elegidos else "Externo"
            if not fila["relevante"]:
                fila["estado"] = "no_relevante"
            else:
                pms = [ponderacion_media(sub_por_usuario[(factor.id, u)]) for u in usuarios
                       if (factor.id, u) in sub_por_usuario]
                pm = _agregar(pms, evaluacion.criterio)
                if pm is None:
                    fila["estado"] = "pendiente"
                else:
                    fila["pm"] = round(float(pm), 2)
                    fila["clasificacion"] = clasificar_foda(fila["alcance"], fila["pm"])
                    fila["estado"] = "evaluado"
                    cuentas[fila["clasificacion"]] += 1
                    if fila["clasificacion"] in ("Fortaleza", "Oportunidad"):
                        buenos += 1
                    else:
                        malos += 1
        filas.append(fila)

    evaluadas = [f for f in filas if f["estado"] == "evaluado"]
    tipo = tipo_recomendacion(evaluadas) if evaluadas else ""
    acciones = []
    malos_ids = [f["factor"].id for f in evaluadas if f["clasificacion"] in ("Debilidad", "Amenaza")]
    por_accion = {}
    if malos_ids:
        for a in AccionSugerida.objects.filter(activo=True, factor_id__in=malos_ids):
            por_accion.setdefault(a.factor_id, []).append(a)
    for f in evaluadas:
        if f["clasificacion"] in ("Debilidad", "Amenaza"):
            for a in por_accion.get(f["factor"].id, []):
                if a.aplica_a == "AMB" or (a.aplica_a == "DEB") == (f["clasificacion"] == "Debilidad"):
                    acciones.append({"factor": f["factor"].nombre, "tipo": f["clasificacion"], "texto": a.descripcion})
    return {
        "filas": filas, "cuentas": dict(cuentas), "buenos": buenos, "malos": malos,
        "decision": decision_por_conteo(buenos, malos) if evaluadas else "",
        "tipo": tipo, "recomendacion": RECOMENDACIONES.get(tipo, ""), "acciones": acciones,
        "n_relevantes": sum(1 for f in filas if f["relevante"]),
        "n_valorados": sum(1 for f in filas if f["ir"] is not None),
        "n_evaluados": len(evaluadas), "usuarios": usuarios,
        "adoptable": bool(evaluadas) and buenos > malos,
    }


@transaction.atomic
def finalizar(evaluacion: Evaluacion):
    """Cierra la etapa: consolida las valoraciones y guarda el resultado (HU-09, HU-10)."""
    r = calcular(evaluacion)
    evaluacion.resultados_factor.all().delete()
    ResultadoFactor.objects.bulk_create([
        ResultadoFactor(evaluacion=evaluacion, factor=f["factor"], alcance_aplicado=f["alcance"],
                        importancia_relativa=f["ir"], pm=f["pm"], clasificacion=f["clasificacion"])
        for f in r["filas"] if f["ir"] is not None])
    ResultadoEvaluacion.objects.update_or_create(
        evaluacion=evaluacion,
        defaults=dict(decision=r["decision"], tipo_recomendacion=r["tipo"], recomendacion=r["recomendacion"],
                      fortalezas=r["cuentas"]["Fortaleza"], oportunidades=r["cuentas"]["Oportunidad"],
                      debilidades=r["cuentas"]["Debilidad"], amenazas=r["cuentas"]["Amenaza"],
                      adoptable=r["adoptable"]))
    evaluacion.estado = "FINAL"
    evaluacion.fecha_finalizacion = timezone.now()
    evaluacion.save(update_fields=["estado", "fecha_finalizacion"])
    from . import ia_importancia
    ia_importancia.invalidar_cache()
    return r


def nivel(n):
    return NIVELES[n] if n is not None else "—"
