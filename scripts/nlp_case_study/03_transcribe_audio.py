#!/usr/bin/env python
# -*- coding: utf-8 -*-

# 03_transcribe_audio.py
import whisper
import json
from pathlib import Path
import numpy as np
from pydub import AudioSegment

class TherapyTranscriber:
    def __init__(self, model_size="base"):
        """Initialize Whisper model"""
        print(f"Loading Whisper {model_size} model...")
        self.model = whisper.load_model(model_size)
        self.audio_file = None
        self.audio_data = None
        
    def load_audio(self, audio_file):
        """Load audio file for processing"""
        self.audio_file = audio_file
        # Load audio using pydub for easier segment extraction
        audio = AudioSegment.from_wav(audio_file)
        # Convert to numpy array for Whisper
        samples = np.array(audio.get_array_of_samples())
        if audio.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1)
        self.audio_data = samples.astype(np.float32) / 32768.0
        self.sample_rate = audio.frame_rate
        
    def transcribe_segment(self, start_time, end_time):
        """Transcribe a specific segment of audio"""
        # Extract segment
        start_sample = int(start_time * self.sample_rate)
        end_sample = int(end_time * self.sample_rate)
        segment_audio = self.audio_data[start_sample:end_sample]
        
        # Transcribe
        result = self.model.transcribe(
            segment_audio,
            language="en",
            fp16=False  # Set to True if you have GPU
        )
        
        return result["text"].strip()
    
    def process_with_diarization(self, diarization_file, audio_file):
        """Transcribe audio using diarization results"""
        # Load diarization results
        with open(diarization_file, 'r') as f:
            segments = json.load(f)
        
        # Load audio
        self.load_audio(audio_file)
        
        # Process each segment
        transcribed_segments = []
        total_segments = len(segments)
        
        for i, segment in enumerate(segments):
            print(f"Transcribing segment {i+1}/{total_segments} "
                  f"({segment['role']} @ {segment['start']:.1f}s)...")
            
            # Transcribe this segment
            text = self.transcribe_segment(
                segment['start'], 
                segment['end']
            )
            
            # Create enhanced segment
            transcribed_segment = {
                **segment,  # Include all original data
                "text": text,
                "word_count": len(text.split()),
            }
            
            transcribed_segments.append(transcribed_segment)
            
            # Print preview
            preview = text[:80] + "..." if len(text) > 80 else text
            print(f"  → {preview}")
        
        return transcribed_segments
    
    def create_formatted_transcript(self, segments):
        """Create a readable transcript"""
        transcript_lines = []
        
        for segment in segments:
            timestamp = f"[{segment['start']:.1f}s - {segment['end']:.1f}s]"
            speaker = segment['role'].upper()
            text = segment['text']
            
            transcript_lines.append(
                f"{timestamp} {speaker}:\n{text}\n"
            )
        
        return "\n".join(transcript_lines)
    
    def analyze_conversation_metrics(self, segments):
        """Calculate conversation metrics"""
        metrics = {
            "therapist": {"word_count": 0, "speaking_time": 0, "turn_count": 0},
            "client": {"word_count": 0, "speaking_time": 0, "turn_count": 0}
        }
        
        for segment in segments:
            role = segment['role']
            metrics[role]['word_count'] += segment['word_count']
            metrics[role]['speaking_time'] += segment['duration']
            metrics[role]['turn_count'] += 1
        
        # Calculate ratios
        total_words = metrics['therapist']['word_count'] + metrics['client']['word_count']
        total_time = metrics['therapist']['speaking_time'] + metrics['client']['speaking_time']
        
        metrics['ratios'] = {
            'word_ratio': metrics['therapist']['word_count'] / total_words,
            'time_ratio': metrics['therapist']['speaking_time'] / total_time,
            'avg_therapist_response': metrics['therapist']['word_count'] / metrics['therapist']['turn_count'],
            'avg_client_response': metrics['client']['word_count'] / metrics['client']['turn_count']
        }
        
        return metrics

def main():
    # Configuration
    AUDIO_FILE = "therapy_session_cbt.wav"
    DIARIZATION_FILE = "data/transcripts/diarization_results_fixed.json"
    OUTPUT_DIR = Path("data/transcripts")
    
    # Initialize transcriber
    transcriber = TherapyTranscriber(model_size="base")
    
    # Process audio with diarization
    print("Starting transcription with speaker diarization...")
    segments = transcriber.process_with_diarization(
        DIARIZATION_FILE, 
        AUDIO_FILE
    )
    
    # Save detailed results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save JSON with all data
    with open(OUTPUT_DIR / "transcribed_segments.json", 'w') as f:
        json.dump(segments, f, indent=2)
    
    # Save formatted transcript
    transcript = transcriber.create_formatted_transcript(segments)
    with open(OUTPUT_DIR / "formatted_transcript.txt", 'w') as f:
        f.write(transcript)
    
    # Calculate and save metrics
    metrics = transcriber.analyze_conversation_metrics(segments)
    with open(OUTPUT_DIR / "conversation_metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    
    # Print summary
    print("\n=== Transcription Complete ===")
    print(f"Total segments: {len(segments)}")
    print(f"\nConversation Metrics:")
    print(f"  Therapist: {metrics['therapist']['word_count']} words "
          f"({metrics['ratios']['word_ratio']:.1%})")
    print(f"  Client: {metrics['client']['word_count']} words "
          f"({100 - metrics['ratios']['word_ratio']:.1%})")
    print(f"\nAverage response length:")
    print(f"  Therapist: {metrics['ratios']['avg_therapist_response']:.0f} words")
    print(f"  Client: {metrics['ratios']['avg_client_response']:.0f} words")

if __name__ == "__main__":
    # First fix the roles
    import subprocess
    subprocess.run(["python", "fix_diarization_roles.py"])
    
    # Then run transcription
    main()

