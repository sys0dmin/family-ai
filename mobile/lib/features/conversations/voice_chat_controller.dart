import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/network/gateway_client.dart';
import '../voice/voice_reply_cache.dart';
import '../voice/voice_session.dart';
import 'conversation_controller.dart';
import 'conversation_gateway.dart';
import 'conversation_models.dart';
import 'photo_picker.dart';

enum VoiceTurnStage {
  idle,
  listening,
  understanding,
  looking,
  thinking,
  speaking,
  error,
}

class VoiceChatController extends ChangeNotifier {
  VoiceChatController(
    this._gateway,
    this._conversation,
    this._voiceSession,
    this._voiceReplyCache,
  );

  final ConversationGateway _gateway;
  final ConversationController _conversation;
  final VoiceSession _voiceSession;
  final VoiceReplyCache _voiceReplyCache;
  Timer? _recordingTimer;
  Timer? _stageTimer;
  VoiceTurnStage _stage = VoiceTurnStage.idle;
  String? _replayingMessageId;
  PickedPhoto? _pendingPhoto;
  int _operation = 0;
  bool _disposed = false;

  VoiceTurnStage get stage => _stage;
  String? get replayingMessageId => _replayingMessageId;
  Uint8List? get pendingPhotoBytes => _pendingPhoto?.bytes;
  bool get askingAboutPhoto => _pendingPhoto != null;
  bool get recording => _stage == VoiceTurnStage.listening;
  bool get active => switch (_stage) {
    VoiceTurnStage.listening ||
    VoiceTurnStage.understanding ||
    VoiceTurnStage.looking ||
    VoiceTurnStage.thinking ||
    VoiceTurnStage.speaking => true,
    _ => false,
  };

  Future<void> toggleRecording() async {
    if (_conversation.loading || _conversation.sendingText) return;
    if (recording) {
      await stopAndSend();
      return;
    }
    if (active) return;
    _pendingPhoto = null;
    await _startRecording();
  }

  Future<void> startSpokenImageQuestion(PickedPhoto photo) async {
    if (_conversation.busy || active) return;
    _pendingPhoto = photo;
    notifyListeners();
    await _startRecording();
  }

  Future<void> _startRecording() async {
    final operation = ++_operation;
    _conversation.clearError();
    try {
      await _voiceSession.startRecording();
      if (!_isCurrent(operation)) return;
      _setStage(VoiceTurnStage.listening);
      _recordingTimer = Timer(const Duration(seconds: 55), stopAndSend);
    } on VoiceSessionException catch (error) {
      _fail(error.message, operation);
    } catch (_) {
      _fail('Не удалось включить микрофон.', operation);
    }
  }

  Future<void> stopAndSend() async {
    if (!recording) return;
    final operation = _operation;
    _recordingTimer?.cancel();
    _recordingTimer = null;
    _conversation.setVoiceBusy(true);
    _setStage(VoiceTurnStage.understanding);

    try {
      final recording = await _voiceSession.stopRecording();
      if (!_isCurrent(operation)) return;
      _conversation.appendMessage(
        ConversationMessage(
          id: 'local-voice-${DateTime.now().microsecondsSinceEpoch}',
          role: 'child',
          content: _pendingPhoto == null
              ? '🎙️ Голосовое сообщение'
              : '📷🎙️ Вопрос о фотографии',
        ),
      );
      final conversationId = await _conversation.ensureConversation();
      if (!_isCurrent(operation)) return;

      // The current one-shot HTTP API cannot expose exact STT/LLM boundaries.
      // Yield once so the child sees the "understanding" state before waiting.
      await Future<void>.delayed(const Duration(milliseconds: 180));
      if (!_isCurrent(operation)) return;
      final photo = _pendingPhoto;
      _setStage(
        photo == null ? VoiceTurnStage.thinking : VoiceTurnStage.looking,
      );
      if (photo != null) {
        _stageTimer = Timer(const Duration(seconds: 3), () {
          if (_isCurrent(operation) && _stage == VoiceTurnStage.looking) {
            _setStage(VoiceTurnStage.thinking);
          }
        });
      }
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

      var reply = ConversationMessage(
        id:
            response.messageId ??
            'local-reply-${DateTime.now().microsecondsSinceEpoch}',
        role: 'assistant',
        content: '🔊 Голосовой ответ',
      );
      if (response.messageId != null) {
        try {
          reply = await _gateway.getMessage(
            conversationId,
            response.messageId!,
          );
        } on GatewayException {
          // The audio response remains useful if message refresh fails.
        }
      }
      if (!_isCurrent(operation)) return;
      _conversation.appendMessage(reply);
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
      if (_isCurrent(operation)) {
        _pendingPhoto = null;
        _setStage(VoiceTurnStage.idle);
      }
    } on VoiceSessionException catch (error) {
      _fail(error.message, operation);
    } on GatewayException catch (error) {
      _fail(error.message, operation);
    } catch (_) {
      _fail('Ответ пришёл, но звук не воспроизвёлся.', operation);
    } finally {
      if (_isCurrent(operation)) {
        _conversation.setVoiceBusy(false);
      }
    }
  }

  Future<void> replay(ConversationMessage message) async {
    final conversationId = _conversation.conversationId;
    if (conversationId == null || message.isChild || active) return;
    final operation = ++_operation;
    _replayingMessageId = message.id;
    _conversation.setVoiceBusy(true);
    _conversation.clearError();
    _setStage(VoiceTurnStage.speaking);
    try {
      var audio = await _voiceReplyCache.read(
        conversationId: conversationId,
        messageId: message.id,
      );
      if (audio == null) {
        final synthesized = await _gateway.synthesizeText(
          conversationId: conversationId,
          text: message.content,
        );
        audio = CachedVoiceReply(
          bytes: synthesized.audioBytes,
          contentType: synthesized.contentType,
        );
        try {
          await _voiceReplyCache.write(
            conversationId: conversationId,
            messageId: message.id,
            bytes: audio.bytes,
            contentType: audio.contentType,
          );
        } catch (_) {
          // The freshly synthesized answer can still be played.
        }
      }
      if (!_isCurrent(operation)) return;
      await _voiceSession.play(audio.bytes, contentType: audio.contentType);
      if (_isCurrent(operation)) _setStage(VoiceTurnStage.idle);
    } on GatewayException catch (error) {
      _fail(error.message, operation);
    } on VoiceSessionException catch (error) {
      _fail(error.message, operation);
    } catch (_) {
      _fail('Не удалось повторить голосовой ответ.', operation);
    } finally {
      if (_isCurrent(operation)) {
        _replayingMessageId = null;
        _conversation.setVoiceBusy(false);
        notifyListeners();
      }
    }
  }

  Future<void> cancel() async {
    ++_operation;
    _recordingTimer?.cancel();
    _recordingTimer = null;
    _stageTimer?.cancel();
    _stageTimer = null;
    try {
      if (recording) {
        await _voiceSession.cancelRecording();
      } else {
        await _voiceSession.stopPlayback();
      }
    } finally {
      _replayingMessageId = null;
      _pendingPhoto = null;
      _conversation.setVoiceBusy(false);
      _setStage(VoiceTurnStage.idle);
    }
  }

  void _fail(String message, int operation) {
    if (!_isCurrent(operation)) return;
    _conversation.setError(message);
    _conversation.setVoiceBusy(false);
    _pendingPhoto = null;
    _stageTimer?.cancel();
    _stageTimer = null;
    _setStage(VoiceTurnStage.error);
  }

  bool _isCurrent(int operation) => !_disposed && operation == _operation;

  void _setStage(VoiceTurnStage value) {
    if (_stage == value || _disposed) return;
    _stage = value;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    ++_operation;
    _recordingTimer?.cancel();
    _stageTimer?.cancel();
    unawaited(_voiceSession.dispose());
    super.dispose();
  }
}
