#!/usr/bin/env python3
"""
Transcribe audio with faster-whisper local ASR.

Usage:
    python3 transcribe_audio.py <audio.wav> [--language zh] [--model small]

Models: tiny, small, medium, large-v3 (default: small)
CPU-only: small model ~15-25 min for 30 min audio on a typical server.
"""
import argparse, json, sys, os, time

def transcribe(audio_path: str, model_size: str = "small", language: str = "zh") -> dict:
    """Transcribe audio and return structured result (same format as fetch_transcript.py)."""
    from faster_whisper import WhisperModel
    
    device = "cpu"
    compute_type = "int8"  # optimized for CPU
    
    print(f"Loading model {model_size}...", file=sys.stderr)
    t0 = time.time()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print(f"Model loaded in {time.time()-t0:.0f}s", file=sys.stderr)
    
    t1 = time.time()
    segments_result, info = model.transcribe(audio_path, language=language, beam_size=5)
    
    detected_lang = info.language
    segments = []
    for seg in segments_result:
        segments.append({
            "text": seg.text.strip(),
            "start": round(seg.start, 2),
            "duration": round(seg.end - seg.start, 2)
        })
    
    elapsed = time.time() - t1
    print(f"Transcription done in {elapsed:.0f}s ({len(segments)} segments)", file=sys.stderr)
    
    full_text = " ".join(seg["text"] for seg in segments)
    
    def fmt(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    
    timestamped = "\n".join(f"{fmt(seg['start'])} {seg['text']}" for seg in segments)
    
    # Use same shape as fetch_transcript.py
    result = {
        "video_id": os.path.basename(audio_path).replace('.wav', ''),
        "language": detected_lang,
        "source": f"faster-whisper/{model_size}",
        "segment_count": len(segments),
        "duration": fmt(segments[-1]["start"] + segments[-1]["duration"]) if segments else "0:00",
        "full_text": full_text,
        "timestamped_text": timestamped,
    }
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio', help='Path to 16kHz mono WAV file')
    parser.add_argument('--language', default='zh', help='Language code')
    parser.add_argument('--model', default='small', help='Model size')
    args = parser.parse_args()
    
    result = transcribe(args.audio, args.model, args.language)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
