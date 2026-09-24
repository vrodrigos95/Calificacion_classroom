# Instalar la app en otra computadora

Guía paso a paso para Windows 10/11. Tiempo aproximado: 30 minutos la primera vez.

Al terminar, para usarla sigue [USO.md](USO.md).

---

## 0. Antes de empezar: ¿quién la va a usar?

La app necesita un **proyecto de Google Cloud** con un "ID de cliente de OAuth". No hace falta
uno nuevo por computadora.

| Caso | Qué necesitas |
|---|---|
| **Tú mismo, en otra computadora** | Reutiliza el **mismo** ID de cliente y secreto que ya tienes. Pásalos de forma segura (USB, gestor de contraseñas). **Nunca por GitHub, correo o WhatsApp.** |
| **Otro docente, con tu proyecto** | En Google Cloud: **Google Auth Platform → Público → Usuarios de prueba → Add users** y agrega su correo (máximo 100 usuarios de prueba). Luego dale el ID y el secreto de forma segura. |
| **Otro docente, con su propio proyecto** | Que siga la sección "Configurar Google Cloud" del [README](../README.md). |

> Si el otro docente es de otra institución, su administrador de Google Workspace podría
> bloquear apps externas. Lo sabrán la primera vez que inicie sesión ("acceso bloqueado").

---

## 1. Instalar los programas necesarios (una sola vez)

Instala estos tres, con las opciones por defecto:

1. **Python 3.11 o más nuevo:** https://www.python.org/downloads/
   - ⚠️ En la primera pantalla del instalador marca **"Add python.exe to PATH"**.
2. **Node.js (versión LTS):** https://nodejs.org/
3. **Git:** https://git-scm.com/download/win

Comprueba que quedaron instalados. Abre **PowerShell** (menú Inicio → escribe "PowerShell") y
corre, uno por uno:

```powershell
python --version
node --version
git --version
```

Cada uno debe responder con un número de versión. Si alguno dice "no se reconoce", reinicia
la computadora y vuelve a probar; si sigue igual, reinstala ese programa.

---

## 2. Descargar el proyecto

En PowerShell:

```powershell
cd $HOME\Documents
git clone https://github.com/vrodrigos95/Calificacion_classroom.git
cd Calificacion_classroom
git checkout claude/nice-ritchie-epu2wf
```

Esto crea la carpeta `Documentos\Calificacion_classroom`.

> Mientras el proyecto está en desarrollo, la versión más nueva vive en la rama
> `claude/nice-ritchie-epu2wf`. Cuando se pase a la rama principal, el último comando ya no
> hará falta.

---

## 3. Instalar la app

1. Abre la carpeta `Documentos\Calificacion_classroom` en el Explorador de archivos.
2. Haz **doble clic en `instalar.bat`**.
   - Si Windows muestra "Windows protegió su PC", clic en **Más información → Ejecutar de
     todas formas**.
3. Espera a que termine (5 a 10 minutos). Instala todo, crea la base de datos y genera las
   claves de seguridad del archivo de configuración.
4. Al final dirá **"Instalación terminada"**. Si dice "Algo falló", toma una captura de la
   ventana.

<details>
<summary>Alternativa: instalar a mano con comandos (si instalar.bat falla)</summary>

En PowerShell, una línea a la vez:

```powershell
cd $HOME\Documents\Calificacion_classroom\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si falla con "la ejecución de scripts está deshabilitada", corre esto una vez y repite la
última línea:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

La línea debe empezar con `(.venv)`. Luego:

```powershell
pip install -e ".[dev]"
python scripts\crear_env.py
alembic upgrade head
cd ..\frontend
npm install
```
</details>

---

## 4. Poner tus datos de Google (y opcionalmente de Claude)

1. Abre `backend\.env` con el **Bloc de notas** (clic derecho → Abrir con → Bloc de notas).
2. Llena estas líneas (sin espacios alrededor del `=`):

   ```
   GOOGLE_CLIENT_ID=el-id-de-tu-cliente.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=el-secreto-de-tu-cliente
   ```

   Los encuentras en Google Cloud → **Google Auth Platform → Clientes**.
3. **Opcional, para la verificación con Claude:**

   ```
   ANTHROPIC_API_KEY=tu-clave-de-la-api
   ```

   Se crea en https://console.anthropic.com → API Keys (requiere saldo). Sin clave, la app
   funciona en modo local.
4. **No toques** `SESSION_SECRET` ni `TOKEN_ENCRYPTION_KEY`: ya se generaron solos.
5. Guarda (Ctrl+S) y cierra.

> 🔒 `backend\.env` contiene secretos. Nunca lo subas a GitHub ni lo mandes por correo. El
> proyecto ya está configurado para que git lo ignore.

---

## 5. Abrir la app por primera vez

1. Doble clic en **`iniciar.bat`**.
2. Se abren dos ventanas negras (no las cierres) y luego el navegador en
   http://localhost:5173.
3. Inicia sesión con Google (ver [USO.md](USO.md), sección 2).
4. En **Mi marca**, sube otra vez las fotos de tu firma: cada computadora tiene su propia base
   de datos.

**Listo.** A partir de aquí, para usar la app solo das doble clic en `iniciar.bat`.

---

## 6. Actualizar a una versión nueva

1. Cierra las dos ventanas negras si están abiertas.
2. Doble clic en **`actualizar.bat`**. Descarga la versión nueva, instala lo que haga falta y
   actualiza la base de datos sin borrar nada.
3. Abre la app con `iniciar.bat`.

---

## 7. ¿Paso mis datos de la computadora vieja?

**No hace falta.** Lo único que conviene conservar es tu marca, y es más simple volver a subir
las fotos en **Mi marca**.

La carpeta `backend\data` guarda hojas de alumnos, que son menores de edad; se borran solas a
los 14 días. Si aun así quieres moverla:
- Copia `backend\data` **y** `backend\.env` juntos (la base de datos depende de las claves de
  ese `.env`).
- Hazlo por USB, no por la nube, y borra la copia del USB después.

---

## 8. Problemas frecuentes al instalar

| Problema | Solución |
|---|---|
| `python` / `node` / `git` "no se reconoce" | No quedó en el PATH. Reinstala; en Python marca "Add python.exe to PATH". Reinicia la computadora. |
| "No se puede cargar el archivo …Activate.ps1" | Corre `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y responde `S`. (Con `instalar.bat` no pasa.) |
| `alembic` / `uvicorn` "no se reconoce" | El entorno no está activado: corre `.\.venv\Scripts\Activate.ps1` dentro de `backend` (la línea debe empezar con `(.venv)`). |
| Al iniciar sesión: `redirect_uri_mismatch` | En Google Cloud → Clientes, el URI de redirección debe ser exactamente `http://localhost:5173/api/auth/callback`. |
| Al iniciar sesión: "acceso bloqueado" o `access_denied` | Falta agregar esa cuenta como usuario de prueba, o la institución bloquea apps externas. |
| "Falta SESSION_SECRET en el entorno" | Corre `instalar.bat` otra vez, o `python scripts\crear_env.py` dentro de `backend` con el entorno activado. |
| "La clave de la API de Claude no es válida" / "no tiene crédito" | Revisa `ANTHROPIC_API_KEY` en `backend\.env` y el saldo en console.anthropic.com. |
| Puerto ocupado ("address already in use") | Ya hay otra copia de la app abierta. Cierra todas las ventanas negras y vuelve a abrir `iniciar.bat`. |
