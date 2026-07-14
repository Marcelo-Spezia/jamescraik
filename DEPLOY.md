# Desplegar la app (para que la use el equipo sin instalar nada)

Objetivo: que tu compañero abra un **link** en el navegador. Usamos **Streamlit
Community Cloud** (gratis, se despliega desde GitHub, los secretos van en su panel).

> ⚠️ **Seguridad — la app gasta plata.** Cada calificación/enrichment dispara llamadas
> reales (tokens de Claude + créditos de Apollo). **No la dejes pública.** Doble candado:
> **contraseña** en la app (paso 3) + app **privada por email** (paso 4). Las API keys
> nunca van al repo: se cargan como *Secrets* en el panel de Streamlit (paso 3).

## 1. Subir el código a GitHub
El `.env` (con las keys) está en `.gitignore`, así que **no se sube**.
- Creá un repo **privado** en GitHub (ej. `icp-engine`).
- Desde la carpeta del proyecto, primer push:
  ```bash
  git add -A
  git commit -m "ICP Engine — calificador de leads (POC)"
  git branch -M main
  git remote add origin https://github.com/<tu-usuario>/icp-engine.git
  git push -u origin main
  ```
  (Si preferís, te dejo esto listo yo y solo pegás el `remote add` + `push`.)

## 2. Crear la app en Streamlit Community Cloud
1. Entrá a https://share.streamlit.io e iniciá sesión con tu cuenta de GitHub.
2. **New app** → elegí el repo, branch `main`, *Main file path*: `ui/app.py`.
3. Deploy. La primera vez tarda unos minutos (instala `requirements.txt`).

## 3. Cargar las credenciales y la contraseña (Secrets)
En la app → **⋮ → Settings → Secrets**, pegá (formato TOML):
```toml
ANTHROPIC_API_KEY = "tu-key-de-claude"
APOLLO_API_KEY = "tu-master-key-de-apollo"
APP_PASSWORD = "una-contraseña-que-elijas"
APP_DEFAULT_LANG = "en"   # abre en inglés para la demo (o "es"). Igual hay selector 🌐 en la app.
```
Guardá. La app las expone como variables de entorno automáticamente. Con `APP_PASSWORD`
seteada, la app **pide contraseña** al abrir (compartísela a tu compañero aparte del link).
La app es **bilingüe** (ES/EN): `APP_DEFAULT_LANG` define con qué idioma abre; el usuario
puede cambiarlo con el selector 🌐 en la barra lateral.

## 4. Restringir el acceso por email (NO saltear)
En **Settings → Sharing**: poné la app en **privada** y agregá los emails del equipo
(tu compañero y vos). Solo esos emails van a poder abrir el link.

## 5. Usar
Compartí el link `https://<algo>.streamlit.app` + la contraseña. Tu compañero:
1. **🧭 Definir campaña** — chatea con Claude para armar filtros de Sales Nav + rúbrica +
   propuesta de valor + señales de enrichment. La guarda.
2. **🎯 Calificar** — sube el CSV (cualquier formato), califica en tiers A/B/C/D con el
   por qué, enriquece los A/B con señales de negocio, filtra y descarga el CSV.
3. **🏢 Contexto** — mantiene el contexto de Making Sense que groundea todo.

## Notas
- **Persistencia:** en Streamlit Cloud el disco es **efímero**. Las campañas y el contexto
  que se guardan *desde la app* (`campaigns/`, `context/`) viven hasta el próximo redeploy.
  Lo que esté **commiteado en el repo** sí persiste. Para persistencia real (guardar desde
  la app y que quede), pasamos a un contenedor (Render/Railway con volumen) — avisá.
- **Costos:** monitoreá el gasto en los paneles de Anthropic y Apollo. La contraseña +
  allowlist evitan uso no autorizado, pero cualquiera con acceso puede gastar créditos.
- **Rotar la contraseña:** cambiá `APP_PASSWORD` en Secrets cuando quieras; efecto inmediato.
