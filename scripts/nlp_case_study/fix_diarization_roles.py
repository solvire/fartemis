#!/usr/bin/env python
# -*- coding: utf-8 -*-

# fix_diarization_roles.py
import json

# Load the results
with open('data/transcripts/diarization_results.json', 'r') as f:
    segments = json.load(f)

# Fix the role assignment
for segment in segments:
    if segment['speaker'] == 'SPEAKER_00':
        segment['role'] = 'therapist'
    else:
        segment['role'] = 'client'

# Save the corrected results
with open('data/transcripts/diarization_results_fixed.json', 'w') as f:
    json.dump(segments, f, indent=2)

print("Fixed role assignments")
