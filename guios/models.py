from django.conf import settings
from django.db import models
from django.utils import timezone

NIVELES = ["Irrelevante", "Opcional", "Importante", "Fundamental"]
NIVELES_SUB = ["No cumple el requisito", "Desconozco si cumple requisito",
               "Cumple parcialmente el requisito", "Cumple el requisito"]
NIVELES_SUB_CORTOS = ["No cumple", "Desconozco", "Parcial", "Cumple"]
NIVEL_CHOICES = [(i, n) for i, n in enumerate(NIVELES)]

SECTORES = [("EDU", "Educación"), ("SAL", "Salud"), ("GOB", "Gobierno"), ("IND", "Industria"),
            ("COM", "Comercio y servicios"), ("TEC", "Tecnología"), ("OTR", "Otro")]
TAMANOS = [("P", "Pequeña (menos de 50 personas)"), ("M", "Mediana (50 a 250)"), ("G", "Grande (más de 250)")]


class Perfil(models.Model):
    ROLES = [("ADMIN", "Administrador"), ("DECISOR", "Decisor")]
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(max_length=10, choices=ROLES, default="DECISOR")
    organizacion = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"{self.usuario.get_username()} ({self.get_rol_display()})"


class Dimension(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "dimensión"
        verbose_name_plural = "dimensiones"

    def __str__(self):
        return self.nombre


class Factor(models.Model):
    ALCANCES = [("Interno", "Interno"), ("Externo", "Externo"), ("Ambos", "Ambos (lo define el decisor)")]
    dimension = models.ForeignKey(Dimension, on_delete=models.PROTECT, related_name="factores")
    nombre = models.CharField(max_length=150)
    alcance = models.CharField(max_length=10, choices=ALCANCES)
    importancia_sugerida = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES, default=1,
        help_text="Importancia sugerida (IS) vigente, de 0 (Irrelevante) a 3 (Fundamental).")
    importancia_base = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES, default=1,
        help_text="IS original de la tesis, para poder restaurarla.")
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["dimension__orden", "orden", "nombre"]
        constraints = [models.UniqueConstraint(fields=["dimension", "nombre"], name="factor_unico_por_dimension")]

    def __str__(self):
        return self.nombre

    @property
    def nivel_sugerido(self):
        return NIVELES[self.importancia_sugerida]


class Subfactor(models.Model):
    factor = models.ForeignKey(Factor, on_delete=models.CASCADE, related_name="subfactores")
    texto = models.TextField()
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["factor", "orden", "id"]

    def __str__(self):
        return self.texto[:80]


class AccionSugerida(models.Model):
    APLICA = [("DEB", "Debilidad"), ("AME", "Amenaza"), ("AMB", "Debilidad o amenaza")]
    factor = models.ForeignKey(Factor, on_delete=models.CASCADE, related_name="acciones")
    descripcion = models.TextField()
    aplica_a = models.CharField(max_length=3, choices=APLICA, default="AMB")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "acción sugerida"
        verbose_name_plural = "acciones sugeridas"

    def __str__(self):
        return f"{self.factor}: {self.descripcion[:60]}"


class Alternativa(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.TextField(blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    creada = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Evaluacion(models.Model):
    ESTADOS = [("PROCESO", "En proceso"), ("FINAL", "Finalizada")]
    CRITERIOS = [("PROMEDIO", "Promedio de los decisores"), ("MEDIANA", "Mediana de los decisores")]
    alternativa = models.ForeignKey(Alternativa, on_delete=models.PROTECT, related_name="evaluaciones")
    creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evaluaciones_creadas")
    estado = models.CharField(max_length=8, choices=ESTADOS, default="PROCESO")
    sector = models.CharField(max_length=3, choices=SECTORES, default="OTR")
    tamano = models.CharField(max_length=1, choices=TAMANOS, default="M")
    usar_is_ia = models.BooleanField("usar IS ajustada por IA", default=False)
    criterio = models.CharField(max_length=8, choices=CRITERIOS, default="PROMEDIO")
    fecha_creacion = models.DateTimeField(default=timezone.now)
    fecha_finalizacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "evaluación"
        verbose_name_plural = "evaluaciones"

    def __str__(self):
        return f"Evaluación #{self.pk} · {self.alternativa}"

    @property
    def finalizada(self):
        return self.estado == "FINAL"


class Participante(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="participantes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="participaciones")
    enviado = models.BooleanField(default=False)
    enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["evaluacion", "usuario"], name="participante_unico")]


class ValoracionFactor(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="valoraciones_factor")
    factor = models.ForeignKey(Factor, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    importancia_decisor = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    importancia_sugerida_usada = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    importancia_relativa = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    relevante = models.BooleanField(default=False)
    alcance_definido = models.CharField(max_length=10, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["evaluacion", "factor", "usuario"], name="valoracion_factor_unica")]


class ValoracionSubfactor(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="valoraciones_subfactor")
    subfactor = models.ForeignKey(Subfactor, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    puntaje = models.PositiveSmallIntegerField(choices=[(i, n) for i, n in enumerate(NIVELES_SUB, 1)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["evaluacion", "subfactor", "usuario"], name="valoracion_subfactor_unica")]


class ResultadoFactor(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="resultados_factor")
    factor = models.ForeignKey(Factor, on_delete=models.PROTECT)
    alcance_aplicado = models.CharField(max_length=10)
    importancia_relativa = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    pm = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    clasificacion = models.CharField(max_length=12, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["evaluacion", "factor"], name="resultado_factor_unico")]


class ResultadoEvaluacion(models.Model):
    evaluacion = models.OneToOneField(Evaluacion, on_delete=models.CASCADE, related_name="resultado")
    decision = models.TextField()
    tipo_recomendacion = models.CharField(max_length=1)
    recomendacion = models.TextField()
    fortalezas = models.PositiveSmallIntegerField(default=0)
    oportunidades = models.PositiveSmallIntegerField(default=0)
    debilidades = models.PositiveSmallIntegerField(default=0)
    amenazas = models.PositiveSmallIntegerField(default=0)
    adoptable = models.BooleanField(default=False)


class PropuestaIS(models.Model):
    """Propuesta de importancia sugerida (IS) generada por IA para un factor."""
    METODOS = [("HISTORIAL", "Aprendizaje del historial"), ("LLM", "Modelo de lenguaje (contextual)")]
    ESTADOS = [("PEND", "Pendiente"), ("APRO", "Aprobada"), ("RECH", "Rechazada")]
    factor = models.ForeignKey(Factor, on_delete=models.CASCADE, related_name="propuestas")
    metodo = models.CharField(max_length=10, choices=METODOS)
    nivel_actual = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    valor_propuesto = models.DecimalField(max_digits=4, decimal_places=2)
    nivel_propuesto = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    confianza = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    n_observaciones = models.PositiveIntegerField(default=0)
    media_historial = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    justificacion = models.TextField()
    sector = models.CharField(max_length=3, blank=True)
    tamano = models.CharField(max_length=1, blank=True)
    estado = models.CharField(max_length=4, choices=ESTADOS, default="PEND")
    creada = models.DateTimeField(default=timezone.now)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada"]
        verbose_name = "propuesta de IS"
        verbose_name_plural = "propuestas de IS"

    @property
    def cambia(self):
        return self.nivel_propuesto != self.nivel_actual


class HistorialIS(models.Model):
    factor = models.ForeignKey(Factor, on_delete=models.CASCADE, related_name="historial_is")
    nivel_anterior = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    nivel_nuevo = models.PositiveSmallIntegerField(choices=NIVEL_CHOICES)
    origen = models.CharField(max_length=40)
    justificacion = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha"]
