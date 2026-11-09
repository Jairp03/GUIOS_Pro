"""Propuesta de mejora: importancia sugerida (IS) asistida por IA.

Problema: en GUIOS la IS es fija (viene de la literatura y de una encuesta a expertos) y es igual
para todas las organizaciones. Este módulo propone una IS que aprende de las evaluaciones reales.

Método 1 (HISTORIAL, no requiere servicios externos): estimación bayesiana con ponderación.
  - Cada valoración de un decisor en una evaluación finalizada es una observación x (0 a 3).
  - Peso de cada observación: w = recencia * similitud.
      recencia  = 0.5 ** (días / 180)            (las evaluaciones recientes pesan más)
      similitud = 1.0 si coincide el sector (0.4 si no) * 1.0 si coincide el tamaño (0.6 si no)
  - IS_nueva = (K * IS_base + sum(w * x)) / (K + sum(w)),  con K = 5 (fuerza de la IS de la tesis).
  - Confianza = sum(w) / (sum(w) + K). Con pocos datos la IS casi no cambia (arranque en frío).
Método 2 (LLM, opcional): un modelo de lenguaje propone la IS según el perfil de la organización.

Toda propuesta queda PENDIENTE hasta que un Administrador la apruebe (humano en el circuito).
"""
import json
import math
from collections import defaultdict
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from ..models import (Factor, HistorialIS, PropuestaIS, ValoracionFactor, NIVELES, SECTORES, TAMANOS)

K_PRIOR = 5.0
VIDA_MEDIA_DIAS = 180.0
MIN_PESO = 1.0  # peso mínimo acumulado para emitir una propuesta
SECTOR_NOMBRES = dict(SECTORES)
TAMANO_NOMBRES = dict(TAMANOS)


def _peso(obs_fecha, obs_sector, obs_tamano, sector, tamano, ahora):
    dias = max((ahora - obs_fecha).total_seconds() / 86400.0, 0.0)
    w = 0.5 ** (dias / VIDA_MEDIA_DIAS)
    if sector:
        w *= 1.0 if obs_sector == sector else 0.4
    if tamano:
        w *= 1.0 if obs_tamano == tamano else 0.6
    return w


def _observaciones(usar_cache=True):
    """Todas las valoraciones de factores de evaluaciones finalizadas (una sola consulta; se guarda 2 minutos)."""
    obs = cache.get("is_obs") if usar_cache else None
    if obs is None:
        obs = list(ValoracionFactor.objects.filter(evaluacion__estado="FINAL").values_list(
            "factor_id", "importancia_decisor", "evaluacion__fecha_finalizacion", "evaluacion__sector", "evaluacion__tamano"))
        if usar_cache:
            cache.set("is_obs", obs, 120)
    return obs


def invalidar_cache():
    cache.delete("is_obs")


def _calcular(base, obs, sector, tamano, ahora):
    sw = swx = 0.0
    for _fid, x, fecha, s, t in obs:
        w = _peso(fecha or ahora, s, t, sector, tamano, ahora)
        sw += w
        swx += w * x
    if sw < MIN_PESO:
        return None
    valor = (K_PRIOR * base + swx) / (K_PRIOR + sw)
    return {"valor": valor, "nivel": min(3, max(0, int(math.floor(valor + 0.5)))), "media": swx / sw,
            "confianza": sw / (sw + K_PRIOR), "n": len(obs), "peso": sw}


def estimar_todos(sector=None, tamano=None, factores=None, usar_cache=False, ahora=None):
    """Estimación de la IS de todos los factores: {factor_id: dict}. Los factores sin datos suficientes no aparecen."""
    ahora = ahora or timezone.now()
    factores = factores if factores is not None else list(Factor.objects.filter(activo=True))
    por_factor = defaultdict(list)
    for o in _observaciones(usar_cache):
        por_factor[o[0]].append(o)
    out = {}
    for f in factores:
        est = _calcular(f.importancia_base, por_factor.get(f.id, []), sector, tamano, ahora)
        if est:
            out[f.id] = est
    return out


def estimar_factor(factor, sector=None, tamano=None, ahora=None):
    """Estimación de un solo factor, o None si no hay datos suficientes."""
    return estimar_todos(sector, tamano, [factor], usar_cache=False, ahora=ahora).get(factor.id)


def _texto_perfil(sector, tamano):
    partes = []
    if sector:
        partes.append(f"sector {SECTOR_NOMBRES.get(sector, sector).lower()}")
    if tamano:
        partes.append(f"organización {TAMANO_NOMBRES.get(tamano, tamano).split(' (')[0].lower()}")
    return " y ".join(partes) if partes else "todas las organizaciones"


def justificar(factor, est, sector, tamano):
    base = NIVELES[factor.importancia_base]
    media_n = NIVELES[min(3, max(0, int(math.floor(est["media"] + 0.5))))]
    return (f"Con {est['n']} valoraciones de decisores (peso efectivo {est['peso']:.1f}) para {_texto_perfil(sector, tamano)}, "
            f"el promedio fue {est['media']:.2f} ({media_n}). La IS original de la tesis es {base}. "
            f"Se combinaron ambas con una confianza del {est['confianza']:.0%}.")


def niveles_para_evaluacion(sector, tamano):
    """IS que se usa en una evaluación con «IS ajustada por IA»: {factor_id: nivel}, con una sola consulta."""
    factores = list(Factor.objects.filter(activo=True))
    ests = estimar_todos(sector, tamano, factores, usar_cache=True)
    return {f.id: (ests[f.id]["nivel"] if f.id in ests else f.importancia_sugerida) for f in factores}


@transaction.atomic
def generar_propuestas_historial(sector=None, tamano=None):
    """Crea propuestas PENDIENTES para los factores cuya IS cambiaría. Devuelve la lista creada."""
    creadas = []
    factores = list(Factor.objects.filter(activo=True))
    ests = estimar_todos(sector, tamano, factores)
    pendientes = set(PropuestaIS.objects.filter(estado="PEND").values_list("factor_id", "nivel_propuesto"))
    for factor in factores:
        est = ests.get(factor.id)
        if est is None or est["nivel"] == factor.importancia_sugerida:
            continue
        if (factor.id, est["nivel"]) in pendientes:
            continue
        creadas.append(PropuestaIS.objects.create(
            factor=factor, metodo="HISTORIAL", nivel_actual=factor.importancia_sugerida,
            valor_propuesto=Decimal(f"{est['valor']:.2f}"), nivel_propuesto=est["nivel"],
            confianza=Decimal(f"{est['confianza']:.2f}"), n_observaciones=est["n"],
            media_historial=Decimal(f"{est['media']:.2f}"),
            justificacion=justificar(factor, est, sector, tamano), sector=sector or "", tamano=tamano or ""))
    return creadas


# ---------------- Método 2: modelo de lenguaje (opcional) ----------------
class ErrorIA(Exception):
    pass


def _llamar_claude(prompt):
    if not settings.ANTHROPIC_API_KEY:
        raise ErrorIA("No hay ANTHROPIC_API_KEY configurada en el archivo .env.")
    cuerpo = json.dumps({
        "model": settings.CLAUDE_MODEL, "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=cuerpo, method="POST",
        headers={"content-type": "application/json", "x-api-key": settings.ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ErrorIA(f"La API respondió con error {e.code}.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorIA("No se pudo conectar con la API de IA.") from e
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _extraer_json(texto):
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini < 0 or fin < ini:
        raise ErrorIA("La respuesta de la IA no tiene el formato esperado.")
    try:
        return json.loads(texto[ini:fin + 1])
    except json.JSONDecodeError as e:
        raise ErrorIA("La respuesta de la IA no es un JSON válido.") from e


@transaction.atomic
def generar_propuestas_llm(sector, tamano, llamar=_llamar_claude):
    """Pide a un LLM una IS por factor según el perfil de la organización. Crea propuestas PENDIENTES."""
    factores = list(Factor.objects.filter(activo=True))
    lista = "\n".join(f"- {f.nombre} (dimensión {f.dimension.nombre}, alcance {f.alcance}, "
                      f"IS actual: {NIVELES[f.importancia_sugerida]})" for f in factores)
    prompt = (
        "Eres un experto en adopción de software libre y de fuentes abiertas (FLOSS). Para una organización con "
        f"perfil: {_texto_perfil(sector, tamano)}, propone la importancia sugerida de cada factor del método GUIOS. "
        "Niveles: 0=Irrelevante, 1=Opcional, 2=Importante, 3=Fundamental.\n"
        f"Factores:\n{lista}\n\n"
        'Responde SOLO con un JSON de la forma {"factores": [{"factor": "nombre exacto", "nivel": 0-3, '
        '"confianza": 0-1, "justificacion": "una frase"}]}. Incluye únicamente los factores cuyo nivel '
        "propuesto difiere del actual.")
    datos = _extraer_json(llamar(prompt))
    por_nombre = {f.nombre: f for f in factores}
    creadas = []
    for item in datos.get("factores", []):
        f = por_nombre.get(item.get("factor"))
        try:
            nivel = int(item.get("nivel"))
        except (TypeError, ValueError):
            continue
        if f is None or not 0 <= nivel <= 3 or nivel == f.importancia_sugerida:
            continue
        try:
            conf = min(1.0, max(0.0, float(item.get("confianza", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        creadas.append(PropuestaIS.objects.create(
            factor=f, metodo="LLM", nivel_actual=f.importancia_sugerida, valor_propuesto=Decimal(nivel),
            nivel_propuesto=nivel, confianza=Decimal(f"{conf:.2f}"), n_observaciones=0,
            justificacion=str(item.get("justificacion", ""))[:600], sector=sector or "", tamano=tamano or ""))
    return creadas


# ---------------- Revisión por el Administrador ----------------
@transaction.atomic
def aprobar(propuesta, usuario):
    f = propuesta.factor
    anterior = f.importancia_sugerida
    f.importancia_sugerida = propuesta.nivel_propuesto
    f.save(update_fields=["importancia_sugerida"])
    HistorialIS.objects.create(factor=f, nivel_anterior=anterior, nivel_nuevo=propuesta.nivel_propuesto,
                               origen=f"IA: {propuesta.get_metodo_display()}", justificacion=propuesta.justificacion,
                               usuario=usuario)
    propuesta.estado, propuesta.revisada_por, propuesta.revisada_en = "APRO", usuario, timezone.now()
    propuesta.save(update_fields=["estado", "revisada_por", "revisada_en"])


def rechazar(propuesta, usuario):
    propuesta.estado, propuesta.revisada_por, propuesta.revisada_en = "RECH", usuario, timezone.now()
    propuesta.save(update_fields=["estado", "revisada_por", "revisada_en"])


@transaction.atomic
def restaurar_base(factor, usuario):
    if factor.importancia_sugerida == factor.importancia_base:
        return
    HistorialIS.objects.create(factor=factor, nivel_anterior=factor.importancia_sugerida,
                               nivel_nuevo=factor.importancia_base, origen="Restaurar IS de la tesis", usuario=usuario)
    factor.importancia_sugerida = factor.importancia_base
    factor.save(update_fields=["importancia_sugerida"])
