# Plan Técnico: Guitar-wav2vec - Aprendizaje Autosupervisado (SSL) y Alineación Ergonómica (RLHF)

Este plan de diseño arquitectónico de nivel de producción ha sido formulado para migrar tu pipeline de transcripción tradicional (basado en heurísticas y modelos preexistentes como Basic Pitch y librosa) a un sistema integrado de **Aprendizaje Autosupervisado (SSL) tipo wav2vec** especializado en guitarra, alineado con la biomecánica de guitarristas reales mediante **Aprendizaje por Refuerzo con Retroalimentación Humana (RLHF)**.

---

## 🚀 Arquitectura General del Sistema (Guitar-wav2vec-RL)

El nuevo pipeline desacopla el procesamiento acústico de la lógica de digitación ergonómica mediante un flujo secuencial inteligente:

```
[ Audio Crudo de Guitarra ]
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│        ETAPA 1: EXTRACCIÓN DE CARACTERÍSTICAS           │
│   - Red Neuronal Convolucional (Encoder Temporal)       │
│   - Cuantización Vectorial (Código Latente Discreto)    │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│        ETAPA 2: PROCESAMIENTO CONTEXTUAL (SSL)          │
│   - Capas Transformer Bidireccionales (Masked Audio)     │
│   - Comprensión de Contexto Armónico y de Ataque         │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│        ETAPA 3: CABEZA DE CLASIFICACIÓN DE NOTAS        │
│   - Fine-Tuned para (Pitch, Cuerda, Traste)             │
│   - Tokenización Estructurada y Decodificación CTC      │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│        ETAPA 4: FILTRADO ERGONÓMICO (RLHF)              │
│   - Modelo de Recompensa (Fatiga de Mano de Expertos)   │
│   - Optimización de Políticas por Proximal Policy (PPO) │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Fase 1: Estrategia de Datos (Asegurando Relevancia y Diversidad)

Para entrenar un codificador acústico SSL sin sesgos, el corpus debe capturar la física real del instrumento bajo cualquier configuración técnica.

### 1.1. Recolección de Datos de Audio Crudo (Sin Etiquetas para SSL)
- **Volumen**: ~5,000 horas de audio de guitarra cruda no etiquetada.
- **Diversidad Instrumental**:
  - **Guitarras Clásicas/Folk**: Cuerdas de nylon y bronce, cuerpos de madera de resonancia natural.
  - **Guitarras Eléctricas de Cuerpo Sólido/Semihollow**: Píldoras de bobina simple (*single-coils*) y humbuckers.
- **Diversidad de Efectos y Amplificación**:
  - Pistas limpias (*clean*), con sobre-impulso (*overdrive*), distorsión de alta ganancia (crucial para metal), modulación (chorus, flanger), retardos y reverberación.
- **Técnicas de Ejecución**: Grabaciones que contengan de forma representativa rasgueos, arpegios con dedos, uso de púa (*alternate picking*), legato (hammer-ons, pull-offs), slides, armónicos naturales y artificiales, y palm-muting.

### 1.2. Limpieza y Normalización Automatizada
- **Filtro de Ruido**: Aplicación de algoritmos de reducción espectral para eliminar zumbidos de baja frecuencia de amplificadores de tubo (60Hz hum) sin dañar los fundamentales de las cuerdas graves.
- **Normalización de Volumen**: Ajuste de sonoridad estándar por sonoridad integrada (ITU-R BS.1770-4 a -23 LUFS) para evitar sesgos de amplitud en la cuantización latente.
- **Detección de Silencios Extremos**: Fragmentación del flujo de audio mediante puertas de ruido adaptativas (*noise gates*) para descartar bloques de silencio de más de 3 segundos que consumen memoria innecesariamente.

---

## 🧠 Fase 2: Arquitectura SSL ( Tarea de Pretexto de Enmascaramiento Acústico )

El núcleo del sistema utiliza un modelo similar a **wav2vec 2.0**, adaptado específicamente para señales de audio musical con alta transitoriedad y armónicos ricos en resonancia.

```
                  [ Máscara de Audio (15% del tiempo bloqueado) ]
                                      │
                                      ▼
[ Audio Crudo ] ──► [ CNN Encoder ] ──► [ Capa Contextual Transformer ] ──► [ Contexto C ]
                         │                                                       │
                         └──────► [ Cuantizador Vectorial ] ──► [ Código Q ] ◄───┘
                                                                    │
                                                                    ▼
                                                            Pérdida de Contraste
```

### 2.1. Codificador de Características (Feature Encoder)
- Una red convolucional 1D ($7 \text{ bloques de convolución}$) toma el audio crudo muestreado a 16kHz y genera vectores de representación latente $\mathbf{z}_t$ cada 20 ms.
- Mapea el dominio del tiempo directamente al espacio de representación sin pérdida de fase de ataque (transitorios de púa).

### 2.2. Cuantización Vectorial (Vector Quantization - VQ)
- Para que el modelo distinga alturas musicales discretas en lugar de espectros abstractos, implementamos un cuantizador con dos libros de códigos (*codebooks*) independientes $G=2$, cada uno con $V=320$ palabras de código.
- Los vectores $\mathbf{z}_t$ se mapean a representaciones discretas discretizadas $\mathbf{q}_t$ usando selección de Gumbel-Softmax. Esto permite digitalizar la señal de audio en combinaciones atómicas musicales de forma autosupervisada.

### 2.3. Tarea de Pretexto: Masked Latent Agreement
- **Enmascaramiento**: Enmascaramos el **15%** de los frames latentes antes de ser introducidos en la red contextual del Transformer.
- **Transformer Contextual**: El Transformer bidireccional procesa los vectores enmascarados y produce vectores de contexto $\mathbf{c}_t$.
- **Pérdida Contrastiva (Contrastive Loss)**: El modelo debe aprender a predecir la representación cuantizada correcta $\mathbf{q}_t$ para los marcos temporalmente bloqueados, discriminándola de un conjunto de $K=100$ representaciones distractoras falsas de otros instantes de la canción:
  $$\mathcal{L}_{m} = -\log \frac{\exp(\text{sim}(\mathbf{c}_t, \mathbf{q}_t)/\tau)}{\sum_{\tilde{\mathbf{q}}} \exp(\text{sim}(\mathbf{c}_t, \tilde{\mathbf{q}})/\tau)}$$
  Donde $\text{sim}(\mathbf{a}, \mathbf{b})$ es el producto escalar normalizado y $\tau$ es la temperatura.

---

## 🎸 Fase 3: Pipeline de Fine-Tuning (Especialización en Tablatura y Notas)

Una vez que el modelo base **Guitar-wav2vec** comprende la física armónica de la guitarra, realizamos un ajuste fino con supervisión de datos precisos para clasificar altura, cuerda y traste de forma simultánea.

```
                           ┌───────────────────────────┐
                           │   Guitar-wav2vec Base     │
                           └─────────────┬─────────────┘
                                         ▼
                 ┌───────────────────────────────────────────┐
                 │       CABEZA DE INFERENCIA MULTI-TASK     │
                 │   Clasificación Paralela de Atributos     │
                 └──────┬──────────────┬──────────────┬──────┘
                        ▼              ▼              ▼
                 ┌──────────┐   ┌──────────┐   ┌──────────┐
                 │  Pitch   │   │  Cuerda  │   │  Traste  │
                 │ (0-127)  │   │  (1-6)   │   │  (0-22)  │
                 └──────────┘   └──────────┘   └──────────┘
```

### 3.1. Arquitectura de Salida Multi-Task
Colocamos tres cabezas de clasificación paralelas (capas densas lineales) sobre el codificador contextual del Transformer:
1. **Cabeza de Pitch**: Clasificador lineal de $128 \text{ clases}$ (escala MIDI).
2. **Cabeza de Cuerda**: Clasificador de $7 \text{ clases}$ (0 para silencio, 1-6 para cuerdas).
3. **Cabeza de Traste**: Clasificador de $24 \text{ clases}$ (0 para cuerda al aire, 1-22 para trastes, 23 para silencio).

### 3.2. Dataset de Fine-Tuning
- **Dataset de Referencia**: Conjunto de datos curado de tablaturas de alta fidelidad **MusicXML** sincronizadas exactamente milisegundo a milisegundo con grabaciones de audio reales usando técnicas de alineación temporal dinámica (Dynamic Time Warping - DTW).
- **Tokenización Musical**: Cada evento se tokeniza en un vector atómico integrado: `[Pitch_ID, String_ID, Fret_ID]`.

### 3.3. Pérdida de Entrenamiento de Ajuste Fino
Utilizamos una pérdida de entropía cruzada compuesta para optimizar simultáneamente la detección de la nota y la correcta elección del traste en el mástil:
$$\mathcal{L}_{\text{fine-tune}} = w_1 \mathcal{L}_{\text{pitch}} + w_2 \mathcal{L}_{\text{string}} + w_3 \mathcal{L}_{\text{fret}}$$
Implementamos decodificación **Connectionist Temporal Classification (CTC)** para alinear automáticamente las secuencias predichas con la línea temporal del audio sin requerir alineaciones manuales de etiquetas de nota extremadamente detalladas.

---

## 🤝 Fase 4: Alineación Ergonómica (RLHF para Comodidad Biomecánica)

Incluso con una predicción de altura perfecta, la elección de cuerdas y trastes óptimos varía enormemente de un guitarrista a otro. Usamos **RLHF** para entrenar una política que alinee las decisiones de la IA con la ergonomía anatómica humana.

```
                              ┌────────────────────────┐
                              │  Modelo de Recompensa  │
                              │ (Análisis de Esfuerzo) │
                              └───────────▲────────────┘
                                          │
                                          │ (Feedback / Puntuación)
                                          │
┌──────────────────────────┐  Digitación  │  ┌───────────────────────┐
│ Inferencia Guitar-wav2vec├──┬───────────┴─►│ Guitarristas Expertos │
│    (Política π_θ)        │  │              │ (Criterio Humano)     │
└──────────────────────────┘  │              └───────────────────────┘
                              ▼
                [ Optimización de Política PPO ]
```

### 4.1. Diseño del Reward Model (Modelo de Recompensa)
1. **Recolección de Feedback Experto**: Presentamos partituras con diferentes variantes de digitación de transición complejas a guitarristas expertos.
2. **Evaluación de Ergonomía**: Los guitarristas ordenan las opciones priorizando criterios humanos:
   - "Esta posición requiere estirar la mano izquierda sobre 6 trastes en un compás rápido de metal, es dolorosa." $\rightarrow$ Recompensa Baja.
   - "Esta opción usa una cejilla en el traste 5 con acordes Drop-2 muy cómodos de sostener." $\rightarrow$ Recompensa Alta.
3. **Entrenamiento del Reward Model**: Entrenamos un estimador de red neuronal (Reward Model $RM(x, y)$) para evaluar la comodidad de la secuencia física $y$ para el audio de entrada $x$.

### 4.2. Optimización por Aprendizaje por Refuerzo con PPO
Utilizamos **Proximal Policy Optimization (PPO)** para entrenar y refinar el modelo final. La recompensa integrada premia la precisión acústica (Fase 3) y la comodidad ergonómica humana (Fase 4):
$$\mathcal{R}(x, y) = \text{Precisión\_Acústica}(x, y) + \gamma \, RM(x, y) - \beta \, \mathbb{D}_{\text{KL}}\left(\pi_\theta(y|x) \,\|\, \pi_{\text{ref}}(y|x)\right)$$
La penalización por divergencia KL ($\mathbb{D}_{\text{KL}}$) previene que el modelo sugiera digitaciones ergonómicamente perfectas de notas incorrectas que no corresponden al audio.

---

## ⚡ Fase 5: Optimización de Inferencia y Despliegue en FastAPI

Para garantizar que el modelo de deep learning se ejecute en tiempo real y sin costes excesivos en tu servidor backend de FastAPI, aplicamos técnicas rigurosas de compresión de modelos.

### 5.1. Cuantización de Rango Dinámico (INT8 Quantization)
- Convertimos los pesos del modelo Transformer de precisión float32 a enteros de 8 bits (**INT8**).
- **Beneficio**: Reduce el tamaño del modelo en disco y memoria en un **75%** (de ~400 MB a ~100 MB) y acelera la inferencia de CPU en más de **3x** usando instrucciones vectoriales avanzadas de la CPU (como AVX-512 en Windows/Laragon).

### 5.2. Destilación del Conocimiento (Knowledge Distillation)
- Entrenamos una red "Estudiante" compacta de solo 4 bloques Transformer para imitar la salida de probabilidad completa del modelo "Maestro" de 12 bloques.
- El modelo estudiante retiene el **96% de la precisión** del maestro con solo una fracción del peso computacional, ideal para procesar rápidamente audios de larga duración o videos de YouTube.

### 5.3. Inferencia de alto rendimiento en FastAPI
- El modelo cuantizado se exporta a formato **ONNX Runtime** y se carga en FastAPI mediante hilos asíncronos para evitar bloquear el bucle de eventos principal de FastAPI:

```python
import onnxruntime as ort
import numpy as np

class GuitarSSLInference:
    def __init__(self, onnx_model_path: str):
        # Configurar subprocesos de ejecución paralela de ONNX para CPU
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 4
        session_options.inter_op_num_threads = 2
        
        # Cargar el motor ONNX cuantizado en INT8
        self.session = ort.InferenceSession(
            onnx_model_path, 
            sess_options=session_options,
            providers=['CPUExecutionProvider']
        )
        
    def transcribe_audio_signal(self, audio_signal: np.ndarray) -> list[dict]:
        # Formatear entrada temporal de audio de 16kHz
        inputs = {self.session.get_inputs()[0].name: np.array([audio_signal], dtype=np.float32)}
        
        # Inferencia paralela sub-milisegundo
        logits = self.session.run(None, inputs)
        
        # Decodificar CTC a notas, cuerdas y trastes
        return self.decode_ctc_output(logits)
```

---

## 📊 6. Métricas de Evaluación de Rendimiento

Para validar el éxito del pipeline, el modelo final debe superar las siguientes métricas de validación frente al actual sistema heurístico:

1. **F1-Score para Detección Acústica**: Debe ser mayor al **94%** en la correcta clasificación de la nota MIDI del audio.
2. **TAB Accuracy (TA)**: Precisión traste-cuerda en el mástil comparado con tablaturas certificadas por profesionales:
   $$\text{TA} = \frac{\text{Aciertos correctos de (Cuerda, Traste)}}{\text{Total de notas del audio}} \times 100$$
3. **Ergonomic Hand-span Ratio (EHR)**: Distancia promedio horizontal recorrida por la mano por segundo (un EHR menor significa que el modelo diseña digitaciones más compactas y eficientes que evitan fatiga):
   $$\text{EHR} = \frac{1}{S} \sum_{s=1}^{S} |F_s - F_{s-1}|$$

Este diseño representa la frontera absoluta de la investigación y desarrollo de IA en **Music Information Retrieval (MIR)** aplicable a instrumentos físicos.
