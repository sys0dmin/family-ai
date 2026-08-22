import 'package:flutter/material.dart';

class AgentPresentation {
  const AgentPresentation({
    required this.asset,
    required this.color,
    required this.softColor,
    this.avatarScale = 1,
    this.avatarAlignment = Alignment.center,
  });

  final String asset;
  final Color color;
  final Color softColor;
  final double avatarScale;
  final Alignment avatarAlignment;
}

const agentPresentations = <String, AgentPresentation>{
  'teacher_friend': AgentPresentation(
    asset: 'assets/characters/teacher-friend.webp',
    color: Color(0xFF356FC0),
    softColor: Color(0xFFE7F0FD),
  ),
  'scientist': AgentPresentation(
    asset: 'assets/characters/scientist.webp',
    color: Color(0xFF138B78),
    softColor: Color(0xFFE0F5EF),
  ),
  'storyteller': AgentPresentation(
    asset: 'assets/characters/storyteller.webp',
    color: Color(0xFF6654AD),
    softColor: Color(0xFFECE9F8),
  ),
  'socrates': AgentPresentation(
    asset: 'assets/characters/socrates.webp',
    color: Color(0xFFD87831),
    softColor: Color(0xFFFBEDDF),
  ),
  'musician': AgentPresentation(
    asset: 'assets/characters/musician.webp',
    color: Color(0xFF159C9A),
    softColor: Color(0xFFDFF7F4),
  ),
  'outdoor_guide': AgentPresentation(
    asset: 'assets/characters/murka.webp',
    color: Color(0xFF5F8F42),
    softColor: Color(0xFFEDF5DF),
  ),
  'tech_guide': AgentPresentation(
    asset: 'assets/characters/baytik.webp',
    color: Color(0xFF176B91),
    softColor: Color(0xFFE2F3F8),
  ),
  'space_guide': AgentPresentation(
    asset: 'assets/characters/alice-selezneva.webp',
    color: Color(0xFF7A4FC7),
    softColor: Color(0xFFEEE8FB),
    avatarScale: 1.7,
    avatarAlignment: Alignment.topCenter,
  ),
};

const fallbackAgentPresentation = AgentPresentation(
  asset: 'assets/characters/teacher-friend.webp',
  color: Color(0xFF356FC0),
  softColor: Color(0xFFE7F0FD),
);

AgentPresentation presentationFor(String agentId) {
  return agentPresentations[agentId] ?? fallbackAgentPresentation;
}
