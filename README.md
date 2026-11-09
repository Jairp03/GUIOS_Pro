# GUIOS PRO (Django + Supabase)

Sistema web para evaluar si una organización adopta un software libre, con los seis pasos de GUIOS (Rea Sánchez, 2022),
evaluación en equipo, historial, catálogo administrable y **propuesta de importancia sugerida (IS) con IA**.

## 1. Requisitos
- Python 3.10 o superior.
- Una cuenta de Supabase (opcional al inicio: sin base de datos remota el sistema usa SQLite local).

## 2. Instalación (paso a paso)
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (en Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Windows (en Linux/Mac: cp .env.example .env)
python manage.py migrate
python manage.py cargar_catalogo  # 3 dimensiones, 18 factores, 61 subfactores
python manage.py runserver
```

| Rol | Correo | Contraseña |
|---|---|---|
| Decisor | karen@guios.decisor  | Guios2026! |
| Decisor | john@guios.decisor   | Guios2026! |
| Decisor | javier@guios.decisor | Guios2026! |
| Decisor | erick@guios.decisor  | Guios2026! |
| Decisor | angel@guios.decisor  | Guios2026! |

Para un usuario administrador propio: `python manage.py createsuperuser`.

## 3. Conectar Supabase (PostgreSQL)
1. En Supabase crea un proyecto y guarda la contraseña de la base de datos.
2. Entra a **Connect** > **Connection string** y copia la cadena URI (modo *Session pooler*, puerto 5432).
3. Pégala en `.env`: `DATABASE_URL=postgresql://postgres.xxxx:TU_CLAVE@aws-0-REGION.pooler.supabase.com:5432/postgres`
4. Ejecuta `python manage.py migrate` y `python manage.py cargar_catalogo` otra vez, ahora sobre Supabase.
5. Ejecuta `python manage.py activar_rls`. Supabase publica por API las tablas del esquema `public`; con RLS activado
   (y sin políticas) esa API no puede leer nada. Django sigue funcionando porque se conecta con el rol `postgres`.

La autenticación la maneja Django (tabla `auth_user`); no se usa Supabase Auth.

### Si las páginas cargan lento con Supabase
- Con la base de datos remota, cada consulta es un viaje de red. El sistema ya usa un **pool de conexiones**, sesiones en cookie y
  pocas consultas por página (de 2 a 8). Con `DEBUG=True`, la terminal muestra `[rendimiento] ... N consultas · X ms` por página.
- Si la latencia sigue alta, revisa la **región** de tu proyecto de Supabase: la más cercana a Ecuador suele ser São Paulo (`sa-east-1`).
  La región no se puede cambiar en un proyecto ya creado; habría que crear uno nuevo.
- Usa la cadena de *Session pooler* (puerto 5432). Con el *Transaction pooler* (6543) el sistema ajusta lo necesario, pero no es necesario.

## 4. Propuesta de mejora: importancia sugerida con IA (menú «IS con IA», solo Administrador)
La IS de GUIOS era fija (literatura y encuesta a expertos) e igual para todas las organizaciones. Ahora:
- **Aprender del historial** (sin servicios externos): para cada factor combina la IS de la tesis con las valoraciones reales de
  los decisores en evaluaciones finalizadas: `IS = (5·IS_tesis + Σ w·x) / (5 + Σ w)`. El peso `w` baja con la antigüedad
  (vida media de 180 días) y con la diferencia de sector y de tamaño. Con pocos datos casi no cambia; se muestra la confianza.
- **Modelo de lenguaje** (opcional): si defines `ANTHROPIC_API_KEY` en `.env`, propone una IS según el perfil de la organización.
- Toda propuesta queda **pendiente** hasta que el Administrador la aprueba o rechaza. Se guarda el historial de cambios y se
  puede restaurar la IS de la tesis.
- Al crear una evaluación se puede marcar «Usar importancia sugerida ajustada por IA». Se usa la estimación para el sector y el
  tamaño de esa organización, y el valor usado queda guardado para que el resultado sea reproducible.

## 5. Reglas implementadas (tomadas del programa original)
- Importancia relativa = promedio entero (hacia abajo) de la IS y la importancia del decisor. Es relevante si no es Irrelevante.
- Ponderación media (PM) = promedio de los subfactores (1 a 4). PM ≥ 3 es positivo. Con alcance Interno es
  Fortaleza o Debilidad, y con alcance Externo, Oportunidad o Amenaza. Para Soporte (alcance «Ambos») lo define el decisor.
- Decisión por conteo y Recomendación A, B o C según la importancia de las debilidades y amenazas.
- Evaluación en equipo: cada decisor envía sus valoraciones y el creador cierra la etapa. **El criterio de consolidación
  (promedio o mediana) está por validar con el docente.**

## 6. Cambios respecto al prototipo de Figma Make
El prototipo era solo interfaz: no guardaba datos (sin base de datos ni sesión real), y el historial, los resultados y las
acciones sugeridas eran textos fijos. Tampoco había gestión de usuarios (RF-02). Ahora todo se calcula y se guarda en la base de datos.

## 6b. Diseño
Estilo «liquid glass»: superficies de vidrio esmerilado, reflejos que siguen al cursor, fondo animado en azul y naranja, control
segmentado con píldora que se desliza, barras y anillos animados, barra de carga entre páginas y transiciones entre páginas
(en navegadores que las soportan). Respeta «reducir movimiento» del sistema operativo.

## 7. Pruebas
`python manage.py test guios` (reglas de GUIOS, módulo de IA, flujo completo y permisos).

## 8. Despliegue
Con `DEBUG=False`, define `SECRET_KEY`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`, ejecuta `python manage.py collectstatic`
y sirve con `gunicorn config.wsgi`. Los archivos estáticos los sirve WhiteNoise.
