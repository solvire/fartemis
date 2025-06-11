#!/usr/bin/env python
# -*- coding: utf-8 -*-

# 03_transcribe_with_assemblyai.py
import requests
import time
import json
from pathlib import Path
import os

# Get free API key at: https://www.assemblyai.com/
# get the key from env 
API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

def transcribe_therapy_session(audio_file):
    """Complete transcription with speaker labels"""
    headers = {"authorization": API_KEY}
    
    # Upload
    print("Uploading audio...")
    with open(audio_file, 'rb') as f:
        response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=f
        )
    audio_url = response.json()['upload_url']
    
    # Request transcription
    print("Starting transcription...")
    response = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=headers,
        json={
            "audio_url": audio_url,
            "speaker_labels": True,
            "speakers_expected": 2,
            "auto_chapters": True,  # Bonus: automatic topic segmentation
            "sentiment_analysis": True  # Bonus: emotion detection
        }
    )
    transcript_id = response.json()['id']
    
    # Poll for completion
    while True:
        response = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
            headers=headers
        )
        result = response.json()
        
        if result['status'] == 'completed':
            break
        elif result['status'] == 'error':
            raise Exception("Transcription failed")
        
        print(f"Status: {result['status']}...")
        time.sleep(5)
    
    return result

# Process and save
result = transcribe_therapy_session("therapy_session_cbt.wav")

Path("data/transcripts").mkdir(parents=True, exist_ok=True)
with open("data/transcripts/assemblyai_transcript.json", 'w') as f:
    json.dump(result, f, indent=2)

print("✓ Transcription complete!")
print(f"✓ Found {len(result['utterances'])} utterances")
print(f"✓ Detected {len(result['chapters'])} conversation topics")