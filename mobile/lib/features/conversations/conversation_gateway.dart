import 'dart:typed_data';

import 'conversation_models.dart';

class VoiceTurnAudio {
  const VoiceTurnAudio({
    required this.audioBytes,
    required this.contentType,
    this.messageId,
  });

  final Uint8List audioBytes;
  final String contentType;
  final String? messageId;
}

class SynthesizedAudio {
  const SynthesizedAudio({required this.audioBytes, required this.contentType});

  final Uint8List audioBytes;
  final String contentType;
}

abstract interface class ConversationGateway {
  Future<ConversationHistory> getLatestConversation(String agentId);

  Future<String> createConversation(String agentId);

  Future<ConversationMessage> sendTextTurn(String conversationId, String text);

  Future<ConversationMessage> sendImageTurn({
    required String conversationId,
    required Uint8List imageBytes,
    required String filename,
    required String contentType,
    required String question,
  });

  Future<ConversationMessage> getMessage(
    String conversationId,
    String messageId,
  );

  Future<VoiceTurnAudio> sendVoiceTurn({
    required String conversationId,
    required Uint8List audioBytes,
    required String filename,
    required String contentType,
    required Duration recordingDuration,
  });

  Future<SynthesizedAudio> synthesizeText({
    required String conversationId,
    required String text,
  });

  Uri resolveMediaUrl(String contentUrl);
}
