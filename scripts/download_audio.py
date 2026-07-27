#!/usr/bin/env python3
"""
Download YouTube audio as 16kHz mono WAV for ASR.

Usage:
    python3 download_audio.py <url_or_video_id> [--output OUTPUT.wav]

Requires: yt-dlp, ffmpeg
"""
import argparse, subprocess, sys, json, os

def download_audio(url: str, output_path: str) -> str:
    """Download audio, convert to 16kHz mono WAV. Returns path to WAV."""
    tmp = output_path.replace('.wav', '_tmp.wav')
    
    cmd = [
        'yt-dlp', '-f', 'bestaudio', '--extract-audio',
        '--audio-format', 'wav', '--audio-quality', '0',
        '-o', tmp, url, '--no-playlist', '--quiet'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(json.dumps({"error": f"yt-dlp failed: {result.stderr[:200]}"}))
        sys.exit(1)
    
    # Convert to 16kHz mono
    cmd2 = ['ffmpeg', '-y', '-i', tmp, '-ar', '16000', '-ac', '1', output_path, '-loglevel', 'error']
    r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=60)
    os.unlink(tmp)
    
    if r2.returncode != 0:
        print(json.dumps({"error": f"ffmpeg failed: {r2.stderr[:200]}"}))
        sys.exit(1)
    
    return output_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url', help='YouTube URL or video ID')
    parser.add_argument('--output', default=None, help='Output WAV path')
    args = parser.parse_args()
    
    if not re.match(r'^https?://', args.url):
        args.url = f'https://www.youtube.com/watch?v={args.url}'
    
    output = args.output or '/tmp/yt_audio.wav'
    path = download_audio(args.url, output)
    print(json.dumps({"audio_path": path, "size_mb": round(os.path.getsize(path)/1024/1024, 1)}))

if __name__ == '__main__':
    import re
    main()
