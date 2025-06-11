#!/usr/bin/env python
# -*- coding: utf-8 -*-

# 04_segment_classifier.py
import json
from pathlib import Path
from datetime import datetime
import re

class CBTSessionAnalyzer:
    def __init__(self):
        # CBT phase keywords and patterns
        self.cbt_phases = {
            "rapport_building": {
                "keywords": ["how are you", "tell me about", "nice to meet", 
                            "comfortable", "thank you for coming", "how's your week"],
                "description": "Establishing therapeutic alliance"
            },
            "problem_identification": {
                "keywords": ["problem", "issue", "concern", "struggle", "difficult",
                            "challenge", "what brings you", "help with", "bothering"],
                "description": "Identifying specific issues to address"
            },
            "thought_exploration": {
                "keywords": ["think", "thought", "believe", "assume", "mind",
                            "tell yourself", "cognitive", "perception", "interpret"],
                "description": "Exploring thought patterns and cognitions"
            },
            "emotion_identification": {
                "keywords": ["feel", "emotion", "angry", "sad", "anxious", "worried",
                            "scared", "frustrated", "upset", "mood"],
                "description": "Identifying and validating emotions"
            },
            "behavioral_analysis": {
                "keywords": ["do", "did", "behavior", "action", "react", "response",
                            "avoid", "cope", "handle", "manage"],
                "description": "Examining behavioral patterns"
            },
            "cognitive_restructuring": {
                "keywords": ["evidence", "alternative", "realistic", "helpful",
                            "rational", "reframe", "challenge", "question", "examine"],
                "description": "Challenging and reframing thoughts"
            },
            "homework_planning": {
                "keywords": ["practice", "homework", "try", "week", "next time",
                            "assignment", "exercise", "work on", "implement"],
                "description": "Setting goals and homework"
            },
            "session_closure": {
                "keywords": ["summary", "recap", "remember", "takeaway", "learned",
                            "progress", "see you", "next session", "goodbye"],
                "description": "Wrapping up and summarizing"
            }
        }
        
    def load_transcript(self, filepath):
        """Load AssemblyAI transcript"""
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def classify_utterance(self, text):
        """Classify which CBT phase an utterance belongs to"""
        text_lower = text.lower()
        scores = {}
        
        for phase, config in self.cbt_phases.items():
            score = 0
            for keyword in config["keywords"]:
                if keyword in text_lower:
                    score += 1
            scores[phase] = score
        
        # Get phase with highest score
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "general_discussion"
    
    def analyze_chapters(self, chapters):
        """Analyze AssemblyAI's auto-detected chapters"""
        analyzed_chapters = []
        
        for chapter in chapters:
            # Classify the chapter summary
            phase = self.classify_utterance(chapter['summary'])
            
            analyzed_chapters.append({
                "start": chapter['start'] / 1000,  # Convert to seconds
                "end": chapter['end'] / 1000,
                "duration": (chapter['end'] - chapter['start']) / 1000,
                "summary": chapter['summary'],
                "headline": chapter['headline'],
                "detected_phase": phase,
                "phase_description": self.cbt_phases.get(phase, {}).get("description", "General discussion")
            })
        
        return analyzed_chapters
    
    def analyze_therapeutic_techniques(self, utterances):
        """Identify specific therapeutic techniques used"""
        techniques = {
            "socratic_questioning": 0,
            "validation": 0,
            "reframing": 0,
            "psychoeducation": 0,
            "homework_assignment": 0,
            "summarizing": 0,
            "empathy_statements": 0
        }
        
        therapist_utterances = [u for u in utterances if u['speaker'] == 'A']
        
        for utterance in therapist_utterances:
            text = utterance['text'].lower()
            
            # Socratic questioning
            if '?' in text and any(word in text for word in ['what', 'how', 'why', 'when', 'could']):
                techniques['socratic_questioning'] += 1
            
            # Validation
            if any(phrase in text for phrase in ['i understand', 'that makes sense', 'i hear you', "that's valid"]):
                techniques['validation'] += 1
            
            # Reframing
            if any(phrase in text for phrase in ['another way', 'different perspective', 'consider', 'what if']):
                techniques['reframing'] += 1
            
            # Psychoeducation
            if any(phrase in text for phrase in ['research shows', 'typically', 'common', 'normal']):
                techniques['psychoeducation'] += 1
            
            # Homework
            if any(phrase in text for phrase in ['practice', 'try this', 'homework', 'week']):
                techniques['homework_assignment'] += 1
            
            # Summarizing
            if any(phrase in text for phrase in ['so what you', 'let me make sure', 'to summarize']):
                techniques['summarizing'] += 1
            
            # Empathy
            if any(phrase in text for phrase in ['must be', 'sounds like', 'i can imagine']):
                techniques['empathy_statements'] += 1
        
        return techniques
    
    def calculate_session_metrics(self, utterances):
        """Calculate therapeutic quality metrics"""
        therapist_utterances = [u for u in utterances if u['speaker'] == 'A']
        client_utterances = [u for u in utterances if u['speaker'] == 'B']
        
        # Speaking ratio
        therapist_words = sum(len(u['text'].split()) for u in therapist_utterances)
        client_words = sum(len(u['text'].split()) for u in client_utterances)
        total_words = therapist_words + client_words
        
        # Question ratio (therapist questions vs statements)
        therapist_questions = sum(1 for u in therapist_utterances if '?' in u['text'])
        
        # Average response length
        avg_therapist_length = therapist_words / len(therapist_utterances) if therapist_utterances else 0
        avg_client_length = client_words / len(client_utterances) if client_utterances else 0
        
        # Sentiment analysis summary
        sentiment_scores = {'positive': 0, 'negative': 0, 'neutral': 0}
        for u in utterances:
            if 'sentiment' in u:
                sentiment_scores[u['sentiment']] += 1
        
        return {
            "speaking_ratio": {
                "therapist": therapist_words / total_words if total_words > 0 else 0,
                "client": client_words / total_words if total_words > 0 else 0
            },
            "therapist_question_ratio": therapist_questions / len(therapist_utterances) if therapist_utterances else 0,
            "average_utterance_length": {
                "therapist": avg_therapist_length,
                "client": avg_client_length
            },
            "sentiment_distribution": sentiment_scores,
            "total_utterances": len(utterances),
            "session_duration_minutes": utterances[-1]['end'] / 60000 if utterances else 0
        }
    
    def generate_clinical_insights(self, analysis_results):
        """Generate actionable insights for the therapist"""
        insights = []
        metrics = analysis_results['session_metrics']
        techniques = analysis_results['therapeutic_techniques']
        
        # Speaking ratio insight
        if metrics['speaking_ratio']['therapist'] > 0.4:
            insights.append({
                "type": "speaking_balance",
                "severity": "medium",
                "insight": "Consider allowing more client speaking time. Therapist spoke 40%+ of the session.",
                "recommendation": "Use more open-ended questions and longer pauses."
            })
        
        # Question usage
        if metrics['therapist_question_ratio'] < 0.2:
            insights.append({
                "type": "questioning",
                "severity": "medium",
                "insight": "Low use of questions (< 20% of therapist utterances).",
                "recommendation": "Increase Socratic questioning to promote client self-discovery."
            })
        
        # Validation frequency
        if techniques['validation'] < 3:
            insights.append({
                "type": "validation",
                "severity": "low",
                "insight": "Limited validation statements observed.",
                "recommendation": "Increase validation to strengthen therapeutic alliance."
            })
        
        # CBT structure
        phases_covered = len(set(ch['detected_phase'] for ch in analysis_results['chapters_analysis']))
        if phases_covered < 4:
            insights.append({
                "type": "session_structure",
                "severity": "medium",
                "insight": f"Only {phases_covered} distinct CBT phases detected.",
                "recommendation": "Consider a more structured approach covering all CBT components."
            })
        
        return insights

def main():
    # Load AssemblyAI transcript
    analyzer = CBTSessionAnalyzer()
    transcript = analyzer.load_transcript("data/transcripts/assemblyai_transcript.json")
    
    # Analyze chapters/topics
    chapters_analysis = analyzer.analyze_chapters(transcript['chapters'])
    
    # Analyze therapeutic techniques
    techniques = analyzer.analyze_therapeutic_techniques(transcript['utterances'])
    
    # Calculate session metrics
    metrics = analyzer.calculate_session_metrics(transcript['utterances'])
    
    # Generate insights
    analysis_results = {
        "session_id": transcript['id'],
        "analysis_timestamp": datetime.now().isoformat(),
        "chapters_analysis": chapters_analysis,
        "therapeutic_techniques": techniques,
        "session_metrics": metrics
    }
    
    insights = analyzer.generate_clinical_insights(analysis_results)
    analysis_results['clinical_insights'] = insights
    
    # Save results
    output_dir = Path("data/analysis")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "cbt_analysis.json", 'w') as f:
        json.dump(analysis_results, f, indent=2)
    
    # Print summary
    print("\n=== CBT Session Analysis ===")
    print(f"\nDetected CBT Phases:")
    for chapter in chapters_analysis:
        print(f"  • {chapter['headline']}")
        print(f"    Phase: {chapter['detected_phase']} ({chapter['phase_description']})")
        print(f"    Duration: {chapter['duration']:.1f} seconds\n")
    
    print(f"\nTherapeutic Techniques Used:")
    for technique, count in techniques.items():
        if count > 0:
            print(f"  • {technique.replace('_', ' ').title()}: {count} times")
    
    print(f"\nSession Metrics:")
    print(f"  • Speaking ratio - Therapist: {metrics['speaking_ratio']['therapist']:.1%}, "
          f"Client: {metrics['speaking_ratio']['client']:.1%}")
    print(f"  • Question ratio: {metrics['therapist_question_ratio']:.1%} of therapist utterances")
    print(f"  • Session duration: {metrics['session_duration_minutes']:.1f} minutes")
    
    print(f"\nClinical Insights:")
    for insight in insights:
        print(f"  • [{insight['severity'].upper()}] {insight['insight']}")
        print(f"    → {insight['recommendation']}")

if __name__ == "__main__":
    main()
