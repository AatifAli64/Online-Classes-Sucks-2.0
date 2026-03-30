"""
!pip install -q fastapi uvicorn pyngrok soundfile python-multipart faster-whisper torch nest_asyncio librosa
"""

import os
import io
import time
import soundfile as sf
import numpy as np
from fastapi import FastAPI, File, UploadFile
import uvicorn
from pyngrok import ngrok
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
import nest_asyncio

model_size = "large-v3-turbo"
print(f"Loading Faster-Whisper model ({model_size}) on CUDA (float16)...")

model = WhisperModel(model_size, device="cuda", compute_type="float16")
print(f"--- AI Model Fully Loaded ---")

app = FastAPI()

@app.post("/transcribe")
async def transcribe_audio(audio_file: UploadFile = File(...)):
    start_time = time.time()
    
    content = await audio_file.read()
    data, sample_rate = sf.read(io.BytesIO(content))
    
    if len(data.shape) > 1:
        data = data.mean(axis=1).astype(np.float32)
    else:
        data = data.astype(np.float32)
        
    if sample_rate != 16000:
        data = resample_poly(data, up=16000, down=sample_rate).astype(np.float32)
        
    segments, info = model.transcribe(data, beam_size=5, language="en")
    
    text = " ".join([segment.text for segment in segments]).strip()
    
    lower_text = text.lower()
    keywords = ["list of words that sound like your name here eg: atif, aatif, aatef, atif ali, ah teef, ateef, active, autif, artif, at if"]
    name_found = any(k in lower_text for k in keywords)
    
    duration = time.time() - start_time
    print(f"[{duration:.2f}s] Processed Request -> Text: {text} | Found: {name_found}")
    
    return {"text": text, "Your name found": name_found}

# 3. START NGROK TUNNEL AND SERVER
# ==========================================================
NGROK_AUTH_TOKEN = "ngrok authtoken token here"
# ==========================================================

ngrok.set_auth_token(NGROK_AUTH_TOKEN)
public_url = ngrok.connect(8000).public_url

print("\n" + "="*80)
print(f"NGROK URL IS: {public_url}")
print("="*80 + "\n")

nest_asyncio.apply()

config = uvicorn.Config(app, host="0.0.0.0", port=8000)
server_instance = uvicorn.Server(config)
await server_instance.serve()
