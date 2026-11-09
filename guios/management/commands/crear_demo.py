import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from guios.models import (AccionSugerida, Alternativa, Evaluacion, Factor, Participante, Perfil, Subfactor,
                          ValoracionFactor, ValoracionSubfactor, SECTORES)
from guios.services import guios_engine as engine

User = get_user_model()
# Patrones SINTÉTICOS (solo para la demostración): sector -> {factor: ajuste de importancia}
SESGO = {"EDU": {"Coste total de propiedad": 1, "Formación": 1}, "SAL": {"Fiabilidad": 1, "Soporte": 1, "Compatibilidad": 1},
         "GOB": {"Apoyo de la alta dirección": 1, "Bloqueo de proveedores": 1, "Documentación": 1},
         "IND": {"Fiabilidad": 1, "Soporte": 1}, "COM": {"Coste total de propiedad": 1, "Usabilidad": 1},
         "TEC": {"Personalización": 1, "Mantenibilidad": 1, "Reusabilidad": 1}, "OTR": {}}
# Desplazamiento SINTÉTICO general: simula que la IS de la tesis quedó desactualizada para estos factores.
DERIVA = {"Soporte": 1, "Fiabilidad": 1, "Reusabilidad": -1, "Portabilidad": -1}
ACCIONES = {"Soporte": "Ejemplo: contratar soporte comercial o acordar un canal de atención con la comunidad.",
            "Formación": "Ejemplo: planificar capacitación del personal antes de la migración.",
            "Coste total de propiedad": "Ejemplo: estimar costos de migración, soporte y capacitación a tres años."}


class Command(BaseCommand):
    help = "Crea usuarios, alternativas y un historial SINTÉTICO de evaluaciones para probar el sistema y la IA."

    def add_arguments(self, p):
        p.add_argument("--historial", type=int, default=40, help="Cantidad de evaluaciones sintéticas.")
        p.add_argument("--semilla", type=int, default=7)

    def handle(self, *a, **o):
        call_command("cargar_catalogo", verbosity=0)
        rnd = random.Random(o["semilla"])
        cuentas = [("admin@guios.local", "Administrador GUIOS", "ADMIN", "Admin2026!"), ("maria@unemi.edu.ec", "María Pérez", "DECISOR", "Guios2026!"),
                   ("luis@unemi.edu.ec", "Luis Andrade", "DECISOR", "Guios2026!"), ("ana@unemi.edu.ec", "Ana Torres", "DECISOR", "Guios2026!")]
        users = []
        for correo, nombre, rol, clave in cuentas:
            u, nuevo = User.objects.get_or_create(username=correo, defaults={"email": correo, "first_name": nombre})
            if nuevo:
                u.set_password(clave); u.save()
            Perfil.objects.update_or_create(usuario=u, defaults={"rol": rol})
            users.append(u)
        alts = [Alternativa.objects.get_or_create(nombre=n, defaults={"descripcion": d, "creada_por": users[1]})[0] for n, d in
                [("LibreOffice", "Suite ofimática"), ("Odoo Community", "ERP modular"), ("Moodle", "Plataforma educativa"), ("Nextcloud", "Almacenamiento y colaboración")]]
        for nombre, texto in ACCIONES.items():
            f = Factor.objects.get(nombre=nombre)
            AccionSugerida.objects.get_or_create(factor=f, descripcion=texto)
        factores = list(Factor.objects.filter(activo=True))
        calidad = {f.id: rnd.uniform(2.5, 3.9) for f in factores}
        ajuste_alt = {a.id: d for a, d in zip(alts, (0.3, 0.0, -0.3, 0.15))}
        ahora = timezone.now(); creadas = 0
        for _ in range(o["historial"]):
            sector = rnd.choice([s for s, _ in SECTORES]); tamano = rnd.choice("PMG")
            fecha = ahora - timedelta(days=rnd.randint(2, 300))
            participantes = rnd.sample(users[1:], rnd.randint(1, 3))
            ev = Evaluacion.objects.create(alternativa=rnd.choice(alts), creador=participantes[0], sector=sector, tamano=tamano, fecha_creacion=fecha)
            for u in participantes:
                Participante.objects.create(evaluacion=ev, usuario=u, enviado=True, enviado_en=fecha)
                for f in factores:
                    dec = max(0, min(3, round(f.importancia_base + DERIVA.get(f.nombre, 0) + SESGO[sector].get(f.nombre, 0) + rnd.gauss(0, 0.6))))
                    ir = engine.importancia_relativa(f.importancia_sugerida, dec)
                    ValoracionFactor.objects.create(evaluacion=ev, factor=f, usuario=u, importancia_decisor=dec,
                        importancia_sugerida_usada=f.importancia_sugerida, importancia_relativa=ir, relevante=engine.es_relevante(ir),
                        alcance_definido="Externo" if f.alcance == "Ambos" else "")
                    if engine.es_relevante(ir):
                        for s in Subfactor.objects.filter(factor=f, activo=True):
                            ValoracionSubfactor.objects.create(evaluacion=ev, subfactor=s, usuario=u, puntaje=max(1, min(4, round(calidad[f.id] + ajuste_alt[ev.alternativa_id] + rnd.gauss(0, 0.7)))))
            engine.finalizar(ev)
            Evaluacion.objects.filter(pk=ev.pk).update(fecha_finalizacion=fecha + timedelta(days=rnd.randint(1, 5)))
            creadas += 1
        self.stdout.write(self.style.SUCCESS(f"Demo lista: {len(users)} usuarios, {len(alts)} alternativas, {creadas} evaluaciones sintéticas."))
        self.stdout.write("Administrador: admin@guios.local / Admin2026!   ·   Decisores: maria@unemi.edu.ec / Guios2026!")
