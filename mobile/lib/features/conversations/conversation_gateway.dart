import 'dart:typed_data';

import 'activity_models.dart';
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

enum VoiceStreamEventType { started, message, audio, complete, error }

class VoiceStreamEvent {
  const VoiceStreamEvent({
    required this.type,
    this.turnId,
    this.messageId,
    this.audioBytes,
    this.contentType,
    this.audioIndex,
    this.chunkCount,
    this.errorMessage,
  });

  final VoiceStreamEventType type;
  final String? turnId;
  final String? messageId;
  final Uint8List? audioBytes;
  final String? contentType;
  final int? audioIndex;
  final int? chunkCount;
  final String? errorMessage;
}

class VoiceStreamingUnavailable implements Exception {
  const VoiceStreamingUnavailable();
}

abstract interface class ConversationGateway {
  Future<List<ActivitySummary>> getActivities(String agentId);

  Future<ActivitySession?> getActivityState(String conversationId);

  Future<ActivityActionResult> startActivity(
    String conversationId,
    String activityId,
  );

  Future<ActivityActionResult> resumeActivity(String conversationId);

  Future<ActivityActionResult> stopActivity(
    String conversationId, {
    required bool leaveForConversation,
  });

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

  Stream<VoiceStreamEvent> streamVoiceTurn({
    required String conversationId,
    required Uint8List audioBytes,
    required String filename,
    required String contentType,
    required Duration recordingDuration,
  });

  Future<VoiceTurnAudio> sendSpokenImageTurn({
    required String conversationId,
    required Uint8List imageBytes,
    required String imageFilename,
    required String imageContentType,
    required Uint8List audioBytes,
    required String audioFilename,
    required String audioContentType,
    required Duration recordingDuration,
  });

  Stream<VoiceStreamEvent> streamSpokenImageTurn({
    required String conversationId,
    required Uint8List imageBytes,
    required String imageFilename,
    required String imageContentType,
    required Uint8List audioBytes,
    required String audioFilename,
    required String audioContentType,
    required Duration recordingDuration,
  });

  Future<void> cancelVoiceStream(String turnId);

  Future<void> reportVoicePlayback({
    required String turnId,
    required Duration duration,
  });

  Future<SynthesizedAudio> synthesizeText({
    required String conversationId,
    required String text,
  });

  Uri resolveMediaUrl(String contentUrl);
}
