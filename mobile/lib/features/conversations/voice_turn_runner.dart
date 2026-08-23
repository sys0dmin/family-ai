part of 'voice_chat_controller.dart';

extension _VoiceTurnRunner on VoiceChatController {
  Future<void> _runStreamingTurn({
    required int operation,
    required String conversationId,
    required RecordedVoice recording,
    required PickedPhoto? photo,
  }) async {
    final stopwatch = Stopwatch()..start();
    final stream = photo == null
        ? _gateway.streamVoiceTurn(
            conversationId: conversationId,
            audioBytes: recording.bytes,
            filename: recording.filename,
            contentType: recording.contentType,
            recordingDuration: recording.duration,
          )
        : _gateway.streamSpokenImageTurn(
            conversationId: conversationId,
            imageBytes: photo.bytes,
            imageFilename: photo.filename,
            imageContentType: photo.contentType,
            audioBytes: recording.bytes,
            audioFilename: recording.filename,
            audioContentType: recording.contentType,
            recordingDuration: recording.duration,
          );
    final iterator = StreamIterator(stream);
    _activeStream = iterator;
    String? messageId;
    String? audioContentType;
    final audioParts = <Uint8List>[];
    var playbackReported = false;
    var completed = false;
    try {
      streamEvents:
      while (await iterator.moveNext()) {
        if (!_isCurrent(operation)) return;
        final event = iterator.current;
        switch (event.type) {
          case VoiceStreamEventType.started:
            _activeTurnId = event.turnId;
            break;
          case VoiceStreamEventType.message:
            messageId = event.messageId;
            break;
          case VoiceStreamEventType.audio:
            final bytes = event.audioBytes;
            final contentType = event.contentType;
            if (bytes == null || bytes.isEmpty || contentType == null) {
              throw const GatewayException(
                'Сервер вернул пустую часть голосового ответа.',
              );
            }
            _stageTimer?.cancel();
            _stageTimer = null;
            _setStage(VoiceTurnStage.speaking);
            audioContentType ??= contentType;
            audioParts.add(bytes);
            await _voiceSession.play(
              bytes,
              contentType: contentType,
              onStarted: () {
                if (playbackReported) return;
                playbackReported = true;
                final turnId = _activeTurnId;
                if (turnId != null) {
                  unawaited(
                    _gateway.reportVoicePlayback(
                      turnId: turnId,
                      duration: stopwatch.elapsed,
                    ),
                  );
                }
              },
            );
            break;
          case VoiceStreamEventType.complete:
            completed = true;
            unawaited(iterator.cancel());
            break streamEvents;
          case VoiceStreamEventType.error:
            throw GatewayException(
              event.errorMessage ??
                  'Не получилось подготовить голосовой ответ.',
            );
        }
      }
    } finally {
      if (identical(_activeStream, iterator)) {
        _activeStream = null;
        _activeTurnId = null;
      }
    }
    if (!completed || messageId == null || audioParts.isEmpty) {
      throw const GatewayException('Голосовой ответ пришёл не полностью.');
    }
    if (!_isCurrent(operation)) return;
    final merged = AudioFormat.mergeWavParts(audioParts);
    if (merged != null && audioContentType != null) {
      try {
        await _voiceReplyCache.write(
          conversationId: conversationId,
          messageId: messageId,
          bytes: merged,
          contentType: audioContentType,
        );
      } catch (_) {
        // Streaming playback remains successful if caching fails.
      }
    }
    if (!_isCurrent(operation)) return;
    final reply = await _loadVoiceReply(conversationId, messageId);
    if (!_isCurrent(operation)) return;
    _conversation.appendMessage(reply);
    await _conversation.refreshActivityState();
  }

  Future<void> _runLegacyTurn({
    required int operation,
    required String conversationId,
    required RecordedVoice recording,
    required PickedPhoto? photo,
  }) async {
    final response = photo == null
        ? await _gateway.sendVoiceTurn(
            conversationId: conversationId,
            audioBytes: recording.bytes,
            filename: recording.filename,
            contentType: recording.contentType,
            recordingDuration: recording.duration,
          )
        : await _gateway.sendSpokenImageTurn(
            conversationId: conversationId,
            imageBytes: photo.bytes,
            imageFilename: photo.filename,
            imageContentType: photo.contentType,
            audioBytes: recording.bytes,
            audioFilename: recording.filename,
            audioContentType: recording.contentType,
            recordingDuration: recording.duration,
          );
    _stageTimer?.cancel();
    _stageTimer = null;
    if (!_isCurrent(operation)) return;
    final reply = await _loadVoiceReply(conversationId, response.messageId);
    if (!_isCurrent(operation)) return;
    _conversation.appendMessage(reply);
    await _conversation.refreshActivityState();
    _setStage(VoiceTurnStage.speaking);
    try {
      await _voiceReplyCache.write(
        conversationId: conversationId,
        messageId: reply.id,
        bytes: response.audioBytes,
        contentType: response.contentType,
      );
    } catch (_) {
      // Playback remains available even if persistent caching fails.
    }
    if (!_isCurrent(operation)) return;
    await _voiceSession.play(
      response.audioBytes,
      contentType: response.contentType,
    );
  }

  Future<ConversationMessage> _loadVoiceReply(
    String conversationId,
    String? messageId,
  ) async {
    if (messageId != null) {
      try {
        return await _gateway.getMessage(conversationId, messageId);
      } on GatewayException {
        // The audio response remains useful if message refresh fails.
      }
    }
    return ConversationMessage(
      id: messageId ?? 'local-reply-${DateTime.now().microsecondsSinceEpoch}',
      role: 'assistant',
      content: '🔊 Голосовой ответ',
    );
  }
}
