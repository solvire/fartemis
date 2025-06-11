#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Processing: therapy_session_cbt.wav
Diarization completed.
Found 66 segments.

=== Diarization Summary ===

SPEAKER_01:
  Total speaking time: 216.7 seconds
  Number of segments: 32
  Average segment length: 6.8 seconds
  Identified as: client

SPEAKER_00:
  Total speaking time: 497.9 seconds
  Number of segments: 34
  Average segment length: 14.6 seconds
  Identified as: client
Saved diarization results to: data/transcripts/diarization_results.json

real	438m59.143s
user	127m54.528s
sys	11m33.467s
"""

import torch
from pyannote.audio import Pipeline
import json
from pathlib import Path
import os


class TherapySessionDiarizer:
    def __init__(self, auth_token: str) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device} token: {auth_token}")
        
        # Load pretrained pipeline (no device parameter here)
        self.pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization@2.1",
            use_auth_token=auth_token
        )
        # Move to device after loading
        self.pipeline.to(self.device)



    def diarize(self, audio_file: str) -> dict:
        """Diarize the given audio file and return speaker segments.
        Args:
            audio_file (str): Path to the audio file to be diarized.
        Returns:
            dict: A dictionary containing speaker segments with start and end times.
        """
        print(f"Processing: {audio_file}")
        
        diarization = self.pipeline(
            audio_file,
            num_speakers=2
        )
        print("Diarization completed.")
        if not diarization:
            print("No diarization results found.")
            return {}
        
        segments = []

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            start = turn.start
            end = turn.end
            segments.append({
                "start": start,
                "end": end,
                "speaker": speaker,
                "duration": end - start
            })
        print(f"Found {len(segments)} segments.")
        return segments

    def identify_roles(self, segments: list) -> list:
        """
        Identify therapist vs client based on speaking patterns.
        Therapist typically has fewer, longer segments.
        Not 100% accurate, but works for therapy sessions.
        Args:
            segments (list): List of segments with speaker information.
        Returns:
            list: Updated segments with identified roles.
        1. Calculate total speaking time and segment count for each speaker.
        2. Calculate average segment length for each speaker.
        3. Assign roles based on average segment length.
        4. Update segments with assigned roles.
        5. Return updated segments with roles.
        """
        speaker_stats = {}
        for seg in segments:
            speaker = seg['speaker']
            if speaker not in speaker_stats:
                speaker_stats[speaker] = {
                    'total_time': 0,
                    'segment_count': 0,
                    'segments': []
                }
            speaker_stats[speaker]['total_time'] += seg['duration']
            speaker_stats[speaker]['segment_count'] += 1
            speaker_stats[speaker]['segments'].append(seg)
        
        # Calculate average segment length
        for speaker, stats in speaker_stats.items():
            stats['avg_segment_length'] = (
                stats['total_time'] / stats['segment_count']
            )
        
        # Assign roles (therapist usually has longer average segments)
        speakers_by_avg_length = sorted(
            speaker_stats.items(), 
            key=lambda x: x[1]['avg_segment_length'],
            reverse=True
        )
        
        # Map speakers to roles
        role_mapping = {
            speakers_by_avg_length[0][0]: "therapist",
            speakers_by_avg_length[1][0]: "client"
        }
        
        # Update segments with roles
        for seg in segments:
            seg['role'] = role_mapping[seg['speaker']]
        
        return segments, speaker_stats
    
    def save_results(self, segments, output_file):
        """Save diarization results to JSON."""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(segments, f, indent=2)
        
        print(f"Saved diarization results to: {output_file}")

def main():
    # get huggingface token from environment variable
    HF_TOKEN = os.getenv("HF_TOKEN")

    AUDIO_FILE = "therapy_session_cbt.wav"
    OUTPUT_FILE = "data/transcripts/diarization_results.json"


    # Initialize diarizer
    diarizer = TherapySessionDiarizer(auth_token=HF_TOKEN)
    
    # Perform diarization
    segments = diarizer.diarize(AUDIO_FILE)
    
    # Identify roles
    segments_with_roles, speaker_stats = diarizer.identify_roles(segments)

    # Print summary
    print("\n=== Diarization Summary ===")
    for speaker, stats in speaker_stats.items():
        print(f"\n{speaker}:")
        print(f"  Total speaking time: {stats['total_time']:.1f} seconds")
        print(f"  Number of segments: {stats['segment_count']}")
        print(f"  Average segment length: {stats['avg_segment_length']:.1f} seconds")
        print(f"  Identified as: {segments_with_roles[0]['role'] if segments_with_roles[0]['speaker'] == speaker else 'client'}")
    
    # Save results
    diarizer.save_results(segments_with_roles, OUTPUT_FILE)

if __name__ == "__main__":
    main()

