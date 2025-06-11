#!/usr/bin/env python
# -*- coding: utf-8 -*-


# 05_generate_visualizations.py
import json
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import re
from textblob import TextBlob

class CBTVisualizer:
    def __init__(self):
        self.colors = {
            'rapport_building': '#8dd3c7',
            'problem_identification': '#ffffb3',
            'thought_exploration': '#bebada',
            'emotion_identification': '#fb8072',
            'behavioral_analysis': '#80b1d3',
            'cognitive_restructuring': '#fdb462',
            'homework_planning': '#b3de69',
            'session_closure': '#fccde5',
            'general_discussion': '#d9d9d9'
        }
        
    def load_data(self):
        """Load analysis data"""
        with open('data/analysis/cbt_analysis.json', 'r') as f:
            self.cbt_analysis = json.load(f)
            
    def create_session_timeline(self):
        """Create timeline visualization of CBT phases"""
        chapters = self.cbt_analysis['chapters_analysis']
        
        # Prepare data for Gantt chart
        timeline_data = []
        for i, chapter in enumerate(chapters):
            timeline_data.append({
                'Task': f"Topic {i+1}",
                'Start': chapter['start'],
                'Finish': chapter['start'] + chapter['duration'],
                'Phase': chapter['detected_phase'],
                'Description': chapter['headline'][:50] + '...',
                'Duration': f"{chapter['duration']/60:.1f} min"
            })
        
        # Create figure
        fig = go.Figure()
        
        # Add bars for each phase
        for i, item in enumerate(timeline_data):
            fig.add_trace(go.Scatter(
                x=[item['Start']/60, item['Finish']/60],
                y=[item['Task'], item['Task']],
                mode='lines',
                line=dict(
                    color=self.colors.get(item['Phase'], '#d9d9d9'),
                    width=30
                ),
                name=item['Phase'].replace('_', ' ').title(),
                text=f"{item['Phase'].replace('_', ' ').title()}<br>{item['Duration']}",
                hovertemplate='%{text}<br>%{x:.1f} min',
                showlegend=False
            ))
            
            # Add text labels
            fig.add_annotation(
                x=(item['Start'] + item['Finish'])/120,
                y=item['Task'],
                text=item['Phase'].replace('_', ' ').title()[:15],
                showarrow=False,
                font=dict(size=10, color='black'),
                bgcolor='rgba(255,255,255,0.8)'
            )
        
        fig.update_layout(
            title='CBT Session Timeline - Phase Progression',
            xaxis_title='Session Time (minutes)',
            yaxis_title='Topics',
            height=400,
            showlegend=False,
            plot_bgcolor='white',
            xaxis=dict(gridcolor='lightgray'),
            yaxis=dict(gridcolor='lightgray')
        )
        
        fig.write_image('data/reports/timeline.png', width=1200, height=400)
        print("✓ Timeline saved to data/reports/timeline.png")
        
    def create_speaking_metrics(self):
        """Create speaking ratio visualizations"""
        metrics = self.cbt_analysis['session_metrics']
        
        # Create subplots
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Speaking Time Distribution', 'Average Response Length'),
            specs=[[{'type': 'pie'}, {'type': 'bar'}]]
        )
        
        # Pie chart
        fig.add_trace(
            go.Pie(
                labels=['Therapist', 'Client'],
                values=[
                    metrics['speaking_ratio']['therapist'],
                    metrics['speaking_ratio']['client']
                ],
                marker_colors=['#4CAF50', '#2196F3'],
                textinfo='label+percent',
                textposition='auto'
            ),
            row=1, col=1
        )
        
        # Bar chart
        fig.add_trace(
            go.Bar(
                x=['Therapist', 'Client'],
                y=[
                    metrics['average_utterance_length']['therapist'],
                    metrics['average_utterance_length']['client']
                ],
                marker_color=['#4CAF50', '#2196F3'],
                text=[
                    f"{metrics['average_utterance_length']['therapist']:.0f}",
                    f"{metrics['average_utterance_length']['client']:.0f}"
                ],
                textposition='outside'
            ),
            row=1, col=2
        )
        
        fig.update_layout(
            title_text='Speaking Metrics Analysis',
            showlegend=False,
            height=400
        )
        
        fig.update_yaxes(title_text="Words per Utterance", row=1, col=2)
        
        fig.write_image('data/reports/speaking_metrics.png', width=1000, height=400)
        print("✓ Speaking metrics saved to data/reports/speaking_metrics.png")
        
    def create_techniques_chart(self):
        """Create therapeutic techniques bar chart"""
        techniques = self.cbt_analysis['therapeutic_techniques']
        
        # Filter techniques with count > 0
        used_techniques = {k: v for k, v in techniques.items() if v > 0}
        
        if not used_techniques:
            print("⚠ No therapeutic techniques detected")
            return
        
        # Create horizontal bar chart
        fig = go.Figure(go.Bar(
            y=[k.replace('_', ' ').title() for k in used_techniques.keys()],
            x=list(used_techniques.values()),
            orientation='h',
            marker_color='#FF6B6B',
            text=list(used_techniques.values()),
            textposition='outside'
        ))
        
        fig.update_layout(
            title='Therapeutic Techniques Used',
            xaxis_title='Frequency',
            yaxis_title='Technique',
            height=400,
            plot_bgcolor='white',
            xaxis=dict(gridcolor='lightgray')
        )
        
        fig.write_image('data/reports/techniques.png', width=800, height=400)
        print("✓ Techniques chart saved to data/reports/techniques.png")
        
    def create_phase_distribution(self):
        """Create phase distribution chart"""
        chapters = self.cbt_analysis['chapters_analysis']
        
        # Calculate time spent in each phase
        phase_times = {}
        for chapter in chapters:
            phase = chapter['detected_phase']
            if phase not in phase_times:
                phase_times[phase] = 0
            phase_times[phase] += chapter['duration'] / 60  # Convert to minutes
        
        # Create donut chart
        fig = go.Figure(go.Pie(
            labels=[p.replace('_', ' ').title() for p in phase_times.keys()],
            values=list(phase_times.values()),
            hole=0.4,
            marker_colors=[self.colors.get(p, '#d9d9d9') for p in phase_times.keys()],
            textinfo='label+percent',
            textposition='auto'
        ))
        
        fig.update_layout(
            title='Time Distribution Across CBT Phases',
            height=500,
            annotations=[
                dict(
                    text=f'{sum(phase_times.values()):.0f}<br>minutes',
                    x=0.5, y=0.5,
                    font_size=20,
                    showarrow=False
                )
            ]
        )
        
        fig.write_image('data/reports/phase_distribution.png', width=800, height=500)
        print("✓ Phase distribution saved to data/reports/phase_distribution.png")
        
    def create_session_summary_card(self):
        """Create a summary statistics card"""
        metrics = self.cbt_analysis['session_metrics']
        insights = self.cbt_analysis['clinical_insights']
        
        # Create figure with subplots for metrics
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Session Duration',
                'Total Utterances',
                'Therapist Question Ratio',
                'Clinical Insights'
            ),
            specs=[[{'type': 'indicator'}, {'type': 'indicator'}],
                   [{'type': 'indicator'}, {'type': 'indicator'}]]
        )
        
        # Duration
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=metrics['session_duration_minutes'],
                number={'suffix': " min"},
                domain={'x': [0, 1], 'y': [0, 1]}
            ),
            row=1, col=1
        )
        
        # Utterances
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=metrics['total_utterances'],
                domain={'x': [0, 1], 'y': [0, 1]}
            ),
            row=1, col=2
        )
        
        # Question ratio
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=metrics['therapist_question_ratio'] * 100,
                number={'suffix': "%"},
                domain={'x': [0, 1], 'y': [0, 1]}
            ),
            row=2, col=1
        )
        
        # Insights count
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=len(insights),
                domain={'x': [0, 1], 'y': [0, 1]}
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            title='Session Summary Statistics',
            height=400,
            showlegend=False
        )
        
        fig.write_image('data/reports/summary_card.png', width=800, height=400)
        print("✓ Summary card saved to data/reports/summary_card.png")

    def create_emotion_trajectory(self):
        """Create emotion trajectory based on text analysis"""
        
        # Load transcript
        with open('data/transcripts/assemblyai_transcript.json', 'r') as f:
            transcript = json.load(f)
        
        utterances = transcript['utterances']
        
        # Analyze sentiment using TextBlob if AssemblyAI sentiment is missing
        times = []
        sentiments = []
        speakers = []
        
        for utterance in utterances:
            # Use AssemblyAI sentiment if available
            if 'sentiment' in utterance and utterance['sentiment']:
                sentiment_mapping = {'POSITIVE': 1, 'NEUTRAL': 0, 'NEGATIVE': -1}
                sentiment_value = sentiment_mapping.get(utterance['sentiment'].upper(), 0)
            else:
                # Fallback: analyze text with TextBlob
                text = utterance['text']
                blob = TextBlob(text)
                # Convert polarity (-1 to 1) to our scale
                sentiment_value = blob.sentiment.polarity
            
            times.append(utterance['start'] / 60000)  # Convert to minutes
            sentiments.append(sentiment_value)
            speakers.append(utterance['speaker'])
        
        # Create the plot
        fig = go.Figure()
        
        # Separate by speaker
        for speaker, color, name in [('A', '#4CAF50', 'Therapist'), ('B', '#2196F3', 'Client')]:
            speaker_times = [t for t, s in zip(times, speakers) if s == speaker]
            speaker_sentiments = [s for s, sp in zip(sentiments, speakers) if sp == speaker]
            
            if speaker_times:
                # Add scatter plot with smoothed line
                fig.add_trace(go.Scatter(
                    x=speaker_times,
                    y=speaker_sentiments,
                    mode='markers+lines',
                    name=name,
                    line=dict(color=color, width=2, shape='spline'),
                    marker=dict(size=8, color=color),
                    hovertemplate='%{y:.2f}<br>%{x:.1f} min'
                ))
        
        # Add phase boundaries
        for chapter in self.cbt_analysis['chapters_analysis']:
            fig.add_vline(
                x=chapter['start'] / 60,
                line_dash="dash",
                line_color="gray",
                opacity=0.3
            )
        
        # Add zero line
        fig.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.2)
        
        fig.update_layout(
            title='Emotional Trajectory Throughout Session',
            xaxis_title='Session Time (minutes)',
            yaxis_title='Sentiment Score',
            yaxis=dict(
                tickmode='array',
                tickvals=[-1, -0.5, 0, 0.5, 1],
                ticktext=['Very Negative', 'Negative', 'Neutral', 'Positive', 'Very Positive'],
                range=[-1.2, 1.2]
            ),
            height=500,
            plot_bgcolor='white',
            xaxis=dict(gridcolor='lightgray'),
            yaxis_gridcolor='lightgray',
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )
        
        fig.write_image('data/reports/emotion_trajectory.png', width=1000, height=500)
        print("✓ Emotion trajectory saved to data/reports/emotion_trajectory.png")
        
    def generate_all_visualizations(self):
        """Generate all visualizations"""
        # Create output directory
        Path('data/reports').mkdir(parents=True, exist_ok=True)
        
        print("\n🎨 Generating visualizations...")
        
        self.create_session_timeline()
        self.create_speaking_metrics()
        self.create_techniques_chart()
        self.create_phase_distribution()
        self.create_session_summary_card()
        self.create_emotion_trajectory()
        
        print("\n✅ All visualizations generated!")
        print("📁 Images saved in: data/reports/")
        print("\nYou can now copy these images for your LinkedIn article:")
        print("  - timeline.png")
        print("  - speaking_metrics.png")
        print("  - techniques.png")
        print("  - phase_distribution.png")
        print("  - summary_card.png")

def main():

    visualizer = CBTVisualizer()
    visualizer.load_data()
    visualizer.generate_all_visualizations()

if __name__ == "__main__":
    main()

