#!/usr/bin/env python3
"""
Baidu ASR transcription — cloud-based, best Chinese accuracy.

Usage:
    python3 transcribe_baidu.py <audio.wav> [--format wav] [--rate 16000]

Requires: requests (auto-installed)
Env vars: BAIDU_ASR_APP_ID, BAIDU_ASR_API_KEY, BAIDU_ASR_SECRET_KEY
"""
import argparse, json, sys, os, time, requests, base64

def get_token(api_key, secret_key):
    """Get Baidu OAuth access token."""
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key
    }
    r = requests.post(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def transcribe(audio_path, token, audio_format="wav", sample_rate=16000):
    """Send audio to Baidu ASR and return full text."""
    # Read audio
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    
    # Baidu ASR limit: 60s per request, 10MB max
    # For longer files, split into chunks
    import wave
    with wave.open(audio_path, "rb") as wf:
        total_frames = wf.getnframes()
        frame_rate = wf.getframerate()
        duration = total_frames / frame_rate
    
    if duration <= 55:
        # Single request
        return _transcribe_chunk(audio_data, token, audio_format, sample_rate)
    
    # Multi-chunk for long audio
    results = []
    chunk_duration = 50  # seconds per chunk
    chunk_frames = int(chunk_duration * frame_rate)
    
    with wave.open(audio_path, "rb") as wf:
        for offset in range(0, total_frames, chunk_frames):
            wf.setpos(offset)
            chunk_data = wf.readframes(min(chunk_frames, total_frames - offset))
            
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                with wave.open(tmp.name, "wb") as wout:
                    wout.setnchannels(wf.getnchannels())
                    wout.setsampwidth(wf.getsampwidth())
                    wout.setframerate(frame_rate)
                    wout.writeframes(chunk_data)
                
                with open(tmp.name, "rb") as f2:
                    chunk_audio = f2.read()
                os.unlink(tmp.name)
            
            text = _transcribe_chunk(chunk_audio, token, audio_format, sample_rate)
            if text:
                results.append(text)
    
    return " ".join(results)

def _transcribe_chunk(audio_data, token, audio_format, sample_rate):
    """Transcribe a single audio chunk."""
    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
    length = len(audio_data)
    
    url = "https://vop.baidu.com/server_api"
    payload = {
        "format": audio_format,
        "rate": sample_rate,
        "channel": 1,
        "cuid": os.uname().nodename,
        "token": token,
        "speech": audio_b64,
        "len": length,
    }
    
    r = requests.post(url, json=payload, timeout=60)
    result = r.json()
    
    if result.get("err_no") != 0:
        err_msg = result.get("err_msg", "unknown")
        print(f"Baidu ASR error: {err_msg}", file=sys.stderr)
        return ""
    
    return " ".join(result.get("result", []))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="Audio file path (WAV, 16kHz mono)")
    parser.add_argument("--format", default="wav")
    parser.add_argument("--rate", type=int, default=16000)
    args = parser.parse_args()
    
    app_id = os.environ.get("BAIDU_ASR_APP_ID")
    api_key = os.environ.get("BAIDU_ASR_API_KEY")
    secret_key = os.environ.get("BAIDU_ASR_SECRET_KEY")
    
    if not all([api_key, secret_key]):
        print(json.dumps({"error": "Missing BAIDU_ASR_* env vars"}), file=sys.stderr)
        sys.exit(1)
    
    t0 = time.time()
    token = get_token(api_key, secret_key)
    text = transcribe(args.audio, token, args.format, args.rate)
    elapsed = time.time() - t0
    
    result = {
        "source": "baidu-asr",
        "duration_seconds": round(elapsed, 1),
        "full_text": text,
        "char_count": len(text)
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    import wave
    main()
