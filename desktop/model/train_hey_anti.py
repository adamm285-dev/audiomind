"""
Synthetic dataset generator and trainer for "Hey Anti" custom wake-word model.
Conforms to openWakeWord ONNX input specifications: [1, 16, 96] float32 embeddings -> [1, 1] float32 logit/prob.
"""
import os
import sys
import asyncio
import subprocess
import shutil
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm
import edge_tts
from openwakeword.utils import AudioFeatures

VOICES = [
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
    "en-US-DavisNeural",
    "en-US-AmberNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-CA-ClaraNeural",
]

RATES = ["-15%", "-5%", "+0%", "+10%", "+20%"]
PITCHES = ["-10Hz", "+0Hz", "+10Hz"]

POSITIVE_PHRASES = [
    "Hey Anti",
    "hey anti",
    "Hey Ante",
    "hey ante",
    "Hey Auntie",
    "hey auntie",
    "Hey Anty",
    "hey anty",
    "Hey Anti!",
    "Hey Ante!",
]

NEGATIVE_PHRASES = [
    # Phonetic near-misses (non-targets)
    "Hey Annie",
    "Hey Andy",
    "Hey Anthony",
    "Hey Antonio",
    "Hey Samantha",
    "Hey Siri",
    "Hey Google",
    "Hey Alexa",
    "Hey Jarvis",
    "Antigravity",
    "antenna",
    # Everyday developer speech
    "Can you run the tests?",
    "Check the database connection.",
    "Open the terminal please.",
    "What is the status of the build?",
    "Let's look at the pull request.",
    "I need to debug this function.",
    "Good morning everyone.",
    "Hello there, how are you?",
    "Where is the configuration file?",
    "Could you explain this error message?",
    "Please commit the recent changes.",
    "We need to deploy this to production.",
    "Start the development server.",
    "The application crashed again.",
    "Check the system logs for details.",
]

FFMPEG_PATH = shutil.which("ffmpeg") or os.environ.get("FFMPEG_PATH") or (r"C:\ffmpeg\bin\ffmpeg.exe" if os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe") else "ffmpeg")

async def synthesize_to_pcm(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> np.ndarray:
    """Synthesize speech using edge-tts and pipe through ffmpeg to 16kHz s16le PCM."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    mp3_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data += chunk["data"]

    if not mp3_data:
        return np.array([], dtype=np.int16)

    proc = subprocess.Popen(
        [FFMPEG_PATH, "-i", "pipe:0", "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    raw_pcm, _ = proc.communicate(input=mp3_data)
    return np.frombuffer(raw_pcm, dtype=np.int16)

def extract_features_from_pcm(pcm: np.ndarray, af: AudioFeatures) -> list[np.ndarray]:
    """Feed audio in 1280-sample chunks and extract 16x96 feature frames."""
    feats = []
    # Pad if shorter than 1280
    if len(pcm) < 1280:
        pcm = np.pad(pcm, (0, 1280 - len(pcm)))
    
    # Process in chunks
    chunk_size = 1280
    for i in range(0, len(pcm), chunk_size):
        chunk = pcm[i:i+chunk_size]
        if len(chunk) < chunk_size:
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
        af(chunk)
        feat = af.get_features(16)
        if feat.shape == (1, 16, 96):
            feats.append(feat[0])
    return feats

class WakeWordNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(16 * 96, 64),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x)

class WakeWordNetExport(nn.Module):
    def __init__(self, base_model):
        super().__init__()
        self.base_model = base_model
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        return self.sigmoid(self.base_model(x))

async def generate_dataset():
    af = AudioFeatures()
    X_pos = []
    X_neg = []

    print("[*] Generating synthetic positive training data for 'Hey Anti'...")
    pos_tasks = []
    for voice in VOICES:
        for rate in ["-10%", "+0%", "+10%"]:
            for pitch in ["-5Hz", "+0Hz", "+5Hz"]:
                for phrase in POSITIVE_PHRASES:
                    pos_tasks.append((phrase, voice, rate, pitch))
    
    # Select a diverse subset of ~120 positive samples
    np.random.seed(42)
    selected_pos = [pos_tasks[i] for i in np.random.choice(len(pos_tasks), min(120, len(pos_tasks)), replace=False)]

    for phrase, voice, rate, pitch in tqdm(selected_pos, desc="Positives"):
        try:
            pcm = await synthesize_to_pcm(phrase, voice, rate, pitch)
            # Add slight noise augmentation
            noise = np.random.randint(-30, 30, size=len(pcm), dtype=np.int16)
            pcm_aug = np.clip(pcm.astype(np.int32) + noise, -32768, 32767).astype(np.int16)
            
            feats = extract_features_from_pcm(pcm_aug, af)
            if feats:
                # The wake word trigger occurs at the peak/end of the phrase
                # The last 2-3 feature frames are positive
                for f in feats[-2:]:
                    X_pos.append(f)
                # Early frames before wake word completed can serve as negative
                if len(feats) > 3:
                    X_neg.append(feats[0])
        except Exception as e:
            continue

    print(f"[*] Generated {len(X_pos)} positive feature frames.")

    print("[*] Generating synthetic negative / adversarial training data...")
    neg_tasks = []
    for voice in VOICES[:6]:
        for phrase in NEGATIVE_PHRASES:
            neg_tasks.append((phrase, voice, "+0%", "+0Hz"))

    for phrase, voice, rate, pitch in tqdm(neg_tasks, desc="Negatives"):
        try:
            pcm = await synthesize_to_pcm(phrase, voice, rate, pitch)
            feats = extract_features_from_pcm(pcm, af)
            for f in feats:
                X_neg.append(f)
        except Exception as e:
            continue

    # Add ambient noise / silence negative frames
    print("[*] Generating synthetic ambient noise negatives...")
    for _ in range(50):
        noise_pcm = np.random.randint(-150, 150, size=16000, dtype=np.int16)
        feats = extract_features_from_pcm(noise_pcm, af)
        for f in feats:
            X_neg.append(f)

    print(f"[*] Generated {len(X_neg)} negative feature frames.")
    return np.array(X_pos, dtype=np.float32), np.array(X_neg, dtype=np.float32)

def train_and_export(X_pos, X_neg, output_onnx_path: str):
    X = np.concatenate([X_pos, X_neg], axis=0)
    y = np.concatenate([np.ones((len(X_pos), 1), dtype=np.float32), np.zeros((len(X_neg), 1), dtype=np.float32)], axis=0)

    # Shuffle
    indices = np.arange(len(X))
    np.random.shuffle(indices)
    X = torch.tensor(X[indices])
    y = torch.tensor(y[indices])

    split = int(0.85 * len(X))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    model = WakeWordNet()
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([12.0]))
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)

    print(f"[*] Training WakeWordNet on {len(X_train)} samples (Val: {len(X_val)})...")
    batch_size = 32

    for epoch in range(60):
        model.train()
        permutation = torch.randperm(X_train.size()[0])
        total_loss = 0.0
        for i in range(0, X_train.size()[0], batch_size):
            indices = permutation[i:i + batch_size]
            batch_x, batch_y = X_train[indices], y_train[indices]

            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(batch_x)

        train_loss = total_loss / len(X_train)

        # Validation
        model.eval()
        with torch.no_grad():
            val_logits = model(X_val)
            val_loss = criterion(val_logits, y_val).item()
            preds = (torch.sigmoid(val_logits) >= 0.5).float()
            val_acc = (preds == y_val).float().mean().item()

        if (epoch + 1) % 10 == 0:
            print(f"Epoch {epoch+1:02d}/60 - Train Loss: {train_loss:.4f} - Val Loss: {val_loss:.4f} - Val Acc: {val_acc*100:.1f}%")

    print(f"[*] Final Val Acc: {val_acc*100:.1f}%. Exporting ONNX model to {output_onnx_path}...")
    export_model = WakeWordNetExport(model)
    export_model.eval()
    dummy_input = torch.randn(1, 16, 96, dtype=torch.float32)

    os.makedirs(os.path.dirname(output_onnx_path), exist_ok=True)
    torch.onnx.export(
        export_model,
        dummy_input,
        output_onnx_path,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        opset_version=18,
    )
    print(f"[+] Successfully exported {output_onnx_path} (Size: {os.path.getsize(output_onnx_path)} bytes)")

async def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "models")
    os.makedirs(out_dir, exist_ok=True)
    onnx_path = os.path.abspath(os.path.join(out_dir, "hey_anti.onnx"))

    cache_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    pos_cache = os.path.join(cache_dir, "X_pos.npy")
    neg_cache = os.path.join(cache_dir, "X_neg.npy")

    if os.path.exists(pos_cache) and os.path.exists(neg_cache):
        print(f"[*] Loading cached dataset from {cache_dir}...")
        X_pos = np.load(pos_cache)
        X_neg = np.load(neg_cache)
    else:
        X_pos, X_neg = await generate_dataset()
        np.save(pos_cache, X_pos)
        np.save(neg_cache, X_neg)

    train_and_export(X_pos, X_neg, onnx_path)

if __name__ == "__main__":
    asyncio.run(main())
