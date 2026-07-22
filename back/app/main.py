import os
import sys
import shutil
import tempfile
import base64

# Intento de agregar rutas comunes de FFmpeg a PATH en Windows
if sys.platform == "win32":
    extra_paths = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\Program Files (x86)\ffmpeg\bin",
        r"C:\laragon\bin\ffmpeg\bin", # Ruta común de Laragon ffmpeg
        r"C:\tools\ffmpeg\bin",       # Ruta común de Chocolatey
    ]
    path_env = os.environ.get("PATH", "")
    for p in extra_paths:
        if os.path.exists(p) and p not in path_env:
            path_env = p + os.path.pathsep + path_env
    os.environ["PATH"] = path_env

# Escribir advertencia si FFmpeg no se detecta en Laragon/Uvicorn
if shutil.which("ffmpeg") is None:
    try:
        log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcription.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n[WARNING] ⚠️ FFmpeg no se ha detectado en el PATH del sistema para Laragon/FastAPI. "
                    "Si lo acabas de instalar o agregar, REINICIA por completo Laragon, Uvicorn y tu editor (VS Code) "
                    "para que el sistema reconozca la nueva variable de entorno.\n")
    except:
        pass

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

from app.transcription.pipeline import run_transcription_pipeline
from app.transcription.gp_generator import generate_gp5
from app.transcription.pitch import BASIC_PITCH_AVAILABLE

app = FastAPI(
    title="Guitar Transcription API",
    description="API para procesar audio de guitarra y generar notas con cuerdas, trastes y partituras en MusicXML.",
    version="1.0.0"
)

# Permitir CORS para desarrollo e integración fácil con el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """
    Ruta raíz para verificar el estado de la API y las capacidades disponibles.
    """
    return {
        "status": "online",
        "message": "Servicio de Transcripción de Guitarra activo.",
        "capabilities": {
            "monophonic_detection": "Available (librosa pYIN)",
            "polyphonic_detection": "Available" if BASIC_PITCH_AVAILABLE else "Unavailable (Requires TensorFlow/Basic Pitch)",
            "musicxml_generation": "Available (music21)"
        },
        "endpoints": {
            "transcribe": "/api/transcribe [POST]"
        }
    }


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    mode: str = Form(
        default="auto",
        description="Modo de detección: 'auto', 'monophonic' o 'polyphonic'."
    ),
    bpm: float = Form(
        default=120.0,
        description="BPM sugerido para estructurar la métrica de la partitura."
    ),
    title: str = Form(
        default="Transcripción Automática",
        description="Título de la obra musical."
    ),
    output_format: str = Form(
        default="both",
        description="Formato de respuesta: 'xml' (retorna archivo MusicXML), 'json' (retorna notas estructuradas) o 'both' (retorna ambos en un JSON)."
    ),
    power_chords: bool = Form(
        default=False,
        description="Si es True, expande automáticamente notas individuales para formar notas quintas (power chords) físicas en la tablatura."
    ),
    demucs_separation: bool = Form(
        default=False,
        description="Si es True, ejecuta Demucs para aislar las pistas de guitarra antes del procesamiento."
    ),
    fingering_algorithm: str = Form(
        default="heuristic",
        description="Algoritmo de digitación: 'heuristic' o 'guitar_bert'."
    ),
    fingering_style: str = Form(
        default="classic",
        description="Estilo de digitaciones para GuitarBERT: 'classic', 'metal' o 'jazz'."
    ),
    guitar_tuning: str = Form(
        default="auto",
        description="Afinación de la guitarra: 'auto', 'standard', 'drop_d', 'drop_c', etc."
    )
):
    """
    Recibe un archivo de audio de guitarra (WAV o MP3) y ejecuta el pipeline de transcripción.
    Retorna la tablatura asignada a cuerdas/trastes y opcionalmente el archivo MusicXML para renderizar partituras.
    """
    # Validar extensión del archivo
    filename = file.filename or "audio"
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in [".wav", ".mp3", ".ogg", ".m4a", ".flac"]:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no soportado: {file_ext}. Use WAV, MP3 o formatos de audio comunes."
        )

    # Crear un archivo temporal para guardar el audio subido
    suffix = file_ext if file_ext else ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        try:
            shutil.copyfileobj(file.file, temp_audio)
            temp_audio_path = temp_audio.name
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar el archivo de audio temporal: {str(e)}"
            )

    try:
        # Ejecutar el pipeline de transcripción
        notes, xml_content = run_transcription_pipeline(
            file_path=temp_audio_path,
            mode=mode,
            bpm=bpm,
            title=title,
            power_chords=power_chords,
            demucs_separation=demucs_separation,
            fingering_algorithm=fingering_algorithm,
            fingering_style=fingering_style,
            guitar_tuning=guitar_tuning
        )
        
        # Eliminar archivo de audio temporal de inmediato para liberar recursos
        try:
            os.remove(temp_audio_path)
        except OSError:
            pass

        # Generar archivo binario GuitarPro (.gp5)
        gp5_bytes = generate_gp5(notes, title=title, bpm=bpm)

        # Estructurar la respuesta según output_format
        if output_format == "xml":
            return Response(
                content=xml_content,
                media_type="application/xml",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{title.replace(' ', '_')}.xml\""
                }
            )
        elif output_format == "gp":
            return Response(
                content=gp5_bytes,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{title.replace(' ', '_')}.gp5\""
                }
            )
        elif output_format == "json":
            return JSONResponse(
                content={
                    "title": title,
                    "bpm": bpm,
                    "notes_count": len(notes),
                    "notes": notes
                }
            )
        else: # "both"
            gp5_base64 = base64.b64encode(gp5_bytes).decode('utf-8')
            return JSONResponse(
                content={
                    "title": title,
                    "bpm": bpm,
                    "notes_count": len(notes),
                    "notes": notes,
                    "musicxml": xml_content,
                    "gp5": gp5_base64
                }
            )

    except Exception as e:
        # Asegurar la limpieza en caso de error
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except OSError:
                pass
        
        err_msg = str(e)
        # Ofrecer sugerencia amistosa si falla la decodificación de audio por dependencias del sistema
        if "librosa" in err_msg or "NoBackendError" in err_msg or "Format not recognised" in err_msg:
            raise HTTPException(
                status_code=400,
                detail="Error al procesar el audio. El formato MP3 u otros formatos comprimidos requieren códecs "
                       "en el sistema (como ffmpeg) o una biblioteca compatible. Por favor, sube un archivo WAV "
                       "(audio sin comprimir), el cual es totalmente compatible de forma nativa sin códecs externos."
            )
            
        raise HTTPException(
            status_code=500,
            detail=f"Error durante el procesamiento y transcripción de la pista: {err_msg}"
        )


@app.post("/api/transcribe_youtube")
async def transcribe_youtube(
    youtube_url: str = Form(...),
    mode: str = Form(
        default="auto",
        description="Modo de detección: 'auto', 'monophonic' o 'polyphonic'."
    ),
    bpm: float = Form(
        default=120.0,
        description="BPM sugerido para estructurar la métrica de la partitura."
    ),
    title: str = Form(
        default="",
        description="Título de la obra musical (vacío para auto-detectar de YouTube)."
    ),
    output_format: str = Form(
        default="both",
        description="Formato de respuesta: 'xml' (retorna archivo MusicXML), 'json' (retorna notas estructuradas) o 'both' (retorna ambos en un JSON)."
    ),
    power_chords: bool = Form(
        default=False,
        description="Si es True, expande automáticamente notas individuales para formar notas quintas (power chords) físicas en la tablatura."
    ),
    demucs_separation: bool = Form(
        default=False,
        description="Si es True, extrae la pista de guitarra del audio de YouTube usando Demucs antes de transcribir."
    ),
    fingering_algorithm: str = Form(
        default="heuristic",
        description="Algoritmo de digitación: 'heuristic' o 'guitar_bert'."
    ),
    fingering_style: str = Form(
        default="classic",
        description="Estilo de digitaciones para GuitarBERT: 'classic', 'metal' o 'jazz'."
    ),
    guitar_tuning: str = Form(
        default="auto",
        description="Afinación de la guitarra: 'auto', 'standard', 'drop_d', 'drop_c', etc."
    )
):
    """
    Descarga el audio de un video de YouTube y ejecuta el pipeline de transcripción.
    """
    import yt_dlp
    
    # 1. Configurar yt-dlp para descargar audio en formato wav o similar
    temp_dir = tempfile.gettempdir()
    outtmpl = os.path.join(temp_dir, '%(id)s.%(ext)s')
    
    ydl_opts_best = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    downloaded_path = None
    video_title = str(title) if title else "Transcripción de YouTube"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_best) as ydl:
            extracted_info = ydl.extract_info(youtube_url, download=True)
            if extracted_info is not None:
                if not title:
                    video_title = str(extracted_info.get('title', 'Transcripción de YouTube'))
                
                # Obtener el archivo generado
                filepath = ydl.prepare_filename(extracted_info)
                base, _ = os.path.splitext(filepath)
                wav_filepath = base + '.wav'
                
                if os.path.exists(wav_filepath):
                    downloaded_path = wav_filepath
                elif os.path.exists(filepath):
                    downloaded_path = filepath
                
    except Exception as e:
        # Fallback sin conversión de audio (en caso de que no tenga ffmpeg en el path)
        try:
            ydl_opts_fallback = {
                'format': 'bestaudio/best',
                'outtmpl': outtmpl,
                'nocheckcertificate': True,
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                extracted_info = ydl.extract_info(youtube_url, download=True)
                if extracted_info is not None:
                    if not title:
                        video_title = str(extracted_info.get('title', 'Transcripción de YouTube'))
                    downloaded_path = ydl.prepare_filename(extracted_info)
        except Exception as err_fallback:
            raise HTTPException(
                status_code=500,
                detail=f"Error al descargar audio de YouTube: {str(err_fallback)}"
            )

    if not downloaded_path or not os.path.exists(downloaded_path):
        raise HTTPException(
            status_code=500,
            detail="No se pudo encontrar el audio descargado de YouTube."
        )

    try:
        # Ejecutar el pipeline de transcripción
        notes, xml_content = run_transcription_pipeline(
            file_path=downloaded_path,
            mode=mode,
            bpm=bpm,
            title=video_title,
            power_chords=power_chords,
            demucs_separation=demucs_separation,
            fingering_algorithm=fingering_algorithm,
            fingering_style=fingering_style,
            guitar_tuning=guitar_tuning
        )
        
        # Eliminar archivo descargado
        try:
            os.remove(downloaded_path)
        except OSError:
            pass

        # Generar archivo binario GuitarPro (.gp5)
        gp5_bytes = generate_gp5(notes, title=video_title, bpm=bpm)

        # Estructurar la respuesta
        if output_format == "xml":
            return Response(
                content=xml_content,
                media_type="application/xml",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{video_title.replace(' ', '_')}.xml\""
                }
            )
        elif output_format == "json":
            return JSONResponse(
                content={
                    "title": video_title,
                    "bpm": bpm,
                    "notes_count": len(notes),
                    "notes": notes
                }
            )
        else: # "both"
            gp5_base64 = base64.b64encode(gp5_bytes).decode('utf-8')
            return JSONResponse(
                content={
                    "title": video_title,
                    "bpm": bpm,
                    "notes_count": len(notes),
                    "notes": notes,
                    "musicxml": xml_content,
                    "gp5": gp5_base64
                }
            )

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        # Escribir el error y la traza de ejecución en transcription.log
        log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcription.log")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[ERROR] Error durante el procesamiento de YouTube: {repr(e)}\n")
                f.write(f"[ERROR] Traceback: {tb_str}\n")
        except:
            pass
            
        if downloaded_path and os.path.exists(downloaded_path):
            try:
                os.remove(downloaded_path)
            except OSError:
                pass
                
        err_detail = str(e) if str(e) else repr(e)
        if "NoBackendError" in err_detail or "NoBackendError" in tb_str:
            raise HTTPException(
                status_code=400,
                detail="Error al procesar el video de YouTube: El sistema requiere 'FFmpeg' para decodificar "
                       "formatos de audio comprimidos de YouTube (como webm/m4a). Laragon no ha podido encontrar "
                       "FFmpeg en el PATH de tu Windows. Por favor, asegúrate de descargar FFmpeg, "
                       "agregarlo a las variables de entorno de tu sistema, y REINICIAR por completo Laragon y "
                       "tu IDE/consola para que surta efecto."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error durante el procesamiento del audio de YouTube: {err_detail}. Traza: {tb_str[:400]}"
        )


@app.post("/api/log")
async def write_log(payload: dict):
    """
    Recibe un mensaje de log del frontend y lo añade al archivo transcription.log.
    """
    msg = payload.get("message", "")
    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcription.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    return {"status": "ok"}
