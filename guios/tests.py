import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (Alternativa, Dimension, Evaluacion, Factor, HistorialIS, Participante, Perfil, PropuestaIS,
                     Subfactor, ValoracionFactor, ValoracionSubfactor)
from .services import guios_engine as eng
from .services import ia_importancia as ia

User = get_user_model()


def crear_usuario(correo, rol="DECISOR", clave="Clave12345!"):
    u = User.objects.create_user(username=correo, email=correo, password=clave, first_name=correo.split("@")[0].title())
    Perfil.objects.create(usuario=u, rol=rol)
    return u


class CatalogoYReglasTests(TestCase):
    def test_catalogo_inicial(self):
        call_command("cargar_catalogo", verbosity=0)
        self.assertEqual((Dimension.objects.count(), Factor.objects.count(), Subfactor.objects.count()), (3, 18, 61))
        self.assertEqual(Factor.objects.get(nombre="Compatibilidad").subfactores.count(), 8)
        self.assertEqual(Factor.objects.get(nombre="Soporte").alcance, "Ambos")

    def test_importancia_relativa_como_el_programa_original(self):
        self.assertEqual(eng.importancia_relativa(2, 0), 1)   # Importante + Irrelevante = Opcional
        self.assertEqual(eng.importancia_relativa(1, 0), 0)   # Opcional + Irrelevante = Irrelevante
        self.assertEqual(eng.importancia_relativa(2, 2), 2)
        self.assertEqual(eng.importancia_relativa(1, 3), 2)   # Opcional + Fundamental = Importante
        self.assertFalse(eng.es_relevante(0)); self.assertTrue(eng.es_relevante(1))

    def test_foda_y_recomendacion(self):
        self.assertEqual(eng.clasificar_foda("Interno", 3.0), "Fortaleza")
        self.assertEqual(eng.clasificar_foda("Interno", 2.9), "Debilidad")
        self.assertEqual(eng.clasificar_foda("Externo", 3.5), "Oportunidad")
        self.assertEqual(eng.clasificar_foda("Externo", 1.0), "Amenaza")
        self.assertTrue(eng.decision_por_conteo(10, 6).startswith("Adoptar"))
        self.assertTrue(eng.decision_por_conteo(3, 6).startswith("No adoptar"))
        self.assertTrue(eng.decision_por_conteo(4, 4).startswith("Se deben considerar"))
        self.assertEqual(eng.tipo_recomendacion([{"clasificacion": "Amenaza", "ir": 2}]), "C")
        self.assertEqual(eng.tipo_recomendacion([{"clasificacion": "Debilidad", "ir": 1}]), "B")
        self.assertEqual(eng.tipo_recomendacion([{"clasificacion": "Fortaleza", "ir": 3}]), "A")


class IATests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("cargar_catalogo", verbosity=0)
        self.admin = crear_usuario("admin@x.com", "ADMIN")
        self.f = Factor.objects.get(nombre="Soporte")  # base: Importante (2)
        self.alt = Alternativa.objects.create(nombre="X")

    def _evaluacion_final(self, dec, sector="SAL", tamano="M", dias=10):
        fecha = timezone.now() - timedelta(days=dias)
        ev = Evaluacion.objects.create(alternativa=self.alt, creador=self.admin, estado="FINAL", sector=sector, tamano=tamano,
                                       fecha_creacion=fecha, fecha_finalizacion=fecha)
        ValoracionFactor.objects.create(evaluacion=ev, factor=self.f, usuario=self.admin, importancia_decisor=dec,
                                        importancia_sugerida_usada=2, importancia_relativa=(2 + dec) // 2, relevante=True)
        return ev

    def test_sin_datos_no_propone(self):
        self.assertIsNone(ia.estimar_factor(self.f))
        self.assertEqual(ia.generar_propuestas_historial(), [])

    def test_una_sola_observacion_no_alcanza(self):
        self._evaluacion_final(3)
        self.assertIsNone(ia.estimar_factor(self.f))

    def test_pocas_observaciones_casi_no_cambian_la_is(self):
        self._evaluacion_final(3)
        self._evaluacion_final(3)
        est = ia.estimar_factor(self.f)
        self.assertEqual(est["nivel"], 2)          # sigue Importante
        self.assertLess(est["confianza"], 0.3)

    def test_muchas_observaciones_mueven_la_is_y_se_aprueba(self):
        for _ in range(25):
            self._evaluacion_final(3)
        est = ia.estimar_factor(self.f)
        self.assertEqual(est["nivel"], 3)
        self.assertGreater(est["confianza"], 0.7)
        creadas = ia.generar_propuestas_historial()
        self.assertEqual(len(creadas), 1)
        self.assertEqual(ia.generar_propuestas_historial(), [])  # no duplica
        ia.aprobar(creadas[0], self.admin)
        self.f.refresh_from_db()
        self.assertEqual((self.f.importancia_sugerida, self.f.importancia_base), (3, 2))
        self.assertEqual(HistorialIS.objects.filter(factor=self.f).count(), 1)
        ia.restaurar_base(self.f, self.admin); self.f.refresh_from_db()
        self.assertEqual(self.f.importancia_sugerida, 2)

    def test_similitud_de_perfil_pesa_mas(self):
        for _ in range(12):
            self._evaluacion_final(3, sector="SAL")
        for _ in range(12):
            self._evaluacion_final(0, sector="EDU")
        self.assertGreater(ia.estimar_factor(self.f, "SAL")["valor"], ia.estimar_factor(self.f, "EDU")["valor"])

    def test_las_evaluaciones_recientes_pesan_mas(self):
        for _ in range(10):
            self._evaluacion_final(3, dias=5)
        for _ in range(10):
            self._evaluacion_final(0, dias=700)
        self.assertGreater(ia.estimar_factor(self.f)["media"], 2.0)

    def test_llm_con_respuesta_simulada(self):
        resp = json.dumps({"factores": [{"factor": "Soporte", "nivel": 3, "confianza": 0.8, "justificacion": "Crítico en salud."},
                                        {"factor": "No existe", "nivel": 1}, {"factor": "Formación", "nivel": 9}]})
        creadas = ia.generar_propuestas_llm("SAL", "M", llamar=lambda p: "Aquí está:\n" + resp)
        self.assertEqual([c.factor.nombre for c in creadas], ["Soporte"])
        self.assertEqual(creadas[0].estado, "PEND")
        with self.assertRaises(ia.ErrorIA):
            ia.generar_propuestas_llm("SAL", "M", llamar=lambda p: "sin json")


class FlujoCompletoTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("cargar_catalogo", verbosity=0)
        self.admin = crear_usuario("admin@x.com", "ADMIN")
        self.maria = crear_usuario("maria@x.com")
        self.luis = crear_usuario("luis@x.com")
        self.alt = Alternativa.objects.create(nombre="LibreOffice")

    def test_login(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        r = self.client.post(reverse("login"), {"correo": "maria@x.com", "password": "mala"})
        self.assertContains(r, "Correo o contraseña incorrectos.")
        r = self.client.post(reverse("login"), {"correo": "MARIA@x.com", "password": "Clave12345!"})
        self.assertRedirects(r, reverse("dashboard"))
        self.assertContains(self.client.get(reverse("dashboard")), "Panel")

    def test_flujo_de_una_evaluacion_en_equipo(self):
        self.client.login(username="maria@x.com", password="Clave12345!")
        r = self.client.post(reverse("evaluacion_nueva"), {"alternativa": self.alt.id, "sector": "EDU", "tamano": "M",
                             "criterio": "PROMEDIO", "invitados": "luis@x.com, nadie@x.com"})
        ev = Evaluacion.objects.get()
        self.assertRedirects(r, reverse("importancia", args=[ev.pk]))
        self.assertEqual(ev.participantes.count(), 2)
        self.assertContains(self.client.get(reverse("importancia", args=[ev.pk])), "Importancia de los factores")
        # Paso 1 y 2: todo Importante salvo dos factores irrelevantes
        datos = {f"f_{f.id}": 2 for f in Factor.objects.all()}
        irrelevantes = Factor.objects.filter(nombre__in=["Reusabilidad", "Portabilidad"])
        for f in irrelevantes:
            datos[f"f_{f.id}"] = 0
        datos[f"a_{Factor.objects.get(nombre='Soporte').id}"] = "Interno"
        self.client.post(reverse("importancia", args=[ev.pk]), datos)
        self.assertEqual(ValoracionFactor.objects.filter(usuario=self.maria, relevante=True).count(), 16)
        # Paso 3 y 4: responde todos los subfactores de los factores relevantes
        for _ in range(20):
            r = self.client.get(reverse("subfactores", args=[ev.pk]))
            if r.status_code != 200:
                break
            fid = r.context["factor"].id
            datos = {f"s_{x['s'].id}": 4 for x in r.context["filas"]}
            if fid == Factor.objects.get(nombre="Formación").id:
                datos = {k: 1 for k in datos}
            resp = self.client.post(f"{reverse('subfactores', args=[ev.pk])}?f={fid}", datos)
            if resp.url == reverse("evaluacion", args=[ev.pk]):
                break
        self.client.post(reverse("enviar", args=[ev.pk]))
        self.assertTrue(Participante.objects.get(usuario=self.maria).enviado)
        # El segundo decisor aún no envía: el creador cierra la etapa con lo enviado
        self.client.post(reverse("consolidar", args=[ev.pk]))
        ev.refresh_from_db(); self.assertTrue(ev.finalizada)
        res = ev.resultado
        self.assertEqual(res.fortalezas + res.oportunidades + res.debilidades + res.amenazas, 16)
        self.assertEqual(res.debilidades, 1)  # Formación (interna) con PM 1
        self.assertTrue(res.adoptable)
        self.assertEqual(res.tipo_recomendacion, "C")  # debilidad en un factor Importante
        page = self.client.get(reverse("resultados", args=[ev.pk]))
        self.assertContains(page, "Adoptar, pues la cantidad"); self.assertContains(page, "Recomendación C")
        self.assertContains(page, "Subfactores no evaluados.")
        self.assertContains(self.client.get(reverse("historial") + "?q=Libre"), "LibreOffice")

    def test_no_se_puede_consolidar_sin_envios_ni_ver_ajenas(self):
        ev = Evaluacion.objects.create(alternativa=self.alt, creador=self.maria)
        Participante.objects.create(evaluacion=ev, usuario=self.maria)
        self.client.login(username="maria@x.com", password="Clave12345!")
        self.client.post(reverse("consolidar", args=[ev.pk]))
        ev.refresh_from_db(); self.assertFalse(ev.finalizada)
        self.client.logout(); self.client.login(username="luis@x.com", password="Clave12345!")
        self.assertEqual(self.client.get(reverse("evaluacion", args=[ev.pk])).status_code, 404)

    def test_is_con_ia_se_congela_en_la_valoracion(self):
        self.client.login(username="maria@x.com", password="Clave12345!")
        ev = Evaluacion.objects.create(alternativa=self.alt, creador=self.maria, usar_is_ia=True, sector="EDU")
        Participante.objects.create(evaluacion=ev, usuario=self.maria)
        self.client.post(reverse("importancia", args=[ev.pk]), {f"f_{f.id}": 2 for f in Factor.objects.all()})
        v = ValoracionFactor.objects.get(usuario=self.maria, factor__nombre="Soporte")
        self.assertEqual(v.importancia_sugerida_usada, Factor.objects.get(nombre="Soporte").importancia_sugerida)

    def test_permisos_y_administracion(self):
        self.client.login(username="maria@x.com", password="Clave12345!")
        for nombre in ("catalogo", "usuarios", "ia_importancia"):
            self.assertRedirects(self.client.get(reverse(nombre)), reverse("dashboard"))
        self.client.logout(); self.client.login(username="admin@x.com", password="Clave12345!")
        dim = Dimension.objects.get(nombre="Económica")
        self.assertContains(self.client.get(reverse("catalogo") + f"?dim={dim.id}"), "Coste total de propiedad")
        self.client.post(reverse("catalogo"), {"accion": "crear_factor", "dimension": dim.id, "nombre": "Licencias", "alcance": "Interno", "importancia_sugerida": 2})
        f = Factor.objects.get(nombre="Licencias"); self.assertEqual(f.importancia_base, 2)
        self.client.post(reverse("catalogo"), {"accion": "baja_factor", "id": f.id}); f.refresh_from_db(); self.assertFalse(f.activo)
        self.client.post(reverse("usuarios"), {"correo": "nuevo@x.com", "nombre": "Nuevo", "rol": "DECISOR", "password": "Temporal123!"})
        self.assertEqual(Perfil.objects.get(usuario__username="nuevo@x.com").rol, "DECISOR")
        self.assertEqual(self.client.get(reverse("ia_importancia")).status_code, 200)
        r = self.client.post(reverse("ia_importancia"), {"accion": "generar_llm", "sector": "EDU"}, follow=True)
        self.assertContains(r, "ANTHROPIC_API_KEY")
