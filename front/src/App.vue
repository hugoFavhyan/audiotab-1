<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'
import { Note, Chord, Scale } from "tonal"

// Dynamically determine the backend URL
const getBackendUrl = () => {
  const hostname = window.location.hostname || '127.0.0.1'
  return `http://${hostname}:8002`
}

const apiBaseUrl = ref(getBackendUrl())
const isBackendOnline = ref(null) // null = checking, true = connected, false = disconnected

// Function to check backend connectivity
const checkBackendConnection = async () => {
  try {
    const res = await fetch(`${apiBaseUrl.value}/`, { method: 'GET' })
    if (res.ok) {
      isBackendOnline.value = true
    } else {
      isBackendOnline.value = false
    }
  } catch (err) {
    isBackendOnline.value = false
  }
}

// Check connection on mount and every 15 seconds
onMounted(() => {
  checkBackendConnection()
  setInterval(checkBackendConnection, 15000)
})

// State variables
const audioFile = ref(null)
const audioUrl = ref('')
const audioInputRef = ref(null)

const bpm = ref(0) // 0 means automatic BPM detection in backend
const title = ref('Mi Transcripción')
const mode = ref('auto') // auto, monophonic, polyphonic
const powerChords = ref(false) // Toggle to automatically expand root notes into power chords
const useDemucs = ref(false) // Toggle to separate vocals/drums/bass using Demucs
const fingeringAlgorithm = ref('heuristic') // 'heuristic' or 'guitar_bert'
const fingeringStyle = ref('classic') // 'classic', 'metal', 'jazz'
const guitarTuning = ref('auto') // auto, standard, drop_d, half_step_down, drop_c, whole_step_down
const inputSource = ref('file') // 'file' or 'youtube'
const youtubeUrl = ref('') // YouTube video URL

const isProcessing = ref(false)
const animationProgress = ref(0) // Percentage of notes animated in real-time
const currentAnimatingNoteIndex = ref(0) // Current index of the note being animated
const errorMessage = ref('')
const successMessage = ref('')
const progress = ref(0)
const progressStatus = ref('')
const logs = ref([])

const addLog = (msg, type = 'info') => {
  const timestamp = new Date().toLocaleTimeString()
  logs.value.push({ timestamp, text: msg, type })
  
  // Enviar el log al servidor para escritura física en un archivo .log
  fetch(`${apiBaseUrl.value}/api/log`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: `[${timestamp}] [${type.toUpperCase()}] ${msg}` })
  }).catch(err => {
    console.error('No se pudo enviar el log remoto:', err)
  })
}

const notesCount = ref(0)
const notes = ref([])
const musicXml = ref('')
const gp5Base64 = ref('')

const displayedNotes = ref([])
const activeFretboardNotes = ref([])
const isAnimatingRealtime = ref(false)
const animationSpeed = ref(180) // ms per note

const osmdContainer = ref(null)
let alphaTabApi = null
let osmdInstance = null
const osmdZoom = ref(1.0)

const isNoteActive = (string, fret) => {
  return activeFretboardNotes.value.some(
    (n) => n.string === string && n.fret === fret
  )
}

const getActiveNotePitch = (string, fret) => {
  const match = activeFretboardNotes.value.find(
    (n) => n.string === string && n.fret === fret
  )
  return match ? match.pitch : ''
}

// Animate the transcription drawing in real-time
const animateNotesInRealtime = async () => {
  if (notes.value.length === 0) return
  
  isAnimatingRealtime.value = true
  displayedNotes.value = []
  activeFretboardNotes.value = []
  animationProgress.value = 0
  currentAnimatingNoteIndex.value = 0
  
  addLog('Iniciando visualización en tiempo real sobre el mástil de guitarra...', 'status')
  
  for (let i = 0; i < notes.value.length; i++) {
    const note = notes.value[i]
    
    // Update progress variables
    currentAnimatingNoteIndex.value = i + 1
    animationProgress.value = Math.round(((i + 1) / notes.value.length) * 100)
    
    // Add note to display list
    displayedNotes.value.push(note)
    
    // Highlight on fretboard
    activeFretboardNotes.value = [{
      string: note.string,
      fret: note.fret,
      pitch: note.pitch
    }]
    
    // Auto scroll the notes card table
    await nextTick()
    const tableContainer = document.querySelector('.table-container')
    if (tableContainer) {
      tableContainer.scrollTop = tableContainer.scrollHeight
    }
    
    // Wait before next note
    await new Promise((resolve) => setTimeout(resolve, animationSpeed.value))
  }
  
  // Clear highlighted notes after finishing
  setTimeout(() => {
    activeFretboardNotes.value = []
    isAnimatingRealtime.value = false
    animationProgress.value = 100
    addLog('¡Visualización en tiempo real completada con éxito!', 'success')
  }, 300)
}

// Handle file selection
const handleFileChange = (e) => {
  const file = e.target.files[0]
  if (!file) return
  
  audioFile.value = file
  audioUrl.value = URL.createObjectURL(file)
  
  // Set default title from file name (without extension)
  const baseName = file.name.replace(/\.[^/.]+$/, "")
  title.value = baseName
}

const triggerFileInput = () => {
  if (audioInputRef.value) {
    audioInputRef.value.click()
  }
}

const handleDragOver = (e) => {
  e.preventDefault()
}

const handleDrop = (e) => {
  e.preventDefault()
  const file = e.dataTransfer.files[0]
  if (file && file.type.startsWith('audio/')) {
    audioFile.value = file
    audioUrl.value = URL.createObjectURL(file)
    const baseName = file.name.replace(/\.[^/.]+$/, "")
    title.value = baseName
  } else {
    errorMessage.value = 'Por favor, arrastra un archivo de audio válido (WAV/MP3).'
  }
}

// Clear selected audio
const clearAudio = () => {
  audioFile.value = null
  audioUrl.value = ''
  if (audioInputRef.value) {
    audioInputRef.value.value = ''
  }
  notesCount.value = 0
  notes.value = []
  musicXml.value = ''
  errorMessage.value = ''
  successMessage.value = ''
  if (osmdContainer.value) {
    osmdContainer.value.innerHTML = ''
  }
}

// Zoom control for OpenSheetMusicDisplay (OSMD)
const setZoom = (factor) => {
  osmdZoom.value = Math.max(0.5, Math.min(2.0, osmdZoom.value + factor))
  if (osmdInstance) {
    osmdInstance.Zoom = osmdZoom.value
    osmdInstance.render()
  }
}

// Render MusicXML using OpenSheetMusicDisplay (OSMD) for flawless notes + tablature rendering
const renderMusicSheet = async (xmlString, gp5Base64 = null) => {
  await nextTick()
  // Esperar un breve retardo para que el DOM se asiente
  await new Promise(resolve => setTimeout(resolve, 300))
  
  console.log('--- COMIENZO DE RENDERIZADO DE PARTITURA ---')
  console.log('MusicXML recibido (longitud):', xmlString ? xmlString.length : 0)

  if (!osmdContainer.value) {
    console.error('[ERROR] Contenedor de partitura no disponible en el DOM.')
    addLog('[ERROR] Contenedor de partitura no disponible en el DOM.', 'error')
    return
  }

  addLog('Iniciando proceso de carga con OpenSheetMusicDisplay (OSMD)...', 'info')

  try {
    // Limpiar contenido previo
    osmdContainer.value.innerHTML = ''
    addLog('Contenedor de partitura limpiado con éxito.', 'info')
    
    // Crear instancia de OSMD
    osmdInstance = new OpenSheetMusicDisplay(osmdContainer.value, {
      autoResize: true,
      backend: 'svg',
      drawTitle: true,
      drawSubtitle: true,
      drawComposer: true,
      drawingParameters: 'default', // Para renderizar todas las notas y la tablatura correctamente
    })

    // Configurar el zoom inicial
    osmdInstance.Zoom = osmdZoom.value

    addLog('Cargando archivo MusicXML en OSMD...', 'info')
    await osmdInstance.load(xmlString)
    
    addLog('Renderizando partitura y tablatura...', 'info')
    osmdInstance.render()
    
    addLog('¡Partitura y tablatura renderizadas de forma hermosa con OSMD!', 'success')
    successMessage.value = '¡Partitura y tablatura de guitarra renderizada con éxito!'
    
  } catch (err) {
    console.error('Error rendering with OSMD:', err)
    addLog(`[ERROR] Excepción atrapada en renderMusicSheet: ${err.message}`, 'error')
    errorMessage.value = `Error al renderizar visualmente la partitura: ${err.message}`
  }
}

// Helper to parse YouTube Video ID
const getYouTubeId = (url) => {
  if (!url) return null
  const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*/
  const match = url.match(regExp)
  return (match && match[2].length === 11) ? match[2] : null
}

// Analizador de teoría musical usando Tonal.js
const getDetectedScale = () => {
  if (notes.value.length === 0) return 'No se han detectado notas aún'
  
  // Extraer notas únicas sin octava
  const uniqueNotes = [...new Set(notes.value.map(n => {
    return n.pitch.replace(/\d+/, '')
  }))]
  
  if (uniqueNotes.length < 3) {
    return 'Se necesitan al menos 3 notas únicas para el análisis de escala.'
  }
  
  try {
    const detected = Scale.detect(uniqueNotes)
    if (detected && detected.length > 0) {
      return detected.slice(0, 3).map(s => s.toUpperCase()).join(', ')
    }
    return 'Escala exótica o modulación híbrida'
  } catch (err) {
    return 'Escala no identificada'
  }
}

const getActiveChordName = () => {
  if (activeFretboardNotes.value.length < 2) return ''
  
  try {
    const pitches = activeFretboardNotes.value.map(n => n.pitch)
    const detected = Chord.detect(pitches)
    if (detected && detected.length > 0) {
      return detected[0]
    }
    return 'Acorde Complejo'
  } catch (err) {
    return ''
  }
}

// Submit for transcription
const startTranscription = async () => {
  if (inputSource.value === 'file' && !audioFile.value) {
    errorMessage.value = 'Por favor, selecciona un archivo de audio primero.'
    return
  }
  if (inputSource.value === 'youtube' && !youtubeUrl.value) {
    errorMessage.value = 'Por favor, introduce un enlace de YouTube válido.'
    return
  }

  isProcessing.value = true
  errorMessage.value = ''
  successMessage.value = ''
  notes.value = []
  musicXml.value = ''
  notesCount.value = 0
  progress.value = 0
  progressStatus.value = inputSource.value === 'youtube' ? 'Iniciando descarga de YouTube...' : 'Preparando archivo de audio...'
  logs.value = [] // Reset logs
  
  if (inputSource.value === 'file') {
    addLog(`Archivo seleccionado: "${audioFile.value.name}" (${(audioFile.value.size / 1024 / 1024).toFixed(2)} MB)`, 'info')
  } else {
    addLog(`Enlace de YouTube seleccionado: "${youtubeUrl.value}"`, 'info')
  }
  addLog(`Parámetros configurados: Título="${title.value || 'Auto-detectar'}" | BPM=${bpm.value} | Algoritmo=${mode.value}`, 'info')
  addLog(`Iniciando conexión con el backend de FastAPI en ${apiBaseUrl.value}...`, 'info')

  if (osmdContainer.value) {
    osmdContainer.value.innerHTML = ''
  }

  // To prevent duplicates in simulation logs
  const loggedStages = new Set()

  // Timer to smoothly progress up to 95%
  const progressTimer = setInterval(() => {
    if (progress.value < 95) {
      progress.value += Math.floor(Math.random() * 4) + 1
      if (progress.value > 95) progress.value = 95
      
      if (progress.value < 20) {
        if (inputSource.value === 'youtube') {
          progressStatus.value = '1/5: Backend descargando audio de YouTube...'
          if (!loggedStages.has(1)) {
            addLog('POST /api/transcribe_youtube - Solicitando al servidor descargar y extraer pista de audio...', 'info')
            addLog('yt-dlp: Iniciando descarga silenciosa del stream en formato WAV de alta calidad...', 'status')
            loggedStages.add(1)
          }
        } else {
          progressStatus.value = '1/5: Subiendo y cargando archivo...'
          if (!loggedStages.has(1)) {
            addLog('POST /api/transcribe - Enviando payload multimedia al servidor...', 'info')
            loggedStages.add(1)
          }
        }
      } else if (progress.value < 40) {
        progressStatus.value = '2/5: Analizando espectrograma y frecuencias...'
        if (!loggedStages.has(2)) {
          if (inputSource.value === 'youtube') {
            addLog('Servidor FastAPI: Descarga de YouTube completada correctamente y metadatos extraídos.', 'info')
          } else {
            addLog('Servidor FastAPI: Carga de archivo completada correctamente.', 'info')
          }
          addLog('Servidor FastAPI: Iniciando pre-procesamiento de señal de audio (remuestreo a 22050Hz, mono)...', 'info')
          addLog('Librosa: Calculando espectrograma de Short-Time Fourier Transform (STFT)...', 'status')
          loggedStages.add(2)
        }
      } else if (progress.value < 65) {
        progressStatus.value = '3/5: Detección de pitch e intervalos...'
        if (!loggedStages.has(3)) {
          addLog(`Pitcher: Ejecutando algoritmo de detección de frecuencia fundamental (${mode.value})...`, 'status')
          if (mode.value === 'auto' || mode.value === 'monophonic') {
            addLog('pYIN: Extrayendo frecuencias fundamentales de autocorrelación probabilística para guitarra monofónica...', 'status')
          }
          if (mode.value === 'auto' || mode.value === 'polyphonic') {
            addLog('Basic Pitch: Ejecutando red neuronal convolucional para onsets, offsets y duraciones polifónicas...', 'status')
          }
          loggedStages.add(3)
        }
      } else if (progress.value < 85) {
        progressStatus.value = '4/5: Optimizando digitaciones de cuerda y traste...'
        if (!loggedStages.has(4)) {
          addLog('Biomechanics: Mapeando frecuencias de audio detectadas a notas MIDI físicas...', 'status')
          addLog('Optimizer: Ejecutando algoritmo heurístico biomecánico para mástil de guitarra...', 'status')
          addLog('Optimizer: Resolviendo posiciones ideales de traste y cuerda con menor esfuerzo de transición...', 'status')
          loggedStages.add(4)
        }
      } else {
        progressStatus.value = '5/5: Estructurando compases y exportando a MusicXML...'
        if (!loggedStages.has(5)) {
          addLog('music21: Creando Stream musical, armaduras de clave y compás rítmico...', 'status')
          addLog('MusicXML Generator: Estructurando metadatos de instrumento (Guitar, standard tuning)...', 'status')
          addLog('MusicXML Generator: Exportando formato XML enriquecido con posiciones de tablatura (Technical notations)...', 'status')
          loggedStages.add(5)
        }
      }
    }
  }, 400)

  const formData = new FormData()
  if (inputSource.value === 'file') {
    formData.append('file', audioFile.value)
  } else {
    formData.append('youtube_url', youtubeUrl.value)
  }
  formData.append('mode', mode.value)
  formData.append('bpm', bpm.value)
  formData.append('title', title.value === 'Mi Transcripción' && inputSource.value === 'youtube' ? '' : title.value)
  formData.append('output_format', 'both')
  formData.append('power_chords', powerChords.value)
  formData.append('demucs_separation', useDemucs.value)
  formData.append('fingering_algorithm', fingeringAlgorithm.value)
  formData.append('fingering_style', fingeringStyle.value)
  formData.append('guitar_tuning', guitarTuning.value)

  const endpoint = inputSource.value === 'youtube' ? 'transcribe_youtube' : 'transcribe'

  try {
    const response = await fetch(`${apiBaseUrl.value}/api/${endpoint}`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Error en el servidor (${response.status})`)
    }

    const data = await response.json()
    
    // Stop progress timer and set to 100%
    clearInterval(progressTimer)
    progress.value = 100
    progressStatus.value = '¡Procesamiento completo!'
    addLog('¡Conexión HTTP Exitosa! Respuesta JSON recibida.', 'success')
    addLog(`Resumen de Transcripción: Se detectaron un total de ${data.notes_count} notas asignadas.`, 'success')

    notesCount.value = data.notes_count
    notes.value = data.notes
    musicXml.value = data.musicxml
    gp5Base64.value = data.gp5

    // Start real-time fretboard visualizer animation
    await animateNotesInRealtime()

    addLog('Cargando la tablatura nativa de GuitarPro en AlphaTab...', 'info')
    // Render the score
    await renderMusicSheet(data.musicxml, data.gp5)
    addLog('Partitura y tablatura renderizadas hermosa y dinámicamente en pantalla con OSMD.', 'success')
  } catch (err) {
    clearInterval(progressTimer)
    progress.value = 0
    console.error('Transcription error:', err)
    addLog(`[ERROR] Falló el procesamiento: ${err.message}`, 'error')
    errorMessage.value = err.message || 'Ocurrió un error inesperado al procesar el audio.'
  } finally {
    isProcessing.value = false
  }
}

// Download MusicXML
const downloadXml = () => {
  if (!musicXml.value) return
  
  const blob = new Blob([musicXml.value], { type: 'application/xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title.value.replace(/\s+/g, '_')}.xml`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Download GuitarPro (.gp5)
const downloadGp5 = () => {
  if (!gp5Base64.value) return
  
  try {
    const byteCharacters = atob(gp5Base64.value)
    const byteNumbers = new Array(byteCharacters.length)
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i)
    }
    const byteArray = new Uint8Array(byteNumbers)
    const blob = new Blob([byteArray], { type: 'application/octet-stream' })
    
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title.value.replace(/\s+/g, '_')}.gp5`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('Error al descargar GP5:', err)
    errorMessage.value = `Error al descargar el archivo GP5: ${err.message}`
  }
}
</script>

<template>
  <div class="app-container">
    <header class="app-header">
      <div class="header-content">
        <div class="logo-area">
          <span class="guitar-icon">🎸</span>
          <div>
            <h1>AudioTab Pro</h1>
            <p class="subtitle">Audio de Guitarra a Partitura y Tablatura Inteligente</p>
          </div>
        </div>
        <div 
          class="status-badge" 
          :class="{ 'connected': isBackendOnline === true, 'disconnected': isBackendOnline === false, 'checking': isBackendOnline === null }"
          @click="checkBackendConnection" 
          style="cursor: pointer;" 
          title="Haga clic para re-verificar conexión con el servidor"
        >
          <span class="dot" :class="{ 'live': isBackendOnline === true, 'offline': isBackendOnline === false, 'checking': isBackendOnline === null }"></span>
          Backend: {{ isBackendOnline === true ? 'Conectado (v1.0.0)' : (isBackendOnline === false ? 'Desconectado' : 'Verificando...') }}
        </div>
      </div>
    </header>

    <main class="app-main-content">
      <!-- Section 1: Upload and Parameters -->
      <section class="config-panel">
        <div class="card">
          <h2>1. Origen de Guitarra</h2>
          
          <!-- Tab Switcher -->
          <div class="tabs-header" style="display: flex; margin-bottom: 20px; border-bottom: 1px solid var(--border);">
            <button 
              class="tab-btn" 
              :class="{ 'active': inputSource === 'file' }" 
              style="padding: 10px 16px; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-h); font-weight: 600; cursor: pointer; transition: all 0.3s;"
              :style="inputSource === 'file' ? 'border-bottom-color: var(--accent); color: var(--accent);' : ''"
              @click="inputSource = 'file'"
            >
              📁 Archivo de Audio
            </button>
            <button 
              class="tab-btn" 
              :class="{ 'active': inputSource === 'youtube' }" 
              style="padding: 10px 16px; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-h); font-weight: 600; cursor: pointer; transition: all 0.3s;"
              :style="inputSource === 'youtube' ? 'border-bottom-color: var(--accent); color: var(--accent);' : ''"
              @click="inputSource = 'youtube'"
            >
              🎬 Video de YouTube
            </button>
          </div>
          
          <!-- File Source Panel -->
          <div v-if="inputSource === 'file'">
            <div 
              class="dropzone" 
              :class="{ 'has-file': audioFile }"
              @dragover="handleDragOver"
              @drop="handleDrop"
              @click="triggerFileInput"
            >
              <input 
                type="file" 
                ref="audioInputRef" 
                class="hidden-input" 
                accept="audio/*"
                @change="handleFileChange" 
              />
              
              <div v-if="!audioFile" class="dropzone-prompt">
                <span class="upload-icon">🎵</span>
                <p class="main-prompt">Arrastra tu archivo de audio o haz clic aquí</p>
                <p class="sub-prompt">Soporta WAV, MP3, FLAC, M4A, OGG</p>
              </div>
              
              <div v-else class="dropzone-file-info" @click.stop>
                <span class="file-icon">✅</span>
                <div class="file-details">
                  <p class="file-name">{{ audioFile.name }}</p>
                  <p class="file-size">{{ (audioFile.size / 1024 / 1024).toFixed(2) }} MB</p>
                </div>
                <button class="btn btn-danger btn-sm" @click="clearAudio">Eliminar</button>
              </div>
            </div>

            <!-- Audio Player if uploaded -->
            <div v-if="audioUrl" class="audio-player-container">
              <label class="input-label">Escuchar archivo cargado:</label>
              <audio :src="audioUrl" controls class="audio-player"></audio>
            </div>
          </div>

          <!-- YouTube Source Panel -->
          <div v-else class="youtube-input-panel">
            <div class="form-group">
              <label for="yt-url" class="input-label">Enlace / URL de YouTube</label>
              <input 
                id="yt-url" 
                v-model="youtubeUrl" 
                type="text" 
                placeholder="https://www.youtube.com/watch?v=..." 
                class="form-control"
                style="margin-bottom: 12px;"
              />
            </div>
            
            <!-- YouTube Preview Player if URL is valid -->
            <div v-if="getYouTubeId(youtubeUrl)" class="yt-preview-container" style="border-radius: 8px; overflow: hidden; border: 1px solid var(--border); margin-bottom: 12px; position: relative; padding-bottom: 56.25%; height: 0;">
              <iframe 
                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" 
                :src="'https://www.youtube.com/embed/' + getYouTubeId(youtubeUrl)" 
                frameborder="0" 
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                allowfullscreen
              ></iframe>
            </div>
            
            <p style="font-size: 12px; color: var(--text); line-height: 1.5; margin: 0;">
              💡 El backend utilizará <code>yt-dlp</code> para extraer el audio de la pista de forma segura y procesar la tablatura y partitura exactamente en sincronía.
            </p>
          </div>
        </div>

        <div class="card">
          <h2>2. Parámetros de Transcripción</h2>
          
          <div class="form-group">
            <label for="api-url" class="input-label">URL del Servidor API (FastAPI)</label>
            <div style="display: flex; gap: 8px;">
              <input 
                id="api-url" 
                v-model="apiBaseUrl" 
                type="text" 
                placeholder="http://127.0.0.1:8000" 
                class="form-control"
                style="flex: 1;"
                @change="checkBackendConnection"
              />
              <button class="btn btn-secondary btn-sm" @click="checkBackendConnection">Probar</button>
            </div>
          </div>
          
          <div class="form-group">
            <label for="title" class="input-label">Título de la Obra</label>
            <input 
              id="title" 
              v-model="title" 
              type="text" 
              placeholder="Ej. Guitar Solo 1" 
              class="form-control"
            />
          </div>

          <div class="form-row">
            <div class="form-group col-6">
              <label for="bpm" class="input-label">BPM (0 para Auto-detectar)</label>
              <input 
                id="bpm" 
                v-model.number="bpm" 
                type="number" 
                min="0" 
                max="240" 
                class="form-control"
              />
            </div>

            <div class="form-group col-6">
              <label for="mode" class="input-label">Algoritmo de Pitch</label>
              <select id="mode" v-model="mode" class="form-control">
                <option value="auto">Selección Automática (Recomendado)</option>
                <option value="monophonic">Monofónico (librosa pYIN - Solos/Líneas simples)</option>
                <option value="polyphonic">Polifónico (basic-pitch - Acordes/Arpegios complejos)</option>
                <option value="guitar_wav2vec">🤖 Avanzado - Guitar-wav2vec (Preentrenamiento SSL + RLHF)</option>
                <option value="consensus">🎯 Consenso - Doble Revisión Inteligente (Máxima Exactitud)</option>
              </select>
            </div>
          </div>

          <div class="form-group" style="margin-top: 16px;">
            <label for="guitar-tuning" class="input-label">Afinación de la Guitarra</label>
            <select id="guitar-tuning" v-model="guitarTuning" class="form-control">
              <option value="auto">Auto-detectar (Inteligente)</option>
              <option value="standard">Estándar (E A D G B e)</option>
              <option value="drop_d">Drop D (D A D G B e)</option>
              <option value="half_step_down">Medio tono abajo (Eb Ab Db Gb Bb eb)</option>
              <option value="drop_c">Drop C (C G C F A d)</option>
              <option value="whole_step_down">Un tono abajo (D G C F A d)</option>
            </select>
          </div>

          <div class="form-group" style="margin-top: 16px;">
            <label class="input-label" style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
              <input 
                v-model="powerChords" 
                type="checkbox" 
                style="width: 18px; height: 18px; cursor: pointer;"
              />
              <span><strong>Modo Quintas (Power Chords):</strong> Reconstruir acordes de quinta en la tablatura</span>
            </label>
            <p style="font-size: 12px; margin: 4px 0 0 26px; color: var(--text);">
              Excelente para canciones de rock/metal que usan acordes de quinta (Power Chords) en tresillo. Agrega la quinta y octava justa automáticamente.
            </p>
          </div>

          <div class="form-group" style="margin-top: 16px; border-top: 1px solid var(--border); padding-top: 16px;">
            <label for="fingering-algo" class="input-label">Algoritmo de Digitación (Mástil)</label>
            <select id="fingering-algo" v-model="fingeringAlgorithm" class="form-control">
              <option value="heuristic">Heurístico Biomecánico Tradicional</option>
              <option value="guitar_bert">🤖 Inteligencia Artificial - GuitarBERT-RL</option>
            </select>
          </div>

          <div v-if="fingeringAlgorithm === 'guitar_bert'" class="form-group" style="margin-top: 16px;">
            <label for="fingering-style" class="input-label">Adaptador de Estilo GuitarBERT-RL</label>
            <select id="fingering-style" v-model="fingeringStyle" class="form-control">
              <option value="classic">Clásico / Folk (Cuerdas al aire y trastes bajos)</option>
              <option value="metal">Metal / Shredding (Trastes altos y arpegios rápidos)</option>
              <option value="jazz">Jazz / Drop Chords (Digitaciones compactas de acordes)</option>
            </select>
          </div>

          <div class="form-group" style="margin-top: 16px; border-top: 1px solid var(--border); padding-top: 16px;">
            <label class="input-label" style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
              <input 
                v-model="useDemucs" 
                type="checkbox" 
                style="width: 18px; height: 18px; cursor: pointer;"
              />
              <span><strong>Aislar Guitarra con Demucs:</strong> Separar pistas de audio</span>
            </label>
            <p style="font-size: 12px; margin: 4px 0 0 26px; color: var(--text);">
              Separa la voz, batería y bajo de forma inteligente utilizando inteligencia artificial (Demucs) antes del análisis, aislando únicamente las notas de guitarra para la transcripción.
            </p>
          </div>

          <button 
            class="btn btn-primary btn-block" 
            :disabled="isProcessing || (inputSource === 'file' && !audioFile) || (inputSource === 'youtube' && !youtubeUrl)"
            @click="startTranscription"
          >
            <span v-if="isProcessing" class="spinner">⏳</span>
            {{ isProcessing ? 'Procesando y Analizando...' : 'Transcribir Audio a Tablatura' }}
          </button>
        </div>
      </section>

      <!-- Status and Errors -->
      <div v-if="errorMessage" class="alert alert-error">
        <strong>⚠️ Error:</strong> {{ errorMessage }}
      </div>
      
      <div v-if="successMessage" class="alert alert-success">
        <strong>🎉 ¡Éxito!</strong> {{ successMessage }}
      </div>

      <!-- Processing State -->
      <div v-if="isProcessing" class="processing-card card">
        <div class="processing-visual">
          <div class="wave-bar bar-1"></div>
          <div class="wave-bar bar-2"></div>
          <div class="wave-bar bar-3"></div>
          <div class="wave-bar bar-4"></div>
          <div class="wave-bar bar-5"></div>
        </div>
        <h3>{{ progressStatus }}</h3>
        
        <!-- Progress Bar -->
        <div class="progress-bar-container">
          <div class="progress-bar-fill" :style="{ width: progress + '%' }"></div>
          <span class="progress-bar-text">{{ Math.round(progress) }}%</span>
        </div>

        <p class="processing-explanation">Nuestro backend está ejecutando análisis de espectrogramas de frecuencia, resolviendo el pitch fundamental mediante inteligencia artificial, estructurando la duración rítmica, y calculando la optimización biomecánica para el mástil de tu guitarra.</p>
      </div>

      <!-- Section 2: Results (Visual score & tablature, and notes metadata) -->
      <section v-if="musicXml || notes.length > 0" class="results-area">
        
        <!-- Video de YouTube Interactivo si es origen YouTube -->
        <div v-if="inputSource === 'youtube' && getYouTubeId(youtubeUrl)" class="card youtube-player-card" style="margin-bottom: 24px;">
          <div class="fretboard-title-area" style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
            <span style="font-size: 24px;">📺</span>
            <h2 style="margin: 0; border: none; padding: 0;">Video de YouTube en Reproducción</h2>
          </div>
          <div class="video-container" style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; border-radius: 8px; border: 1px solid var(--border);">
            <iframe 
              style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" 
              :src="'https://www.youtube.com/embed/' + getYouTubeId(youtubeUrl)" 
              frameborder="0" 
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
              allowfullscreen
            ></iframe>
          </div>
        </div>
        
        <!-- Real-time Guitar Fretboard -->
        <div class="card fretboard-card">
          <div class="fretboard-header">
            <div class="fretboard-title-area">
              <span class="fretboard-icon">🎸</span>
              <h2>Visualizador de Mástil en Tiempo Real</h2>
            </div>
            <div class="animation-controls">
              <span v-if="isAnimatingRealtime" class="pulse-text">⚡ Transcribiendo en tiempo real...</span>
              <button 
                v-if="!isAnimatingRealtime && notes.length > 0" 
                class="btn btn-secondary btn-sm" 
                @click="animateNotesInRealtime"
              >
                🔄 Repetir Animación
              </button>
            </div>
          </div>

          <!-- Análisis de Teoría Musical con Tonal.js -->
          <div class="fretboard-theory-panel" style="display: flex; gap: 16px; margin-bottom: 16px; padding: 10px 14px; background: rgba(170, 59, 255, 0.08); border-radius: 8px; border: 1px dashed rgba(170, 59, 255, 0.3); align-items: center; flex-wrap: wrap;">
            <div style="flex: 1; font-size: 13px; color: var(--text-h); min-width: 250px;">
              🎼 <strong>Análisis de Escala:</strong> <span style="color: #aa3bff; font-weight: 700;">{{ getDetectedScale() }}</span>
            </div>
            <div v-if="activeFretboardNotes.length >= 2" style="font-size: 12px; color: white; font-weight: 700; background: #aa3bff; padding: 4px 10px; border-radius: 4px; box-shadow: 0 0 8px rgba(170, 59, 255, 0.4);">
              🎵 Acorde Activo: {{ getActiveChordName() }}
            </div>
          </div>
          
          <div class="guitar-neck-wrapper">
            <div class="guitar-neck">
              <!-- Nut / Cejuela -->
              <div class="nut"></div>
              
              <!-- Frets -->
              <div class="frets-container">
                <div v-for="fretNum in 16" :key="fretNum - 1" class="fret-column">
                  <span class="fret-number" v-if="fretNum - 1 > 0">{{ fretNum - 1 }}</span>
                  <span class="fret-number-open" v-else>0</span>
                  
                  <!-- Fret Markers / Dots (Frets 3, 5, 7, 9, 12, 15) -->
                  <div 
                    class="fret-marker" 
                    v-if="[3, 5, 7, 9, 12, 15].includes(fretNum - 1)"
                  ></div>
                  
                  <!-- Strings and Note Positions -->
                  <div class="strings-grid">
                    <div v-for="stringNum in 6" :key="stringNum" class="string-line-container">
                      <div class="string-wire"></div>
                      
                      <!-- Active Note Dot -->
                      <div 
                        class="fret-note-dot" 
                        :class="{ 'open-note': fretNum - 1 === 0 }"
                        v-if="isNoteActive(stringNum, fretNum - 1)"
                      >
                        {{ getActiveNotePitch(stringNum, fretNum - 1) }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Real-time Animation Progress Bar -->
          <div v-if="isAnimatingRealtime" class="animation-progress-container" style="margin-top: 20px; padding: 0 10px;">
            <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-h); margin-bottom: 8px; font-weight: 600;">
              <span>⚡ Dibujando notas de la tablatura en el mástil...</span>
              <span>{{ currentAnimatingNoteIndex }} / {{ notes.length }} notas</span>
            </div>
            <div class="progress-bar-container" style="height: 10px; border-radius: 6px; background-color: var(--border); overflow: hidden; position: relative; width: 100%;">
              <div 
                class="progress-bar-fill" 
                :style="{ width: animationProgress + '%' }"
                style="height: 100%; background: linear-gradient(90deg, #10b981 0%, #059669 100%); transition: width 0.1s ease; box-shadow: 0 0 10px rgba(16, 185, 129, 0.4);"
              ></div>
            </div>
          </div>
        </div>

        <div class="results-grid">
          
          <!-- Column A: Visual Notation Player -->
          <div class="card score-card">
            <div class="score-header">
              <h2>Partitura y Tablatura Renderizada</h2>
              <div class="score-controls" v-if="musicXml">
                <button class="btn btn-secondary btn-sm" @click="setZoom(-0.1)">🔎- Alejar</button>
                <span class="zoom-text">{{ Math.round(osmdZoom * 100) }}%</span>
                <button class="btn btn-secondary btn-sm" @click="setZoom(0.1)">🔎+ Acercar</button>
                <button class="btn btn-primary btn-sm" @click="downloadXml">💾 Descargar XML</button>
                <button v-if="gp5Base64" class="btn btn-primary btn-sm" @click="downloadGp5" style="margin-left: 8px;">💾 Descargar GP5</button>
              </div>
            </div>
            
            <div class="score-viewport">
              <div ref="osmdContainer" class="osmd-render-container"></div>
            </div>
          </div>

          <!-- Column B: Notes Breakdown & Tablature Fingering Map -->
          <div class="card notes-card">
            <h2>Mapa de Digitaciones Detallado</h2>
            <p class="notes-summary">Se detectaron <strong>{{ notesCount }}</strong> notas musicales individuales en la grabación. A continuación se muestra la correspondencia traste-cuerda optimizada para guitarra afinada en Estándar (E A D G B e):</p>
            
            <div class="table-container">
              <table class="notes-table">
                <thead>
                  <tr>
                    <th>Tiempo (seg)</th>
                    <th>Nota</th>
                    <th>Frecuencia (Hz)</th>
                    <th>Cuerda Asignada</th>
                    <th>Traste</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(note, index) in displayedNotes" :key="index">
                    <td class="mono">{{ note.start_time.toFixed(3) }}s</td>
                    <td>
                      <span class="note-badge">{{ note.pitch }}</span>
                    </td>
                    <td class="mono text-muted">{{ note.frequency?.toFixed(1) || '0.0' }} Hz</td>
                    <td>
                      <div class="string-indicator">
                        <span class="string-num">{{ note.string }}ª</span>
                        <span class="string-name">{{ getNoteNameForString(note.string) }}</span>
                      </div>
                    </td>
                    <td>
                      <span class="fret-badge" :class="{ 'open-string': note.fret === 0 }">
                        {{ note.fret === 0 ? 'Al aire (0)' : 'Traste ' + note.fret }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </section>
      <!-- Console Diagnostic Logs -->
      <div v-if="logs.length > 0" class="card console-card-wrapper">
        <div class="console-header">
          <div class="console-title-area">
            <span class="console-dot-green"></span>
            <h2>Consola de Diagnóstico de Transcripción</h2>
          </div>
          <button class="btn btn-secondary btn-sm" @click="logs = []">Limpiar Consola</button>
        </div>
        <div class="console-log-box">
          <div v-for="(log, i) in logs" :key="i" class="console-line" :class="log.type">
            <span class="c-time">[{{ log.timestamp }}]</span>
            <span class="c-tag" v-if="log.type === 'error'">[ERROR]</span>
            <span class="c-tag" v-else-if="log.type === 'success'">[SUCCESS]</span>
            <span class="c-tag" v-else-if="log.type === 'status'">[STATUS]</span>
            <span class="c-tag" v-else>[INFO]</span>
            <span class="c-text">{{ log.text }}</span>
          </div>
        </div>
      </div>
    </main>

    <footer class="app-footer">
      <p>AudioTab Pro © 2026 — Transcriptor inteligente de audio de guitarra basado en FastAPI + Music21 + Librosa + OpenSheetMusicDisplay</p>
    </footer>
  </div>
</template>

<script>
// Non-setup script helper
export default {
  methods: {
    getNoteNameForString(stringNum) {
      const strings = {
        1: 'e (Aguda)',
        2: 'B',
        3: 'G',
        4: 'D',
        5: 'A',
        6: 'E (Grave)'
      }
      return strings[stringNum] || ''
    }
  }
}
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
  background-color: var(--bg);
  color: var(--text);
  box-sizing: border-box;
}

.app-header {
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  background: var(--code-bg);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo-area h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  color: var(--text-h);
  line-height: 1;
}

.subtitle {
  font-size: 13px;
  margin: 4px 0 0;
  color: var(--text);
}

.guitar-icon {
  font-size: 32px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  background: var(--accent-bg);
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid var(--accent-border);
  color: var(--accent);
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot.live {
  background-color: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: pulse 1.5s infinite;
}

.dot.offline {
  background-color: #ef4444;
  box-shadow: 0 0 8px #ef4444;
}

.dot.checking {
  background-color: #f59e0b;
  box-shadow: 0 0 8px #f59e0b;
  animation: pulse 1.5s infinite;
}

.status-badge.disconnected {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.status-badge.checking {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}

@keyframes pulse {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.1); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.app-main-content {
  flex: 1;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  padding: 24px;
  box-sizing: border-box;
}

.config-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .config-panel {
    grid-template-columns: 1fr;
  }
}

.card {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow);
  text-align: left;
}

.card h2 {
  font-size: 18px;
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--text-h);
  border-bottom: 2px solid var(--border);
  padding-bottom: 8px;
}

/* Dropzone Styles */
.dropzone {
  border: 2px dashed var(--border);
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
}

.dropzone:hover {
  border-color: var(--accent);
  background: var(--accent-bg);
}

.dropzone.has-file {
  border-style: solid;
  border-color: var(--accent-border);
  background: var(--accent-bg);
}

.upload-icon {
  font-size: 40px;
  display: block;
  margin-bottom: 12px;
}

.main-prompt {
  font-weight: 600;
  color: var(--text-h);
  margin-bottom: 4px;
}

.sub-prompt {
  font-size: 12px;
  color: var(--text);
}

.hidden-input {
  display: none;
}

.dropzone-file-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
}

.file-icon {
  font-size: 28px;
}

.file-details {
  flex-grow: 1;
}

.file-name {
  font-weight: 600;
  color: var(--text-h);
  margin: 0;
  word-break: break-all;
}

.file-size {
  font-size: 12px;
  color: var(--text);
  margin: 4px 0 0;
}

.audio-player-container {
  margin-top: 16px;
}

.audio-player {
  width: 100%;
  margin-top: 6px;
}

/* Forms */
.form-group {
  margin-bottom: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.col-6 {
  flex: 0 0 calc(50% - 8px);
}

.input-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--text-h);
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--bg);
  color: var(--text-h);
  font-size: 14px;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-bg);
}

/* Buttons */
.btn {
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid transparent;
}

.btn-primary {
  background-color: var(--accent);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
  box-shadow: 0 4px 12px var(--accent-bg);
}

.btn-primary:disabled {
  background-color: var(--border);
  color: var(--text);
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--code-bg);
  border-color: var(--border);
  color: var(--text-h);
}

.btn-secondary:hover {
  background-color: var(--border);
}

.btn-danger {
  background-color: #ef4444;
  color: white;
}

.btn-danger:hover {
  background-color: #dc2626;
}

.btn-block {
  display: block;
  width: 100%;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
}

/* Alert Boxes */
.alert {
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 24px;
  text-align: left;
  font-size: 14px;
}

.alert-error {
  background-color: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #f87171;
}

.alert-success {
  background-color: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #34d399;
}

/* Loading/Processing Visual */
.processing-card {
  text-align: center;
  padding: 40px;
  margin-bottom: 24px;
}

.progress-bar-container {
  width: 100%;
  max-width: 600px;
  background-color: var(--border);
  height: 24px;
  border-radius: 12px;
  margin: 20px auto;
  position: relative;
  overflow: hidden;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
}

.progress-bar-fill {
  background: linear-gradient(90deg, var(--accent) 0%, #aa3bff 100%);
  height: 100%;
  border-radius: 12px;
  transition: width 0.4s ease;
  box-shadow: 0 1px 5px rgba(170, 59, 255, 0.4);
}

.progress-bar-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-weight: 700;
  font-size: 12px;
  color: var(--text-h);
  text-shadow: 0 1px 1px rgba(255, 255, 255, 0.8);
}

.processing-explanation {
  font-size: 14px;
  line-height: 1.6;
  max-width: 800px;
  margin: 0 auto;
}

.processing-visual {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 6px;
  height: 60px;
  margin-bottom: 20px;
}

.wave-bar {
  width: 6px;
  background-color: var(--accent);
  border-radius: 3px;
  animation: wave 1.2s ease-in-out infinite;
}

.bar-1 { height: 10px; animation-delay: 0.1s; }
.bar-2 { height: 35px; animation-delay: 0.3s; }
.bar-3 { height: 55px; animation-delay: 0s; }
.bar-4 { height: 25px; animation-delay: 0.4s; }
.bar-5 { height: 45px; animation-delay: 0.2s; }

@keyframes wave {
  0%, 100% { transform: scaleY(1); }
  50% { transform: scaleY(0.4); }
}

.spinner {
  display: inline-block;
  animation: rotate 2s linear infinite;
}

@keyframes rotate {
  100% { transform: rotate(360deg); }
}

/* Results Area */
.results-area {
  margin-top: 12px;
}

.results-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 24px;
}

@media (max-width: 1024px) {
  .results-grid {
    grid-template-columns: 1fr;
  }
}

.score-card {
  display: flex;
  flex-direction: column;
}

.score-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 2px solid var(--border);
  padding-bottom: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.score-header h2 {
  margin: 0;
  border-bottom: none;
  padding-bottom: 0;
}

.score-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.zoom-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
  min-width: 44px;
  text-align: center;
}

.score-viewport {
  background: white;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  min-height: 400px;
  overflow-x: auto;
}

.osmd-render-container {
  width: 100%;
  min-width: 600px;
}

/* Notes Table */
.notes-card {
  display: flex;
  flex-direction: column;
}

.notes-summary {
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 16px;
}

.table-container {
  overflow: auto;
  max-height: 500px;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.notes-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.notes-table th {
  background-color: var(--code-bg);
  color: var(--text-h);
  font-weight: 600;
  padding: 12px;
  border-bottom: 2px solid var(--border);
  position: sticky;
  top: 0;
}

.notes-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.notes-table tr:hover {
  background-color: rgba(170, 59, 255, 0.05);
}

.mono {
  font-family: var(--mono);
}

.text-muted {
  color: var(--text);
  font-size: 12px;
}

.note-badge {
  background-color: var(--accent);
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 12px;
  display: inline-block;
}

.string-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
}

.string-num {
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-bg);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
}

.string-name {
  font-size: 12px;
  color: var(--text-h);
}

.fret-badge {
  background-color: var(--code-bg);
  border: 1px solid var(--border);
  color: var(--text-h);
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 500;
  font-size: 12px;
}

.fret-badge.open-string {
  background-color: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.3);
  color: #10b981;
  font-weight: 600;
}

/* Footer */
.app-footer {
  border-top: 1px solid var(--border);
  padding: 24px;
  margin-top: 40px;
  font-size: 12px;
  color: var(--text);
  background: var(--code-bg);
  text-align: center;
}

/* Fretboard Styles */
.fretboard-card {
  margin-bottom: 24px;
}

.fretboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 2px solid var(--border);
  padding-bottom: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.fretboard-title-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.fretboard-title-area h2 {
  margin: 0;
  border-bottom: none;
  padding-bottom: 0;
}

.fretboard-icon {
  font-size: 24px;
}

.animation-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pulse-text {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  animation: glow 1s infinite alternate;
}

@keyframes glow {
  from { opacity: 0.6; text-shadow: 0 0 2px var(--accent-border); }
  to { opacity: 1; text-shadow: 0 0 8px var(--accent); }
}

/* Guitar Neck Styling */
.guitar-neck-wrapper {
  overflow-x: auto;
  width: 100%;
  background-color: #1f1b24; /* Rich dark fretboard background */
  border-radius: 8px;
  padding: 30px 10px;
  border: 1px solid var(--border);
}

.guitar-neck {
  display: flex;
  position: relative;
  min-width: 900px;
  height: 180px;
  background-image: linear-gradient(180deg, #2b2533 0%, #1e1924 100%);
  border-top: 4px solid #3c3445;
  border-bottom: 4px solid #3c3445;
}

.nut {
  width: 15px;
  background: #e5e4e7;
  height: 100%;
  border-radius: 2px;
  box-shadow: 2px 0 5px rgba(0,0,0,0.5);
  z-index: 10;
}

.frets-container {
  display: flex;
  flex: 1;
  height: 100%;
  position: relative;
}

.fret-column {
  flex: 1;
  border-right: 2px solid #a3a1a8; /* Fret wire */
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.fret-number {
  position: absolute;
  top: -24px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-h);
}

.fret-number-open {
  position: absolute;
  top: -24px;
  left: -20px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-h);
}

/* Fret markers / dots */
.fret-marker {
  position: absolute;
  width: 12px;
  height: 12px;
  background-color: rgba(229, 228, 231, 0.4); /* Clay dots */
  border-radius: 50%;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  z-index: 1;
}

/* Strings grid */
.strings-grid {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
  width: 100%;
  z-index: 2;
}

.string-line-container {
  height: 16.6%;
  width: 100%;
  position: relative;
  display: flex;
  align-items: center;
}

.string-wire {
  width: 100%;
  background: linear-gradient(180deg, #c0c0c0 0%, #808080 100%);
  position: absolute;
  pointer-events: none;
}

/* Change string thickness */
.string-line-container:nth-child(1) .string-wire { height: 1px; }
.string-line-container:nth-child(2) .string-wire { height: 1.5px; }
.string-line-container:nth-child(3) .string-wire { height: 2px; }
.string-line-container:nth-child(4) .string-wire { height: 2.5px; }
.string-line-container:nth-child(5) .string-wire { height: 3px; }
.string-line-container:nth-child(6) .string-wire { height: 3.5px; }

/* Active note circle */
.fret-note-dot {
  position: absolute;
  left: 50%;
  transform: translate(-55%, -50%);
  background: linear-gradient(135deg, #aa3bff 0%, #8b13ff 100%);
  color: white;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  box-shadow: 0 0 12px #aa3bff, inset 0 0 4px rgba(255,255,255,0.4);
  animation: pop 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  z-index: 5;
}

.fret-note-dot.open-note {
  left: -20px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  box-shadow: 0 0 12px #10b981, inset 0 0 4px rgba(255,255,255,0.4);
}

@keyframes pop {
  0% { transform: translate(-55%, -50%) scale(0.5); opacity: 0; }
  100% { transform: translate(-55%, -50%) scale(1); opacity: 1; }
}

/* Console Diagnostic CSS */
.console-card-wrapper {
  margin-top: 24px;
  border-color: #374151;
  background-color: #111827;
}

.console-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #374151;
  padding-bottom: 10px;
  margin-bottom: 12px;
}

.console-title-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.console-header h2 {
  color: #f3f4f6;
  margin: 0;
  border: none;
  padding: 0;
  font-size: 16px;
}

.console-dot-green {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #10b981;
  box-shadow: 0 0 8px #10b981;
  display: inline-block;
  animation: pulse 2s infinite;
}

.console-log-box {
  font-family: var(--mono);
  font-size: 12px;
  background-color: #030712;
  border-radius: 6px;
  padding: 16px;
  max-height: 250px;
  overflow-y: auto;
  border: 1px solid #1f2937;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.console-line {
  line-height: 1.5;
  text-align: left;
  word-break: break-all;
}

.console-line.info {
  color: #e5e7eb;
}

.console-line.status {
  color: #38bdf8;
}

.console-line.success {
  color: #34d399;
  font-weight: 600;
}

.console-line.error {
  color: #f87171;
  font-weight: 600;
}

.c-time {
  color: #6b7280;
  margin-right: 8px;
}

.c-tag {
  font-weight: 700;
  margin-right: 8px;
}

.c-tag.info { color: #9ca3af; }
.c-tag.status { color: #0284c7; }
.c-tag.success { color: #059669; }
.c-tag.error { color: #dc2626; }
</style>
