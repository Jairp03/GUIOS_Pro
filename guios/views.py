from collections import Counter
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (AccionForm, AlternativaForm, EvaluacionForm, FactorForm, SubfactorForm, UsuarioForm)
from .models import (AccionSugerida, Alternativa, Dimension, Evaluacion, Factor, HistorialIS, NIVELES, ResultadoEvaluacion,
                     NIVELES_SUB, NIVELES_SUB_CORTOS, Participante, Perfil, PropuestaIS, SECTORES, Subfactor,
                     TAMANOS, ValoracionFactor, ValoracionSubfactor)
from .services import guios_engine as engine
from .services import ia_importancia as ia

User = get_user_model()


# ---------------------------------------------------------------- utilidades
def rol_de(user):
    """Rol del usuario sin consultas extra: el perfil llega junto con el usuario (ver backends.py)."""
    if user.is_superuser:
        return "ADMIN"
    rol = getattr(user, "_rol", None)
    if rol is None:
        try:
            rol = user.perfil.rol
        except Perfil.DoesNotExist:
            rol = Perfil.objects.get_or_create(usuario=user)[0].rol
        user._rol = rol
    return rol


def es_admin(user):
    return user.is_authenticated and rol_de(user) == "ADMIN"


def admin_requerido(vista):
    @login_required
    def envoltura(request, *a, **kw):
        if not es_admin(request.user):
            messages.error(request, "Esta sección es solo para Administradores.")
            return redirect("dashboard")
        return vista(request, *a, **kw)
    envoltura.__name__ = vista.__name__
    return envoltura


def evaluacion_permitida(request, pk, participante=False):
    """Devuelve la evaluación si el usuario puede verla. Con participante=True exige que sea decisor de ella."""
    ev = get_object_or_404(Evaluacion.objects.select_related("alternativa", "creador"), pk=pk)
    user = request.user
    es_creador = ev.creador_id == user.id
    if not (es_creador or es_admin(user) or ev.participantes.filter(usuario=user).exists()):
        raise Http404()
    if participante and not es_creador and not ev.participantes.filter(usuario=user).exists():
        raise Http404()
    return ev


def mis_evaluaciones(user):
    qs = Evaluacion.objects.select_related("alternativa", "creador")
    if es_admin(user):
        return qs
    return qs.filter(Q(participantes__usuario=user) | Q(creador=user)).distinct()


def progreso_usuarios(ev, ids):
    """Avance de varios decisores con 3 consultas en total (no una por decisor)."""
    ids = list(ids)
    relevantes = {i: set() for i in ids}
    hay_paso1 = {i: False for i in ids}
    for uid, fid, rel in ValoracionFactor.objects.filter(evaluacion=ev, usuario_id__in=ids).values_list("usuario_id", "factor_id", "relevante"):
        hay_paso1[uid] = True
        if rel:
            relevantes[uid].add(fid)
    contestadas = {(u, f): n for u, f, n in ValoracionSubfactor.objects.filter(evaluacion=ev, usuario_id__in=ids)
                   .values_list("usuario_id", "subfactor__factor_id").annotate(n=Count("id"))}
    totales = dict(Subfactor.objects.filter(activo=True).values_list("factor_id").annotate(n=Count("id")))
    out = {}
    for i in ids:
        rel = relevantes[i]
        completos = sum(1 for f in rel if totales.get(f) and contestadas.get((i, f), 0) >= totales[f])
        out[i] = {"paso1": hay_paso1[i], "relevantes": len(rel), "completos": completos,
                  "paso3": bool(rel) and completos == len(rel),
                  "pct": int(100 * completos / len(rel)) if rel else (0 if not hay_paso1[i] else 100)}
    return out


def progreso(ev, user):
    return progreso_usuarios(ev, [user.id])[user.id]


# ---------------------------------------------------------------- acceso
def ingresar(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    error = ""
    if request.method == "POST":
        correo = request.POST.get("correo", "").strip().lower()
        user = authenticate(request, username=correo, password=request.POST.get("password", ""))
        if user is not None and user.is_active:
            login(request, user)
            return redirect(request.GET.get("next") or "dashboard")
        error = "Correo o contraseña incorrectos."
    return render(request, "guios/login.html", {"error": error})


@login_required
def dashboard(request):
    evs = mis_evaluaciones(request.user)
    ids = evs.values("id")
    cuentas = Evaluacion.objects.filter(id__in=ids).aggregate(
        total=Count("id"), finales=Count("id", filter=Q(estado="FINAL")), proceso=Count("id", filter=Q(estado="PROCESO")))
    res = ResultadoEvaluacion.objects.filter(evaluacion_id__in=ids).aggregate(
        f=Sum("fortalezas"), o=Sum("oportunidades"), d=Sum("debilidades"), a=Sum("amenazas"),
        adoptables=Count("id", filter=Q(adoptable=True)))
    seis = timezone.now() - timedelta(days=183)
    por_mes = Counter(f.strftime("%Y-%m") for f in
                      Evaluacion.objects.filter(id__in=ids, fecha_creacion__gte=seis).values_list("fecha_creacion", flat=True))
    meses, cursor = [], timezone.now().replace(day=1)
    for _ in range(6):
        meses.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    meses.reverse()
    maximo = max([por_mes.get(m, 0) for m in meses] + [1])
    grafico = [{"mes": m[5:] + "/" + m[2:4], "n": por_mes.get(m, 0), "alto": int(100 * por_mes.get(m, 0) / maximo)} for m in meses]
    foda = {"Fortalezas": res["f"] or 0, "Oportunidades": res["o"] or 0, "Debilidades": res["d"] or 0, "Amenazas": res["a"] or 0}
    total_foda = sum(foda.values()) or 1
    foda_lista = [{"nombre": k, "n": v, "pct": round(100 * v / total_foda)} for k, v in foda.items()]
    adoptables, finales = res["adoptables"], cuentas["finales"]
    ctx = {
        "tarjetas": [
            {"titulo": "Evaluaciones", "valor": cuentas["total"], "icono": "chart", "tono": "navy"},
            {"titulo": "Alternativas", "valor": Alternativa.objects.count(), "icono": "box", "tono": "orange"},
            {"titulo": "Finalizadas", "valor": finales, "icono": "check", "tono": "green"},
            {"titulo": "Adoptables", "valor": adoptables, "icono": "rocket", "tono": "blue"}],
        "grafico": grafico, "foda": foda_lista, "recientes": list(evs[:5]),
        "pendientes_ia": PropuestaIS.objects.filter(estado="PEND").count() if es_admin(request.user) else 0,
        "en_proceso": cuentas["proceso"], "anillo": round(100 * adoptables / finales) if finales else 0,
    }
    return render(request, "guios/dashboard.html", ctx)


# ---------------------------------------------------------------- alternativas
@login_required
def alternativas(request):
    form = AlternativaForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("borrar"):
            alt = get_object_or_404(Alternativa, pk=request.POST["borrar"])
            if alt.evaluaciones.exists():
                messages.error(request, "No se puede eliminar: la alternativa ya tiene evaluaciones.")
            else:
                alt.delete(); messages.success(request, "Alternativa eliminada.")
            return redirect("alternativas")
        if form.is_valid():
            alt = form.save(commit=False); alt.creada_por = request.user; alt.save()
            messages.success(request, f"Alternativa «{alt.nombre}» guardada.")
            return redirect("alternativas")
    lista = Alternativa.objects.annotate(n=Count("evaluaciones"))
    return render(request, "guios/alternativas.html", {"form": form, "alternativas": lista})


# ---------------------------------------------------------------- evaluaciones
@login_required
def evaluacion_nueva(request):
    form = EvaluacionForm(request.POST or None, initial={"alternativa": request.GET.get("alternativa")})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        ev = Evaluacion.objects.create(alternativa=d["alternativa"], creador=request.user, sector=d["sector"],
                                       tamano=d["tamano"], usar_is_ia=d["usar_is_ia"], criterio=d["criterio"])
        Participante.objects.create(evaluacion=ev, usuario=request.user)
        desconocidos = []
        for correo in {c.strip().lower() for c in d["invitados"].replace("\n", ",").split(",") if c.strip()}:
            u = User.objects.filter(username__iexact=correo, is_active=True).first()
            if u and u != request.user:
                Participante.objects.get_or_create(evaluacion=ev, usuario=u)
            elif not u:
                desconocidos.append(correo)
        if desconocidos:
            messages.warning(request, "No se invitó a estos correos porque no tienen cuenta: " + ", ".join(desconocidos))
        messages.success(request, "Evaluación creada. Empieza por la importancia de los factores.")
        return redirect("importancia", pk=ev.pk)
    return render(request, "guios/evaluacion_nueva.html", {"form": form})


@login_required
def evaluacion_detalle(request, pk):
    ev = evaluacion_permitida(request, pk)
    partes = list(ev.participantes.select_related("usuario"))
    prog = progreso_usuarios(ev, [p.usuario_id for p in partes] + [request.user.id])
    equipo = [{"p": p, "prog": prog[p.usuario_id]} for p in partes]
    ctx = {"ev": ev, "equipo": equipo, "mio": prog[request.user.id],
           "puede_cerrar": (ev.creador_id == request.user.id or es_admin(request.user)) and not ev.finalizada,
           "mi_part": next((p for p in partes if p.usuario_id == request.user.id), None), "nivel_is": ev.usar_is_ia}
    return render(request, "guios/evaluacion_detalle.html", ctx)


@login_required
def importancia(request, pk):
    ev = evaluacion_permitida(request, pk, participante=True)
    factores = list(Factor.objects.filter(activo=True).select_related("dimension"))
    previas = {v.factor_id: v for v in ValoracionFactor.objects.filter(evaluacion=ev, usuario=request.user)}
    niveles_ia = ia.niveles_para_evaluacion(ev.sector, ev.tamano) if ev.usar_is_ia else None

    def sug_de(f):
        previa = previas.get(f.id)
        if previa:
            return previa.importancia_sugerida_usada
        return niveles_ia[f.id] if niveles_ia else f.importancia_sugerida

    if request.method == "POST":
        if ev.finalizada:
            messages.error(request, "La evaluación ya fue finalizada.")
            return redirect("evaluacion", pk=ev.pk)
        nuevos, cambiados = [], []
        for f in factores:
            try:
                dec = int(request.POST.get(f"f_{f.id}", ""))
                if not 0 <= dec <= 3:
                    raise ValueError
            except ValueError:
                messages.error(request, f"Falta calificar el factor «{f.nombre}».")
                return redirect("importancia", pk=ev.pk)
            sug = sug_de(f)
            ir = engine.importancia_relativa(sug, dec)
            alcance = request.POST.get(f"a_{f.id}", "") if f.alcance == "Ambos" else ""
            if alcance not in ("", "Interno", "Externo"):
                alcance = "Externo"
            previa = previas.get(f.id)
            if previa:
                previa.importancia_decisor, previa.importancia_relativa = dec, ir
                previa.relevante, previa.alcance_definido = engine.es_relevante(ir), alcance
                cambiados.append(previa)
            else:
                nuevos.append(ValoracionFactor(evaluacion=ev, factor=f, usuario=request.user, importancia_decisor=dec,
                                               importancia_sugerida_usada=sug, importancia_relativa=ir,
                                               relevante=engine.es_relevante(ir), alcance_definido=alcance))
        ValoracionFactor.objects.bulk_create(nuevos)
        ValoracionFactor.objects.bulk_update(cambiados, ["importancia_decisor", "importancia_relativa", "relevante", "alcance_definido"])
        Participante.objects.filter(evaluacion=ev, usuario=request.user).update(enviado=False, enviado_en=None)
        messages.success(request, "Importancia guardada. Ahora valora los subfactores.")
        return redirect("subfactores", pk=ev.pk)
    filas = []
    for f in factores:
        previa = previas.get(f.id)
        sug = sug_de(f)
        filas.append({"f": f, "sug": sug, "dec": previa.importancia_decisor if previa else sug,
                      "alcance": previa.alcance_definido if previa and previa.alcance_definido else "Externo"})
    dims = list(Dimension.objects.all())
    return render(request, "guios/importancia.html", {"ev": ev, "filas": filas, "dims": dims, "niveles": list(enumerate(NIVELES))})


@login_required
def subfactores(request, pk):
    ev = evaluacion_permitida(request, pk, participante=True)
    relevantes = list(ValoracionFactor.objects.filter(evaluacion=ev, usuario=request.user, relevante=True)
                      .select_related("factor", "factor__dimension"))
    if not relevantes:
        messages.warning(request, "Primero califica la importancia de los factores.")
        return redirect("importancia", pk=ev.pk)
    contestadas = Counter(ValoracionSubfactor.objects.filter(evaluacion=ev, usuario=request.user)
                          .values_list("subfactor__factor_id", flat=True))
    totales = dict(Subfactor.objects.filter(activo=True, factor_id__in=[v.factor_id for v in relevantes])
                   .values_list("factor_id").annotate(n=Count("id")))
    seleccionado = next((v for v in relevantes if str(v.factor_id) == request.GET.get("f")), None)
    if seleccionado is None:
        seleccionado = next((v for v in relevantes if contestadas.get(v.factor_id, 0) < totales.get(v.factor_id, 0)), relevantes[0])
    factor = seleccionado.factor
    subs = list(Subfactor.objects.filter(factor=factor, activo=True))
    previas = {v.subfactor_id: v for v in ValoracionSubfactor.objects.filter(evaluacion=ev, usuario=request.user, subfactor__factor=factor)}
    if request.method == "POST":
        if ev.finalizada:
            messages.error(request, "La evaluación ya fue finalizada.")
            return redirect("evaluacion", pk=ev.pk)
        nuevos = {}
        for s_ in subs:
            try:
                p = int(request.POST.get(f"s_{s_.id}", ""))
                if not 1 <= p <= 4:
                    raise ValueError
            except ValueError:
                messages.error(request, "Responde todos los subfactores antes de guardar.")
                return redirect(f"{request.path}?f={factor.id}")
            nuevos[s_.id] = p
        crear, cambiar = [], []
        for sid, p in nuevos.items():
            previa = previas.get(sid)
            if previa:
                previa.puntaje = p
                cambiar.append(previa)
            else:
                crear.append(ValoracionSubfactor(evaluacion=ev, subfactor_id=sid, usuario=request.user, puntaje=p))
        ValoracionSubfactor.objects.bulk_create(crear)
        ValoracionSubfactor.objects.bulk_update(cambiar, ["puntaje"])
        Participante.objects.filter(evaluacion=ev, usuario=request.user).update(enviado=False, enviado_en=None)
        pm = engine.ponderacion_media(nuevos.values())
        alcance = seleccionado.alcance_definido or (factor.alcance if factor.alcance != "Ambos" else "Externo")
        messages.success(request, f"«{factor.nombre}» guardado: ponderación media {pm:.2f} → {engine.clasificar_foda(alcance, pm)}.")
        pendiente = next((v for v in relevantes if v.factor_id != factor.id and
                          (contestadas.get(v.factor_id, 0) < totales.get(v.factor_id, 0))), None)
        return redirect(f"{request.path}?f={pendiente.factor_id}") if pendiente else redirect("evaluacion", pk=ev.pk)
    lista = [{"v": v, "hechos": contestadas.get(v.factor_id, 0), "total": totales.get(v.factor_id, 0),
              "ok": contestadas.get(v.factor_id, 0) >= totales.get(v.factor_id, 0), "activo": v.factor_id == factor.id} for v in relevantes]
    filas = [{"s": s_, "val": previas[s_.id].puntaje if s_.id in previas else None} for s_ in subs]
    opciones = list(zip(range(1, 5), NIVELES_SUB_CORTOS, NIVELES_SUB))
    return render(request, "guios/subfactores.html", {"ev": ev, "lista": lista, "factor": factor, "filas": filas,
                                                      "opciones": opciones, "sel": seleccionado})


@login_required
@require_POST
def enviar(request, pk):
    ev = evaluacion_permitida(request, pk)
    part = get_object_or_404(Participante, evaluacion=ev, usuario=request.user)
    if ev.finalizada:
        messages.error(request, "La evaluación ya fue finalizada.")
    elif not progreso(ev, request.user)["paso3"]:
        messages.error(request, "Completa los subfactores de todos tus factores relevantes antes de enviar.")
    else:
        part.enviado, part.enviado_en = True, timezone.now()
        part.save(update_fields=["enviado", "enviado_en"])
        messages.success(request, "Tus valoraciones fueron enviadas.")
    return redirect("evaluacion", pk=ev.pk)


@login_required
@require_POST
def consolidar(request, pk):
    ev = evaluacion_permitida(request, pk)
    if not (ev.creador_id == request.user.id or es_admin(request.user)):
        messages.error(request, "Solo el creador o un Administrador puede cerrar la etapa.")
    elif ev.finalizada:
        messages.info(request, "La evaluación ya estaba finalizada.")
    elif not ev.participantes.filter(enviado=True).exists():
        messages.error(request, "Al menos un decisor debe enviar sus valoraciones antes de consolidar.")
    else:
        engine.finalizar(ev)
        messages.success(request, "Etapa cerrada: las valoraciones se consolidaron en un resultado único.")
        return redirect("resultados", pk=ev.pk)
    return redirect("evaluacion", pk=ev.pk)


@login_required
def resultados(request, pk):
    ev = evaluacion_permitida(request, pk)
    r = engine.calcular(ev, preliminar_de=None if ev.finalizada else request.user.id)
    return render(request, "guios/resultados.html", {"ev": ev, "r": r, "preliminar": not ev.finalizada,
                                                     "niveles": NIVELES, "n_decisores": len(r["usuarios"])})


@login_required
def historial(request):
    q = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    qs = mis_evaluaciones(request.user).select_related("resultado").prefetch_related("participantes__usuario")
    if q:
        qs = qs.filter(alternativa__nombre__icontains=q)
    if fecha:
        try:
            d = datetime.strptime(fecha, "%Y-%m-%d").date()
            qs = qs.filter(fecha_creacion__date=d)
        except ValueError:
            messages.warning(request, "La fecha debe tener el formato AAAA-MM-DD.")
    return render(request, "guios/historial.html", {"evaluaciones": qs, "q": q, "fecha": fecha})


# ---------------------------------------------------------------- administración
@admin_requerido
def catalogo(request):
    dims = list(Dimension.objects.all())
    dim = next((d for d in dims if str(d.id) == request.GET.get("dim")), dims[0] if dims else None)
    if request.method == "POST":
        a = request.POST.get("accion")
        try:
            if a == "crear_factor":
                f = FactorForm(request.POST)
                if f.is_valid(): f.save(); messages.success(request, "Factor creado.")
                else: messages.error(request, "Revisa los datos del factor (¿ya existe en esa dimensión?).")
            elif a == "editar_factor":
                obj = get_object_or_404(Factor, pk=request.POST["id"]); f = FactorForm(request.POST, instance=obj)
                if f.is_valid():
                    f.save(); messages.success(request, "Factor actualizado.")
                else: messages.error(request, "Revisa los datos del factor.")
            elif a in ("baja_factor", "alta_factor"):
                obj = get_object_or_404(Factor, pk=request.POST["id"]); obj.activo = a == "alta_factor"; obj.save()
                messages.success(request, "Factor " + ("reactivado." if obj.activo else "dado de baja (se conserva el historial)."))
            elif a == "crear_sub":
                f = SubfactorForm(request.POST)
                if f.is_valid(): f.save(); messages.success(request, "Subfactor creado.")
                else: messages.error(request, "Revisa los datos del subfactor.")
            elif a in ("baja_sub", "alta_sub"):
                obj = get_object_or_404(Subfactor, pk=request.POST["id"]); obj.activo = a == "alta_sub"; obj.save()
                messages.success(request, "Subfactor actualizado.")
            elif a == "crear_accion":
                f = AccionForm(request.POST)
                if f.is_valid(): f.save(); messages.success(request, "Acción sugerida registrada.")
                else: messages.error(request, "Revisa los datos de la acción.")
            elif a == "borrar_accion":
                get_object_or_404(AccionSugerida, pk=request.POST["id"]).delete(); messages.success(request, "Acción eliminada.")
        except Exception as exc:  # noqa: BLE001 - mostrar un mensaje claro en lugar de un error 500
            messages.error(request, f"No se pudo completar la acción: {exc}")
        return redirect(f"{request.path}?dim={request.POST.get('dim_ret', dim.id if dim else '')}")
    factores = Factor.objects.filter(dimension=dim).annotate(
        n_sub=Count("subfactores", filter=Q(subfactores__activo=True))).prefetch_related("acciones") if dim else []
    ctx = {"dims": dims, "dim": dim, "factores": factores, "form_factor": FactorForm(initial={"dimension": dim}),
           "niveles": list(enumerate(NIVELES)), "ver": request.GET.get("ver")}
    if request.GET.get("ver"):
        ctx["factor_ver"] = get_object_or_404(Factor, pk=request.GET["ver"])
        ctx["subs"] = ctx["factor_ver"].subfactores.all()
    return render(request, "guios/catalogo.html", ctx)


@admin_requerido
def usuarios(request):
    form = UsuarioForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("toggle"):
            u = get_object_or_404(User, pk=request.POST["toggle"])
            if u == request.user:
                messages.error(request, "No puedes desactivar tu propia cuenta.")
            else:
                u.is_active = not u.is_active; u.save(); messages.success(request, "Estado del usuario actualizado.")
            return redirect("usuarios")
        if request.POST.get("cambiar_rol"):
            u = get_object_or_404(User, pk=request.POST["cambiar_rol"])
            p, _ = Perfil.objects.get_or_create(usuario=u)
            if request.POST.get("rol") in ("ADMIN", "DECISOR"):
                p.rol = request.POST["rol"]; p.save(); messages.success(request, "Rol actualizado.")
            return redirect("usuarios")
        if form.is_valid():
            d = form.cleaned_data
            u = User.objects.create_user(username=d["correo"], email=d["correo"], password=d["password"], first_name=d["nombre"])
            Perfil.objects.create(usuario=u, rol=d["rol"])
            messages.success(request, f"Usuario {d['correo']} creado.")
            return redirect("usuarios")
    lista = [{"u": u, "rol": rol_de(u)} for u in User.objects.select_related("perfil").order_by("first_name", "username")]
    return render(request, "guios/usuarios.html", {"form": form, "lista": lista})


@admin_requerido
def ia_importancia(request):
    if request.method == "POST":
        a = request.POST.get("accion")
        sector = request.POST.get("sector") or None
        tamano = request.POST.get("tamano") or None
        if a == "generar_historial":
            creadas = ia.generar_propuestas_historial(sector, tamano)
            messages.success(request, f"Se generaron {len(creadas)} propuestas." if creadas else
                             "No hay propuestas nuevas: faltan evaluaciones finalizadas o la IS actual ya coincide con los datos.")
        elif a == "generar_llm":
            try:
                creadas = ia.generar_propuestas_llm(sector, tamano)
                messages.success(request, f"El modelo de lenguaje propuso {len(creadas)} cambios.")
            except ia.ErrorIA as e:
                messages.error(request, str(e))
        elif a in ("aprobar", "rechazar"):
            p = get_object_or_404(PropuestaIS, pk=request.POST["id"], estado="PEND")
            (ia.aprobar if a == "aprobar" else ia.rechazar)(p, request.user)
            messages.success(request, "Propuesta " + ("aprobada: la IS del catálogo fue actualizada." if a == "aprobar" else "rechazada."))
        elif a == "restaurar":
            ia.restaurar_base(get_object_or_404(Factor, pk=request.POST["id"]), request.user)
            messages.success(request, "Se restauró la IS original de la tesis.")
        return redirect("ia_importancia")
    pendientes = PropuestaIS.objects.filter(estado="PEND").select_related("factor", "factor__dimension")
    factores = []
    lista_f = list(Factor.objects.filter(activo=True).select_related("dimension"))
    ests = ia.estimar_todos(factores=lista_f)
    for f in lista_f:
        est = ests.get(f.id)
        factores.append({"f": f, "est": est, "cambio": f.importancia_sugerida != f.importancia_base,
                         "pct": int(100 * (est["valor"] if est else f.importancia_sugerida) / 3)})
    ctx = {"pendientes": pendientes, "factores": factores, "niveles": NIVELES,
           "historial": HistorialIS.objects.select_related("factor", "usuario")[:12],
           "sectores": SECTORES, "tamanos": TAMANOS,
           "n_obs": ValoracionFactor.objects.filter(evaluacion__estado="FINAL").count(),
           "n_eval": Evaluacion.objects.filter(estado="FINAL").count()}
    return render(request, "guios/ia_importancia.html", ctx)
