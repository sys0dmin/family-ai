import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../../features/agents/agent.dart';
import '../../features/conversations/conversation_models.dart';
import '../config/server_address.dart';

class GatewayException implements Exception {
  const GatewayException(this.message);

  final String message;

  @override
  String toString() => message;
}

class VoiceTurnResponse {
  const VoiceTurnResponse({
    required this.audioBytes,
    required this.contentType,
    required this.messageId,
  });

  final Uint8List audioBytes;
  final String contentType;
  final String? messageId;
}

class SpeechAudio {
  const SpeechAudio({required this.audioBytes, required this.contentType});

  final Uint8List audioBytes;
  final String contentType;
}

class GatewayClient {
  factory GatewayClient({
    required ServerAddress serverAddress,
    required http.Client httpClient,
    Duration timeout = const Duration(seconds: 10),
    Duration voiceTimeout = const Duration(seconds: 90),
  }) {
    return GatewayClient._(serverAddress, httpClient, timeout, voiceTimeout);
  }

  GatewayClient._(
    this.serverAddress,
    this._httpClient,
    this.timeout,
    this.voiceTimeout,
  );

  final ServerAddress serverAddress;
  final http.Client _httpClient;
  final Duration timeout;
  final Duration voiceTimeout;

  Future<void> checkHealth() async {
    final response = await _get(serverAddress.resolve('/healthz'));
    final body = _decodeObject(response);
    if (body['status'] != 'ok' || body['service'] != 'ai-gateway') {
      throw const GatewayException('По этому адресу нет Family AI Gateway.');
    }
  }

  Future<List<Agent>> getAgents() async {
    final response = await _get(serverAddress.resolve('/v1/agents'));
    final body = _decodeObject(response);
    final items = body['items'];
    if (items is! List<dynamic>) {
      throw const GatewayException('Сервер вернул неверный список друзей.');
    }
    return items
        .map((item) => Agent.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<ConversationHistory> getLatestConversation(String agentId) async {
    final response = await _get(
      serverAddress.resolve(
        '/v1/conversations/latest',
        queryParameters: {'agent_id': agentId},
      ),
    );
    final body = _decodeObject(response);
    final messages = body['messages'];
    if (messages is! List<dynamic>) {
      throw const GatewayException('Сервер вернул неверную историю разговора.');
    }
    return ConversationHistory(
      conversationId: body['conversation_id'] as String?,
      messages: messages
          .map(
            (item) =>
                ConversationMessage.fromJson(item as Map<String, dynamic>),
          )
          .toList(growable: false),
      isTruncated: body['history_truncated'] as bool? ?? false,
    );
  }

  Future<String> createConversation(String agentId) async {
    final response = await _postJson(
      serverAddress.resolve('/v1/conversations/'),
      {'agent_id': agentId},
    );
    final body = _decodeObject(response);
    return body['conversation_id'] as String;
  }

  Future<ConversationMessage> sendTextTurn(
    String conversationId,
    String text,
  ) async {
    final response = await _postJson(
      serverAddress.resolve('/v1/conversations/$conversationId/turn'),
      {'role': 'child', 'content': text},
    );
    return ConversationMessage.fromJson(_decodeObject(response));
  }

  Future<ConversationMessage> getMessage(
    String conversationId,
    String messageId,
  ) async {
    final response = await _get(
      serverAddress.resolve(
        '/v1/conversations/$conversationId/messages/$messageId',
      ),
    );
    return ConversationMessage.fromJson(_decodeObject(response));
  }

  Future<VoiceTurnResponse> sendVoiceTurn({
    required String conversationId,
    required Uint8List audioBytes,
    required String filename,
    required String contentType,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      serverAddress.resolve('/v1/voice/$conversationId/turn'),
    );
    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        audioBytes,
        filename: filename,
        contentType: MediaType.parse(contentType),
      ),
    );

    try {
      final streamedResponse = await _httpClient
          .send(request)
          .timeout(voiceTimeout);
      final response = await http.Response.fromStream(
        streamedResponse,
      ).timeout(voiceTimeout);
      if (response.statusCode == 413) {
        throw const GatewayException(
          'Голосовое сообщение получилось слишком длинным.',
        );
      }
      if (response.statusCode == 422) {
        throw const GatewayException(
          'Не удалось расслышать голос. Попробуй ещё раз.',
        );
      }
      _requireSuccess(response);
      if (response.bodyBytes.isEmpty) {
        throw const GatewayException('Сервер не вернул голосовой ответ.');
      }
      return VoiceTurnResponse(
        audioBytes: response.bodyBytes,
        contentType:
            response.headers['content-type'] ?? 'application/octet-stream',
        messageId: response.headers['x-family-ai-message-id'],
      );
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось отправить голосовое сообщение.');
    }
  }

  Future<SpeechAudio> synthesizeText({
    required String conversationId,
    required String text,
  }) async {
    try {
      final response = await _httpClient
          .post(
            serverAddress.resolve('/v1/voice/$conversationId/synthesize'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'text': text}),
          )
          .timeout(voiceTimeout);
      _requireSuccess(response);
      if (response.bodyBytes.isEmpty) {
        throw const GatewayException('Сервер не вернул голосовой ответ.');
      }
      return SpeechAudio(
        audioBytes: response.bodyBytes,
        contentType:
            response.headers['content-type'] ?? 'application/octet-stream',
      );
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось снова озвучить ответ.');
    }
  }

  Uri resolveMediaUrl(String contentUrl) {
    final uri = Uri.parse(contentUrl);
    return uri.hasScheme ? uri : serverAddress.uri.resolveUri(uri);
  }

  Future<http.Response> _get(Uri uri) async {
    try {
      final response = await _httpClient.get(uri).timeout(timeout);
      return _requireSuccess(response);
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось связаться с сервером.');
    }
  }

  Future<http.Response> _postJson(Uri uri, Map<String, dynamic> body) async {
    try {
      final response = await _httpClient
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(timeout);
      return _requireSuccess(response);
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось связаться с сервером.');
    }
  }

  http.Response _requireSuccess(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response;
    }
    throw GatewayException('Сервер ответил с ошибкой ${response.statusCode}.');
  }

  Map<String, dynamic> _decodeObject(http.Response response) {
    try {
      final value = jsonDecode(utf8.decode(response.bodyBytes));
      if (value is Map<String, dynamic>) return value;
    } catch (_) {
      // The caller receives a stable error without leaking response details.
    }
    throw const GatewayException('Сервер вернул непонятный ответ.');
  }
}
