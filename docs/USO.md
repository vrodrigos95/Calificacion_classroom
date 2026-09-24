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

## 4. Revisar una tarea

### 4.1 Elegir la tarea
1. En **Mis cursos**, clic en el grupo.
2. Clic en la tarea. Verás la tabla de alumnos: quién entregó, quién no, si fue tarde y qué
   archivos subió. Arriba, el resumen: "44 entregadas · 0 sin archivos · 5 sin entrega".

### 4.2 Descargar las entregas
1. Clic en **Descargar entregas**.
2. Espera a que termine (con ~45 entregas, menos de un minuto). Verás "X de Y procesadas".
3. En la columna **Imágenes** aparece "1 página ▼", "2 páginas ▼", etc. Clic ahí para ver las
   miniaturas; clic en una miniatura para verla completa.

### 4.3 Revisar tu marca
1. Revisa que esté marcada la casilla **Buscar mi marca en esta tarea**. Si en una tarea no
   firmaste en clase, desmárcala.
2. Clic en **Revisar marcas**.
3. Junto al nombre de cada alumno con marca aparece el **recorte** de la firma encontrada.
4. En la columna **Marca**:

| Dice | Qué significa | Qué haces |
|---|---|---|
| **Con marca · 100** | Tu firma se reconoció con claridad. | Revisa el recorte de un vistazo. Si no es tu firma, clic en "No es mi marca". |
| **¿Es tu marca?** | Se encontró algo parecido, pero hay que confirmar. | Mira el recorte y da clic en **✓ Sí, es mi marca** o **✗ No**. |
| **Revisar a mano** | No se pudo verificar (p. ej. falló la conexión con Claude). | Mira el recorte y decide igual que arriba. |
| **Sin marca** | No se encontró tu firma. | Esa tarea se revisa normal. |
| **Módulo desactivado** | Desmarcaste "Buscar mi marca" en esta tarea. | — |
| **Configura tu marca** | No tienes ninguna marca activa. | Ve a **Mi marca**. |

- **Confirmar varias a la vez:** después de ver los recortes, **Confirmar las N por
  confirmar** las marca todas como tuyas.
- **Deshacer:** si te equivocas, clic en **deshacer** junto a tu decisión.
- Tus decisiones **no se pierden** aunque vuelvas a dar "Revisar marcas".

### 4.4 Capturar en Classroom
1. Clic en **Ver entrega** en la fila del alumno: se abre su entrega en Classroom.
2. Captura la calificación (por ejemplo 100 si dice "Con marca · 100").

> En la etapa 5 la tabla tendrá un botón para **copiar calificación y comentario** y una
> casilla **Capturado** para llevar el control.

### 4.5 Si un alumno entrega después o vuelve a entregar
Clic en **Actualizar y reintentar errores**. La app descarga solo lo nuevo, lo que cambió y lo
que había fallado. Después, **Revisar marcas** otra vez: tus decisiones anteriores se respetan,
salvo en los alumnos que volvieron a entregar, que se revisan desde cero.

---

## 5. Qué significa cada estado de la columna "Imágenes"

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
| 4 | Calificar los ejercicios de las tareas **sin** tu firma, con comentario sugerido. |
| 5 | Procesar toda la tarea de un solo clic, botón de copiar calificación y comentario, casilla "Capturado". |
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
