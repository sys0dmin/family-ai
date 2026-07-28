import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import '../../core/network/gateway_client.dart';
import '../agents/agent.dart';
import '../voice/voice_reply_cache.dart';
import 'conversation_gateway.dart';
import 'conversation_models.dart';

class ConversationController extends ChangeNotifier {
  ConversationController(this._agent, this._gateway, this._voiceReplyCache);

  final Agent _agent;
  final ConversationGateway _gateway;
  final VoiceReplyCache _voiceReplyCache;
  final List<ConversationMessage> _messages = [];
  Timer? _confirmationTimer;
  String? _conversationId;
  String? _error;
  bool _loading = true;
  bool _sendingText = false;
  bool _voiceBusy = false;
  bool _confirmNewConversation = false;

  UnmodifiableListView<ConversationMessage> get messages =>
      UnmodifiableListView(_messages);
  String? get conversationId => _conversationId;
  String? get error => _error;
  bool get loading => _loading;
  bool get sendingText => _sendingText;
  bool get voiceBusy => _voiceBusy;
  bool get busy => _loading || _sendingText || _voiceBusy;
  bool get confirmNewConversation => _confirmNewConversation;

  Future<void> loadHistory() async {
    try {
      final history = await _gateway.getLatestConversation(_agent.id);
      _conversationId = history.conversationId;
      _messages
        ..clear()
        ..addAll(history.messages);
    } on GatewayException catch (error) {
      _error = error.message;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> sendText(String text) async {
    final normalized = text.trim();
    if (normalized.isEmpty || busy) return;
    _sendingText = true;
    _error = null;
    _messages.add(
      ConversationMessage(
        id: 'local-${DateTime.now().microsecondsSinceEpoch}',
        role: 'child',
        content: normalized,
      ),
    );
    notifyListeners();
    try {
      final conversationId = await ensureConversation();
      final reply = await _gateway.sendTextTurn(conversationId, normalized);
      _messages.add(reply);
    } on GatewayException catch (error) {
      _error = error.message;
    } finally {
      _sendingText = false;
      notifyListeners();
    }
  }

  Future<void> sendImage({
    required Uint8List imageBytes,
    required String filename,
    required String contentType,
    required String question,
  }) async {
    if (busy || !_agent.supportsImageUpload) return;
    final normalized = question.trim().isEmpty
        ? 'Алиса, расскажи, что интересного видно на этой фотографии?'
        : question.trim();
    _sendingText = true;
    _error = null;
    _messages.add(
      ConversationMessage(
        id: 'local-image-${DateTime.now().microsecondsSinceEpoch}',
        role: 'child',
        content: '📷 $normalized',
      ),
    );
    notifyListeners();
    try {
      final conversationId = await ensureConversation();
      final reply = await _gateway.sendImageTurn(
        conversationId: conversationId,
        imageBytes: imageBytes,
        filename: filename,
        contentType: contentType,
        question: normalized,
      );
      _messages.add(reply);
    } on GatewayException catch (error) {
      _error = error.message;
    } finally {
      _sendingText = false;
      notifyListeners();
    }
  }

  Future<bool> requestNewConversation() async {
    if (busy) return false;
    if (!_confirmNewConversation) {
      _confirmNewConversation = true;
      notifyListeners();
      _confirmationTimer?.cancel();
      _confirmationTimer = Timer(const Duration(seconds: 4), () {
        _confirmNewConversation = false;
        notifyListeners();
      });
      return false;
    }

    _confirmationTimer?.cancel();
    _confirmNewConversation = false;
    _sendingText = true;
    _error = null;
    notifyListeners();
    try {
      final previousConversationId = _conversationId;
      _conversationId = await _gateway.createConversation(_agent.id);
      if (previousConversationId != null) {
        try {
          await _voiceReplyCache.clearConversation(previousConversationId);
        } catch (_) {
          // Cache cleanup must not prevent starting a new conversation.
        }
      }
      _messages.clear();
      return true;
    } on GatewayException catch (error) {
      _error = error.message;
      return false;
    } finally {
      _sendingText = false;
      notifyListeners();
    }
  }

  Future<String> ensureConversation() async {
    return _conversationId ??= await _gateway.createConversation(_agent.id);
  }

  void appendMessage(ConversationMessage message) {
    _messages.add(message);
    notifyListeners();
  }

  void setVoiceBusy(bool value) {
    if (_voiceBusy == value) return;
    _voiceBusy = value;
    notifyListeners();
  }

  void setError(String message) {
    _error = message;
    notifyListeners();
  }

  void clearError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _confirmationTimer?.cancel();
    super.dispose();
  }
}
