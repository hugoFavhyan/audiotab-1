import torch
import torch.nn as nn
import torch.nn.functional as F
import math

class GuitarWav2VecConfig:
    """
    Configuración de hiperparámetros para el modelo Guitar-wav2vec.
    """
    def __init__(self):
        self.sample_rate = 16000          # 16 kHz para procesamiento wav2vec estándar
        self.encoder_embed_dim = 512      # Dimensión de embeddings latentes
        self.transformer_heads = 8         # Cabezas de Multi-Head Attention
        self.transformer_layers = 12       # Bloques encoder bidireccionales
        self.codebook_groups = 2           # Grupos de cuantización vectorial G=2
        self.codebook_vars = 320           # Vocabulario de cuantización V=320
        self.num_pitches = 128            # Escala MIDI de salidas de pitch
        self.num_strings = 7              # 0 para silencio, 1-6 para cuerdas
        self.num_frets = 24               # 0 para al aire, 1-22 para trastes, 23 para silencio


class FeatureEncoder(nn.Module):
    """
    Encoder Convolucional Temporal (Feature Extractor) para señales de audio crudo de guitarra.
    Reduce la frecuencia de muestreo de 16kHz a una representación latente cada 20 ms.
    """
    def __init__(self, embed_dim=512):
        super().__init__()
        # 7 Bloques de convolución 1D con normalización de grupo
        self.conv_layers = nn.ModuleList([
            nn.Conv1d(1, 512, kernel_size=10, stride=5, bias=False),
            nn.Conv1d(512, 512, kernel_size=3, stride=2, bias=False),
            nn.Conv1d(512, 512, kernel_size=3, stride=2, bias=False),
            nn.Conv1d(512, 512, kernel_size=3, stride=2, bias=False),
            nn.Conv1d(512, 512, kernel_size=3, stride=2, bias=False),
            nn.Conv1d(512, 512, kernel_size=2, stride=2, bias=False),
            nn.Conv1d(512, embed_dim, kernel_size=2, stride=2, bias=False)
        ])
        self.norms = nn.ModuleList([nn.GroupNorm(32, 512) for _ in range(7)])

    def forward(self, x):
        # x shape: [Batch, 1, Num_Samples]
        for conv, norm in zip(self.conv_layers, self.norms):
            x = conv(x)
            x = norm(x)
            x = F.gelu(x)
        # Output shape: [Batch, embed_dim, Seq_Len]
        return x


class VectorQuantizer(nn.Module):
    """
    Cuantizador Vectorial Gumbel-Softmax para digitalizar características acústicas de guitarra.
    """
    def __init__(self, groups=2, num_vars=320, embed_dim=512):
        super().__init__()
        self.groups = groups
        self.num_vars = num_vars
        self.var_dim = embed_dim // groups
        
        # Dos diccionarios de código (Codebooks) discretos
        self.codebooks = nn.Parameter(torch.randn(groups, num_vars, self.var_dim))

    def forward(self, z, temp=1.0):
        # z shape: [Batch, Seq_Len, embed_dim]
        b, t, d = z.shape
        z_split = z.view(b, t, self.groups, self.var_dim)
        
        # Calcular distancias para Gumbel-Softmax
        # (Aquí se simula la cuantización por palabra del libro de códigos de forma simplificada)
        quantized = []
        for g in range(self.groups):
            # Calcular softmax de distancias
            logits = torch.matmul(z_split[:, :, g], self.codebooks[g].T)
            if self.training:
                # Gumbel Softmax en entrenamiento
                probs = F.gumbel_softmax(logits, tau=temp, hard=True)
            else:
                # Selección discreta (Argmax) en validación/inferencia
                probs = F.one_hot(logits.argmax(dim=-1), num_classes=self.num_vars).float()
                
            g_quantized = torch.matmul(probs, self.codebooks[g])
            quantized.append(g_quantized)
            
        # Concatenar grupos cuantizados
        q = torch.cat(quantized, dim=-1)
        return q


class GuitarBERTEncoder(nn.Module):
    """
    Capas de Transformer Bidireccional (GuitarBERT) para capturar el contexto
    armónico de notas anteriores y posteriores simultáneamente.
    """
    def __init__(self, embed_dim=512, heads=8, layers=12):
        super().__init__()
        self.pos_embeddings = nn.Parameter(torch.randn(1, 2048, embed_dim)) # Límite máx 2048 frames (~40 seg)
        
        # Capas de Encoder Transformer de PyTorch
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim, 
            nhead=heads, 
            dim_feedforward=2048, 
            activation="gelu",
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=layers)

    def forward(self, x):
        # x shape: [Batch, Seq_Len, embed_dim]
        seq_len = x.shape[1]
        x = x + self.pos_embeddings[:, :seq_len]
        # Inferencia bidireccional de atención mutua
        return self.transformer(x)


class MultiTaskPredictionHead(nn.Module):
    """
    Cabeza de Clasificación Paralela Multi-Task para clasificar de forma
    independiente y simultánea Pitch, Cuerda de asignación y Traste.
    """
    def __init__(self, embed_dim, config):
        super().__init__()
        self.pitch_head = nn.Linear(embed_dim, config.num_pitches)
        self.string_head = nn.Linear(embed_dim, config.num_strings)
        self.fret_head = nn.Linear(embed_dim, config.num_frets)

    def forward(self, x):
        # x shape: [Batch, Seq_Len, embed_dim]
        pitch_logits = self.pitch_head(x)
        string_logits = self.string_head(x)
        fret_logits = self.fret_head(x)
        return pitch_logits, string_logits, fret_logits


class GuitarWav2Vec(nn.Module):
    """
    Clase Principal que integra toda la red neuronal Guitar-wav2vec.
    Soporta tareas de pre-entrenamiento SSL y Fine-Tuning de Tablatura.
    """
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.feature_encoder = FeatureEncoder(config.encoder_embed_dim)
        self.quantizer = VectorQuantizer(config.codebook_groups, config.codebook_vars, config.encoder_embed_dim)
        self.context_encoder = GuitarBERTEncoder(config.encoder_embed_dim, config.transformer_heads, config.transformer_layers)
        self.prediction_head = MultiTaskPredictionHead(config.encoder_embed_dim, config)

    def forward(self, raw_audio, mask=None):
        # 1. Extraer características convolucionales
        # raw_audio shape: [Batch, 1, Num_Samples]
        z = self.feature_encoder(raw_audio)
        z = z.transpose(1, 2) # [Batch, Seq_Len, embed_dim]
        
        # 2. Aplicar enmascaramiento si es tarea SSL
        if mask is not None and self.training:
            z[mask] = 0.0 # Enmascarar con ceros (o vector MASK aprendible)

        # 3. Procesar contexto armónico con Transformer
        c = self.context_encoder(z)
        
        # 4. Clasificar tareas en paralelo
        pitch, string, fret = self.prediction_head(c)
        return pitch, string, fret


# -------------------------------------------------------------
# PÉRDIDAS BIOMECÁNICAS Y ENTRENAMIENTO DE PRODUCCIÓN
# -------------------------------------------------------------

class BiomechanicalErgonomicLoss(nn.Module):
    """
    Calcula penalizaciones físicas basadas en el estiramiento y cruce de dedos
    para moldear la pérdida de la red hacia digitaciones humanas ergonómicas.
    """
    def __init__(self):
        super().__init__()

    def forward(self, predicted_strings, predicted_frets, target_f0):
        # predicted_strings: [Batch, Seq_Len, 7] (logits)
        # predicted_frets: [Batch, Seq_Len, 24] (logits)
        
        batch_size, seq_len, _ = predicted_frets.shape
        loss = torch.tensor(0.0, device=predicted_frets.device)
        
        # Decodificar clases predichas de forma diferenciable mediante softmax/reparameterización
        strings = predicted_strings.argmax(dim=-1)
        frets = predicted_frets.argmax(dim=-1)
        
        # Recorrer secuencialmente para transiciones horizontales
        for t in range(1, seq_len):
            curr_fret = frets[:, t]
            prev_fret = frets[:, t-1]
            curr_string = strings[:, t]
            prev_string = strings[:, t-1]
            
            # 1. Penalizar estiramiento incómodo (> 4 trastes de separación) si no son al aire
            mask_no_open = (curr_fret != 0) & (prev_fret != 0)
            distance = torch.abs(curr_fret - prev_fret)
            stretch_penalty = torch.clamp(distance - 4, min=0) ** 2
            loss += torch.where(mask_no_open, stretch_penalty.float(), torch.zeros_like(distance, dtype=torch.float)).sum()
            
            # 2. Penalizar saltos excesivos de cuerda
            string_jump = torch.abs(curr_string - prev_string)
            loss += torch.where(string_jump > 2, (string_jump * 1.5).float(), torch.zeros_like(string_jump, dtype=torch.float)).sum()
            
        return loss / (batch_size * seq_len)


# -------------------------------------------------------------
# SKELETON DEL PIPELINE DE PREENTRENAMIENTO Y FINE-TUNING
# -------------------------------------------------------------

def train_guitar_ssl_step(model, optimizer, raw_audio, biomechanical_loss_fn):
    """
    Ejemplo de paso de entrenamiento para pre-entrenamiento SSL y Fine-Tuning.
    """
    model.train()
    optimizer.zero_grad()
    
    # 1. Diseñar máscara aleatoria del 15% de la secuencia
    batch_size = raw_audio.shape[0]
    seq_len = 100 # Longitud de ejemplo basada en convoluciones de salida
    mask = torch.rand(batch_size, seq_len) < 0.15
    
    # 2. Ejecutar Inferencia de la Red
    pitch, string, fret = model(raw_audio, mask=mask)
    
    # 3. Calcular Pérdidas Acústicas de Clasificación (Cross Entropy de ejemplo)
    # En producción estas se compararían con etiquetas del dataset de tablaturas reales
    dummy_target_pitch = torch.randint(0, 128, (batch_size, seq_len), device=raw_audio.device)
    dummy_target_string = torch.randint(0, 7, (batch_size, seq_len), device=raw_audio.device)
    dummy_target_fret = torch.randint(0, 24, (batch_size, seq_len), device=raw_audio.device)
    
    loss_pitch = F.cross_entropy(pitch.transpose(1, 2), dummy_target_pitch)
    loss_string = F.cross_entropy(string.transpose(1, 2), dummy_target_string)
    loss_fret = F.cross_entropy(fret.transpose(1, 2), dummy_target_fret)
    
    # 4. Calcular Pérdida Biomecánica de alineación ergonómica
    loss_biomec = biomechanical_loss_fn(string, fret, dummy_target_pitch)
    
    # Pérdida total combinada
    total_loss = loss_pitch + loss_string + loss_fret + 0.5 * loss_biomec
    
    total_loss.backward()
    optimizer.step()
    
    return total_loss.item()
