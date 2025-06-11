#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Let's first check what's in the AssemblyAI data
import json

# Debug script to check sentiment data
with open('data/transcripts/assemblyai_transcript.json', 'r') as f:
    transcript = json.load(f)

# Check if sentiment exists
print("Checking for sentiment data...")
print(f"Keys in transcript: {transcript.keys()}")

if 'utterances' in transcript and len(transcript['utterances']) > 0:
    print(f"\nFirst utterance keys: {transcript['utterances'][0].keys()}")
    
    # Check if any utterance has sentiment
    has_sentiment = any('sentiment' in u for u in transcript['utterances'])
    print(f"Has sentiment data: {has_sentiment}")
    
    if has_sentiment:
        # Show a sample
        for u in transcript['utterances'][:5]:
            if 'sentiment' in u:
                print(f"Sentiment found: {u['sentiment']}")