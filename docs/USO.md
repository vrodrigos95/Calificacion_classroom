# Guía de uso: Revisor de tareas

Esta guía explica cómo usar la app día a día. Si todavía no está instalada en tu
computadora, primero sigue [INSTALACION.md](INSTALACION.md).

> **Lo más importante:** la app **nunca escribe nada en Classroom**. Solo lee las entregas,
> te sugiere la calificación y tú la capturas en Classroom. Si la app se equivoca, en
> Classroom no pasa nada.

---

## 1. Abrir la app

1. En la carpeta del proyecto (por ejemplo `Documentos\Calificacion_classroom`), haz **doble
   clic en `iniciar.bat`**.
2. Se abren **dos ventanas negras**: "Revisor - servidor" y "Revisor - interfaz". **No las
   cierres** mientras uses la app; puedes minimizarlas.
3. A los pocos segundos se abre el navegador en **http://localhost:5173**. Si no se abre solo,
   escribe esa dirección.

**Para cerrar la app:** cierra las dos ventanas negras.

> Si el navegador dice "No se puede acceder a este sitio", espera 10 segundos y recarga: la
> interfaz tarda un poco en arrancar. Si sigue igual, revisa que las dos ventanas negras estén
> abiertas y sin texto rojo.

---

## 2. Iniciar sesión

1. Clic en **Iniciar sesión con Google** y elige tu cuenta **institucional** (la de Classroom).
2. Si aparece **"Google no verificó esta app"**, da clic en **Continuar**. Es normal: la app
   está en modo de prueba.
3. En la lista de permisos, **marca todas las casillas** y acepta. La app solo pide permisos de
   lectura.
4. Verás la lista de **Mis cursos**.

> **Cada ~7 días Google te pedirá iniciar sesión otra vez.** Es una regla de Google para apps
> en modo de prueba. No se pierde nada: vuelves a iniciar sesión y sigues.

---

## 3. Configurar tu marca (solo la primera vez)

Tu marca es tu firma o sello con el que validas en clase las tareas bien hechas.

1. Arriba a la derecha, clic en **Mi marca**.
2. En **Agregar una marca**:
   - **Nombre:** por ejemplo "Firma verde".
   - **Imágenes de referencia:** sube de 1 a 5 fotos o recortes de tu firma **tal como
     aparece en las hojas** (misma pluma, mismo color). Varias fotos distintas ayudan.
   - **Significado:**
     - *Tarea correcta:* la entrega vale 100 y no se revisa el contenido.
     - *Solo informativa:* se muestra, pero la tarea se revisa normal.
   - **Dónde buscarla:** *Solo en la primera página* (lo normal) o *En cualquier página*.
     Una marca de "tarea correcta" en la primera página cubre toda la tarea, aunque tenga
     varias hojas.
3. Clic en **Guardar marca**.

Puedes cambiar el significado, la zona o las fotos cuando quieras, o desactivar la marca con
la casilla **Activa**.

> **Modo local vs. Claude.** Arriba de la página verás cuál está activo:
> - **Modo local** (sin clave de la API de Claude): la app encuentra la tinta de tu marca y te
>   muestra el recorte, pero **tú confirmas cada una**. Nunca pone 100 sola.
> - **Verificación con Claude** (con clave en `backend\.env`): Claude compara cada recorte con
>   tus fotos. Las coincidencias claras valen 100 solas; las dudosas te las pregunta.

---

## 4. Revisar una tarea (el flujo normal)

### 4.0 Elegir cómo se califica la tarea
Arriba de cada tarea, en **¿Cómo se califica esta tarea?**:

- **Solo revisar mi firma** (no usa Claude ni clave de respuestas): con firma = **100** sin
  comentario; sin firma = **90** con el comentario **"La actividad tiene que estar firmada"**.
  Puedes cambiar el 90 y el comentario ahí mismo; el cambio aplica de inmediato a toda la tarea.
  Sigue con **4.2** (no hace falta la clave de respuestas).
- **Revisar los ejercicios:** con firma = 100; las demás se califican con la clave de respuestas
  y Claude (secciones 4.1 y 4.2).

> En modo local (sin clave de Claude), las firmas encontradas aparecen como **Revisar a mano**
> y **no tienen calificación hasta que las confirmes** (nunca se pone 100 ni 90 sin tu
> decisión). Mira los recortes y usa **Confirmar las N por confirmar** o confírmalas una por una.
> Si rechazas una marca ("No"), esa entrega pasa a **Sin firma** (90).
>
> Revisa también el filtro **Sin firma**: si una firma era muy tenue o quedó cortada en la foto,
> puede no detectarse. Abre la hoja y, si sí está firmada, corrige la calificación a 100 y borra
> el comentario.

### 4.1 Una sola vez por tarea: la clave de respuestas
Solo hace falta para calificar las entregas **sin** tu firma (las firmadas valen 100 sin clave).

1. En **Mis cursos**, entra al grupo y a la tarea.
2. Clic en **Preparar la clave de respuestas →** y elige una forma:
   - **Capturarla tú** en la tabla (número, respuesta correcta y, si quieres, enunciado,
     procedimiento esperado y notación exigida, p. ej. "en porcentaje; usar ∪"). No usa Claude.
   - **A. Subir mi clave:** escríbela o sube una foto o PDF; Claude la acomoda en la tabla.
   - **B. Resolver con Claude:** busca el enunciado en la descripción y adjuntos de la tarea;
     si no está, en las hojas de los alumnos. Si distintos alumnos tienen enunciados
     diferentes, te avisa.
3. **Revisa y corrige** la tabla y da clic en **Validar clave**. La app **nunca** califica con una
   clave sin validar. Si luego la cambias, hay que validarla otra vez.
4. Abajo eliges cuánto vale un **error menor** en esta tarea (por defecto, la mitad).

### 4.2 Procesar la tarea (un clic)
Clic en **Procesar tarea**. La app, sin que hagas nada más:
1. Descarga las entregas.
2. Busca tu firma (si la casilla del módulo está activa; ver "Pasos por separado").
3. Pone 100 a las firmadas y califica las demás con la clave validada.

Lo que ya estaba listo no se repite. Si un alumno entrega después o vuelve a entregar, da clic
en **Procesar de nuevo**: solo se procesa lo nuevo.

### 4.3 El panel de revisión
Cada alumno aparece en una fila:

| Columna | Qué es |
|---|---|
| **Alumno** | Nombre y, si tiene marca, el **recorte** de tu firma para verificarla de un vistazo. Clic en el nombre para ver el detalle (páginas, ejercicio por ejercicio, decisiones sobre la marca). |
| **Estado** | *Con marca*, *Revisada*, *Revisar a mano*, *Error*, *Pendiente* o *Sin entrega* (ver tabla abajo). |
| **Calificación** | Sugerida sobre 100. Puedes cambiarla escribiendo otro número; "restaurar" regresa a la sugerida. 📋 la copia. |
| **Comentario privado** | Sugerido para el alumno, en español y de tú. Puedes editarlo; **Copiar comentario** lo copia. |
| **Classroom** | **Abrir entrega** te lleva directo a la entrega del alumno en Classroom. |
| **Capturado** | Márcala cuando ya pusiste calificación y comentario en Classroom. |

Arriba, los filtros (**Revisar a mano**, **Error**, **Con marca**…) y **Ocultar capturadas**
te ayudan a ir en orden. Tu trabajo en el panel es **revisar y copiar**:

1. Filtra **Revisar a mano** y resuelve cada una: confirma o rechaza la marca, o ajusta la
   calificación después de ver las páginas y el motivo.
2. Con **Todas**, ve alumno por alumno: **Abrir entrega** → pega la calificación (📋) y el
   comentario (**Copiar comentario**) en Classroom → marca **Capturado**.

| Estado | Qué significa | Qué haces |
|---|---|---|
| **Con marca** | Tu firma se reconoció (o la confirmaste). Vale 100. | Mira el recorte y captura. |
| **Sin firma** | (Modo «solo firma») No se encontró tu firma: 90 y el comentario configurado. | Revisa rápido la hoja por si la firma no se detectó, y captura. |
| **Revisada** | Claude leyó todo con claridad. | Revisa rápido y captura. |
| **Revisar a mano** | Algo es ilegible, ambiguo o dudoso, o hay una posible marca por confirmar. La calificación es solo sugerida. | Abre el detalle, decide y ajusta si hace falta. |
| **Error** | No se pudo descargar o calificar (el motivo aparece abajo). | Revísala en Classroom o vuelve a procesar. |
| **Pendiente** | Aún no se califica (p. ej. falta validar la clave). | Valida la clave y procesa de nuevo. |
| **Sin entrega** | El alumno no entregó. | — |

### 4.4 Pasos por separado (opcional)
Debajo de **Procesar tarea**, "Pasos por separado" permite solo descargar, solo revisar marcas,
desactivar la búsqueda de tu marca en esta tarea o **confirmar todas las marcas por confirmar**
después de ver los recortes. En el detalle de cada alumno puedes **Calificar** una sola entrega.

Reglas de la calificación: cada ejercicio vale 100 / número de ejercicios; error menor = la
mitad (o lo que configures). Un ejercicio que Claude no leyó con claridad **nunca** cuenta como
correcto. Una marca dudosa **nunca** da 100 sin tu confirmación.

## 5. Estados de las imágenes (en el detalle de cada alumno)

| Dice | Qué significa |
|---|---|
| **N páginas ▼** | Descargada y convertida. Clic para ver las páginas. |
| **En cola / Descargando…** | En proceso. |
| **Error** + motivo | No se pudo descargar esa entrega (p. ej. "PDF dañado o protegido", "El archivo ya no existe en Drive"). Las demás siguen normales. Revísala en Classroom con "Ver entrega". |
| **Borrada (retención)** | Las imágenes se borraron automáticamente por privacidad (ver abajo). Vuelve a descargar si las necesitas. |
| **—** | El alumno no entregó. |

---

## 6. Privacidad de tus alumnos

- Las imágenes descargadas y los recortes **se borran solos a los 14 días** (se cambia con
  `RETENTION_DAYS` en `backend\.env`).
- Si un alumno anula su entrega en Classroom, sus imágenes se borran al actualizar.
- La app no guarda correos de alumnos y no escribe sus nombres en los registros.
- Todo se guarda **solo en tu computadora** (carpeta `backend\data`).
- Si configuras la clave de Claude, las imágenes de las firmas encontradas se envían a la API
  de Anthropic para compararlas.

---

## 7. Lo que la app todavía no hace

| Etapa | Qué agrega |
|---|---|
| 6 | Señalar posibles copias entre alumnos. |

---

## 8. Problemas frecuentes

| Problema | Solución |
|---|---|
| "No se puede acceder a este sitio" | Espera unos segundos y recarga. Revisa que las dos ventanas negras estén abiertas. |
| Te regresa a la pantalla de inicio de sesión | La sesión con Google caducó (cada ~7 días). Inicia sesión otra vez. |
| "Faltan permisos" al iniciar sesión | En la pantalla de Google, marca **todas** las casillas. |
| "Google negó el acceso" | Revisa que seas docente de ese curso. |
| Una firma clara sale "Sin marca" | Agrega más fotos de referencia de tu firma en **Mi marca** (con la misma pluma) y vuelve a dar "Revisar marcas". |
| Una ventana negra muestra texto rojo | Toma una captura de esa ventana para revisarlo. |
