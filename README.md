# AudioTab Pro 🎸 - Documentación Completa de Desarrollo

¡Bienvenido a **AudioTab Pro**! Este es un sistema de transcripción inteligente y visualización en tiempo real que convierte archivos de audio y videos de YouTube en partituras y tablaturas de guitarra completas y altamente jugables.

Este documento ofrece una guía técnica detallada de la arquitectura, comportamiento y flujos de datos tanto de la interfaz de usuario (Frontend) como de la API de análisis y procesamiento (Backend).

---

## 🚀 Arquitectura General del Sistema

El proyecto está diseñado bajo una arquitectura de microservicios desacoplada y moderna:

```
[ FRONTEND ] (Vue 3 + Vite)
     │
     ├── (Peticiones HTTP / Form-Data) ──► [ BACKEND API ] (FastAPI + Uvicorn)
     │                                           │
     │                                           ├──► [ PIPELINE DE AUDIO ]
     │                                           │      ├── Librosa (Espectro & pYIN)
     │                                           │      ├── Basic Pitch (CNN Polifónico)
     │                                           │      └── Biomechanics (Heurística de mástil)
     │                                           │
     │                                           ├──► [ GENERACIÓN MUSICAL ]
     │                                           │      ├── Music21 (Estructuras y compases)
     │                                           │      └── Fractions (Tresillos perfectos)
     │                                           │
     │                                           └──► [ CACHE & COLA ] (PostgreSQL / Redis)
```

---

## 🎨 1. Frontend (Vue 3 / Vite)

El frontend está desarrollado sobre **Vue 3 (Composition API)** y servido por **Vite**. Es una Single Page Application (SPA) reactiva enfocada en el alto rendimiento visual y el diagnóstico detallado.

### Componentes Clave en el Frontend

1. **Gestor de Orígenes de Entrada (`inputSource`)**:
   - **📁 Subir Archivo**: Soporta carga de archivos locales mediante arrastrar y soltar (Drag and Drop) o selector de archivos.
   - **🎬 Video de YouTube**: Permite ingresar un link de YouTube. Embebe dinámicamente un reproductor oficial `<iframe>` interactivo con controles de API de YouTube, permitiendo reproducir el video original mientras se estudia la tablatura.

2. **Visualizador de Mástil en Tiempo Real (Fretboard Visualizer)**:
   - Renderiza un mástil físico de guitarra de 6 cuerdas y 15 trastes en SVG/CSS.
   - Durante la reproducción de la transcripción, anima y resalta de forma síncrona las posiciones exactas de traste y cuerda, mostrando los nombres científicos de las notas (ej. `E2`, `A#3`) con efectos de pulso visual.

3. **Renderizador de Partituras (OpenSheetMusicDisplay - OSMD)**:
   - Consume el MusicXML generado y lo renderiza de forma nativa en un lienzo SVG interactivo en el navegador.
   - Soporta controles de Zoom (`setZoom`) interactivos para alejar o acercar el papel musical.

4. **Consola de Diagnóstico en Tiempo Real**:
   - Recibe logs de procesamiento transmitidos desde el backend a través de peticiones HTTP POST y los acumula en un visor de consola estilo terminal Unix, diferenciando etapas por colores: `INFO`, `STATUS`, `SUCCESS` y `ERROR`.

5. **Panel de Parámetros de Transcripción**:
   - Configura el BPM sugerido (o auto-detectado).
   - Selecciona el Algoritmo de Pitch (Auto, pYIN Monofónico o Basic Pitch Polifónico).
   - **Modo Quintas (Power Chords)**: Casilla que activa la duplicación inteligente de notas graves.
   - **URL de Servidor API**: Permite alternar dinámicamente la dirección del backend, integrando un botón "Probar" (Pinger) que pings el servidor para comprobar conexión e inmunizar el frontend contra problemas de red local (`localhost` vs `127.0.0.1` vs IP de red para móviles).

---

## ⚙️ 2. Backend (FastAPI / Python)

El backend es un servicio de alto rendimiento construido sobre **FastAPI**. Se encarga de la descarga de flujos, el análisis digital de señales de audio (DSP), la asignación biomecánica y la generación de partituras estructuradas.

### Endpoints Principales (`back/app/main.py`)

* **`GET /`**:
  - Endpoint de comprobación de salud (*healthcheck*) y capacidades. Retorna el estado del backend y detalla si la detección polifónica de Spotify (`basic-pitch`) está activa o inactiva en el sistema anfitrión.

* **`POST /api/transcribe`**:
  - Recibe el archivo de audio físico del frontend en formato de formulario binario (`Multipart/Form-Data`).
  - Ejecuta el procesamiento de audio local y la optimización de digitación.

* **`POST /api/transcribe_youtube`**:
  - Diseñado específicamente para evitar la tasa de límite de YouTube y bloqueos de red local.
  - Utiliza `yt-dlp` para descargar la pista de audio del video de manera directa (`proxy: ''` para saltarse firewalls rotos como `172.16.0.1:8090`).
  - Envía cabeceras de navegador reales (`User-Agent`) para inmunizar las descargas de YouTube ante Connection Reset Errors (10054).
  - Extrae el título del video de forma dinámica y ejecuta el pipeline de transcripción sobre el audio descargado.

* **`POST /api/log`**:
  - Endpoint receptor para centralizar los logs del frontend y escribirlos de manera física y cronológica en el archivo de registro `back/transcription.log`.

---

## 🎸 3. El Pipeline de Transcripción (Análisis de Audio y Teoría de Guitarra)

El corazón matemático de AudioTab Pro reside en su pipeline de transcripción. Cada nota mostrada en la pantalla del usuario pasa por 5 etapas críticas:

### Etapa 1: Preprocesamiento de Audio (`preprocess_audio`)
El audio (archivo físico o descarga de YouTube) se remuestrea a **22050Hz (monofónico)** usando `librosa`. Se calcula el tempo (BPM) automáticamente en base al espectograma de Short-Time Fourier Transform (STFT) si el usuario especifica `0` BPM.

### Etapa 2: Detección de Pitch
1. **Monofónico (librosa pYIN)**: Utiliza la autocorrelación probabilística para determinar la frecuencia fundamental ($F_0$) en cada instante, filtrando armónicos irrelevantes y agrupando frames consecutivos con tolerancia de duración mínima de 0.05 segundos para estructurar notas musicales coherentes.
2. **Polifónico (Spotify Basic Pitch)**: Ejecuta una red neuronal convolucional para extraer de manera polifónica el inicio (*onsets*), el final (*offsets*) y la duración de múltiples notas superpuestas.

### Etapa 3: Optimización de Digitaciones de Guitarra (`optimize_fingering`)
Una vez obtenidas las notas musicales en formato de notas MIDI ($M$), un algoritmo heurístico biomecánico decide en qué cuerda y traste de guitarra debe tocarse la nota:
- Evalúa la comodidad de traste y cuerda actual en comparación con la nota anterior.
- Penaliza los saltos de traste extremos en el mástil y los saltos de cuerda incómodos.
- Prioriza de forma inteligente las cuerdas al aire (traste 0) e implementa preferencias por trastes ergonómicos (trastes del 0 al 12).

### Etapa 4: Reconstrucción en "Modo Quintas" (Power Chords)
Cuando se activa el **Modo Quintas**, el pipeline transforma las notas raíces monofónicas graves (en cuerdas 6, 5, 4 y 3) en power chords de guitarra reales:
- **La Quinta Justa**: Se agrega automáticamente la nota a una distancia de +7 semitonos MIDI en la cuerda superior ($S - 1$).
- **La Octava**: Se agrega la octava a una distancia de +12 semitonos MIDI en la cuerda superior ($S - 2$).
- **Compensación de Afinación**: El algoritmo compensa la afinación de la guitarra estándar, aplicando un desplazamiento de traste adicional de $+3$ en lugar de $+2$ cuando la digitación cruza de la cuerda 3 (G) a la cuerda 2 (B), garantizando tablaturas 100% realistas y cómodas de tocar en el mástil.

### Etapa 5: Estructuración Rítmica y Cuantización en Tresillos (`quantize_duration`)
Un problema clásico en la transcripción de audio es que los tiempos reales nunca encajan de forma perfecta en una cuadrícula de compás tradicional, especialmente ritmos rápidos en tresillos (*triplets*):
- Implementamos una cuantización de alta precisión en `back/app/transcription/musicxml_generator.py`.
- En lugar de usar valores de punto flotante flotantes que causan imprecisiones en el compás, utilizamos la clase **`Fraction`** de Python.
- Mapeamos las duraciones de las notas directamente a fracciones matemáticas exactas como `Fraction(1, 3)` para tresillos de corchea, `Fraction(2, 3)` para tresillos de negra y `Fraction(1, 6)` para tresillos de semicorchea.
- Al agrupar notas simultáneas e insertarlas en la estructura de **music21**, el motor detecta la secuencia de fracciones fraccionarias y escribe de forma perfecta las directrices rítmicas del tresillo en el documento final de MusicXML.

---

## 🛠️ Instalación y Configuración de Desarrollo

### Requisitos Previos
- Python 3.10 o superior instalado.
- Node.js (v18 o superior) e npm.
- FFmpeg instalado y agregado a las variables de entorno de tu sistema (requerido para conversiones complejas de audio comprimido a WAV).

### Configuración del Backend
1. Entra a la carpeta del backend:
   ```bash
   cd back
   ```
2. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecuta el servidor de desarrollo FastAPI usando Uvicorn:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Configuración del Frontend
1. Entra a la carpeta del frontend:
   ```bash
   cd front
   ```
2. Instala las dependencias de NPM:
   ```bash
   npm install
   ```
3. Inicia el servidor local de desarrollo de Vite:
   ```bash
   npm run dev
   ```
4. Abre en tu navegador la dirección indicada (usualmente `http://localhost:5173`).

---

## 🎹 Resumen del Flujo de Datos del Sistema

1. **Selección del Origen**: El usuario sube un archivo `.mp3` o ingresa un link de YouTube en el frontend.
2. **Conexión API**: Al hacer clic en "Transcribir", el frontend envía una petición POST multipart al backend a la dirección dinámica (`/api/transcribe` o `/api/transcribe_youtube`).
3. **Descarga de YouTube (Opcional)**: El backend utiliza `yt-dlp` omitiendo proxies del sistema para descargar el flujo de audio en segundos.
4. **DSP & Detección**: `librosa` limpia y procesa la señal; se detectan las notas raíz en tresillos.
5. **Heurística Biomecánica**: Se calculan las mejores digitaciones de guitarra y se añaden las notas del power chord si el "Modo Quintas" está activado.
6. **MusicXML & GP5**: Se genera la partitura estructurada con fracciones en `music21` y la tablatura nativa en binario `.gp5`.
7. **Pintado SVG**: El frontend recibe el payload, reproduce la animación en tiempo real en el mástil virtual, y pinta la partitura/tablatura dinámica con OSMD y AlphaTab.

¡Feliz desarrollo de AudioTab Pro! 🎸
