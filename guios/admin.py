from django.contrib import admin

from . import models

for m in (models.Perfil, models.Dimension, models.Factor, models.Subfactor, models.AccionSugerida,
          models.Alternativa, models.Evaluacion, models.Participante, models.ResultadoEvaluacion,
          models.PropuestaIS, models.HistorialIS):
    admin.site.register(m)
