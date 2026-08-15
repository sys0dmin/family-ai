import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../../features/agents/agent.dart';
import '../../features/calibration/calibration_models.dart';
import '../../features/conversations/activity_models.dart';
import '../../features/conversations/conversation_models.dart';
import '../../features/conversations/conversation_gateway.dart';
import '../../features/voice/voice_session.dart';
import '../config/server_address.dart';

class GatewayException implements Exception {
  const GatewayException(this.message);

  final String message;

  @override
  String toString() => message;
}

class SpeechAudio {
  const SpeechAudio({required this.audioBytes, required this.contentType});

  final Uint8List audioBytes;
  final String contentType;
}

class GatewayClient implements ConversationGateway {
  static final Random _secureRandom = Random.secure();

  static String _newRequestId() {
    final bytes = List<int>.generate(16, (_) => _secureRandom.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes
        .map((value) => value.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  static Map<String, String> _traceHeaders({bool json = false}) => {
    'X-Request-ID': _newRequestId(),
    if (json) 'Content-Type': 'application/json',
  };
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

  @override
  Future<List<ActivitySummary>> getActivities(String agentId) async {
    final response = await _get(
      serverAddress.resolve(
        '/v1/activities',
        queryParameters: {'agent_id': agentId},
      ),
    );
    final items = _decodeObject(response)['items'];
    if (items is! List<dynamic>) {
      throw const GatewayException('Сервер вернул неверный список занятий.');
    }
    return items
        .map((item) => ActivitySummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  @override
  Future<ActivitySession?> getActivityState(String conversationId) async {
    final response = await _get(
      serverAddress.resolve('/v1/activities/conversations/$conversationId'),
    );
    final session = _decodeObject(response)['session'];
    return session == null
        ? null
        : ActivitySession.fromJson(session as Map<String, dynamic>);
  }

  @override
  Future<ActivityActionResult> startActivity(
    String conversationId,
    String activityId,
  ) async {
    final response = await _postJson(
      serverAddress.resolve(
        '/v1/activities/conversations/$conversationId/$activityId/start',
      ),
      const {},
    );
    return _decodeActivityAction(response);
  }

  @override
  Future<ActivityActionResult> stopActivity(
    String conversationId, {
    required bool leaveForConversation,
  }) async {
    final response = await _postJson(
      serverAddress.resolve(
        '/v1/activities/conversations/$conversationId/stop',
      ),
      {'leave_for_conversation': leaveForConversation},
    );
    return _decodeActivityAction(response);
  }

  ActivityActionResult _decodeActivityAction(http.Response response) {
    final body = _decodeObject(response);
    return ActivityActionResult(
      session: ActivitySession.fromJson(
        body['session'] as Map<String, dynamic>,
      ),
      message: ConversationMessage.fromJson(
        body['message'] as Map<String, dynamic>,
      ),
    );
  }

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

  Future<ActiveCalibration> getActiveCalibration() async {
    try {
      final response = await _httpClient
          .get(serverAddress.resolve('/v1/stt-calibration/active'))
          .timeout(timeout);
      if (response.statusCode == 404) {
        return const ActiveCalibration.inactive();
      }
      _requireSuccess(response);
      return ActiveCalibration.fromJson(_decodeObject(response));
    } catch (_) {
      return const ActiveCalibration.inactive();
    }
  }

  Future<SpeechAudio> getCalibrationPromptAudio({
    required String sessionId,
    required String promptId,
  }) async {
    final response = await _get(
      serverAddress.resolve(
        '/v1/stt-calibration/$sessionId/prompts/$promptId/audio',
      ),
    );
    return SpeechAudio(
      audioBytes: response.bodyBytes,
      contentType: response.headers['content-type'] ?? 'audio/wav',
    );
  }

  Future<void> uploadCalibrationSample({
    required String sessionId,
    required String promptId,
    required RecordedVoice recording,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      serverAddress.resolve('/v1/stt-calibration/$sessionId/samples/$promptId'),
    );
    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        recording.bytes,
        filename: recording.filename,
        contentType: MediaType.parse(recording.contentType),
      ),
    );
    try {
      final streamed = await _httpClient.send(request).timeout(voiceTimeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(voiceTimeout);
      _requireSuccess(response);
    } catch (error) {
      if (error is GatewayException) rethrow;
      throw const GatewayException('Не удалось отправить проверку речи.');
    }
  }

  Future<void> completeCalibration(String sessionId) async {
    await _postJson(
      serverAddress.resolve('/v1/stt-calibration/$sessionId/complete'),
      const {},
    );
  }

  @override
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

  @override
  Future<String> createConversation(String agentId) async {
    final response = await _postJson(
      serverAddress.resolve('/v1/conversations/'),
      {'agent_id': agentId},
    );
    final body = _decodeObject(response);
    return body['conversation_id'] as String;
  }

  @override
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

  @override
  Future<ConversationMessage> sendImageTurn({
    required String conversationId,
    required Uint8List imageBytes,
    required String filename,
    required String contentType,
    required String question,
  }) async {
    final request =
        http.MultipartRequest(
            'POST',
            serverAddress.resolve('/v1/vision/$conversationId/turn'),
          )
          ..headers.addAll(_traceHeaders())
          ..fields['question'] = question
          ..files.add(
            http.MultipartFile.fromBytes(
              'file',
              imageBytes,
              filename: filename,
              contentType: MediaType.parse(contentType),
            ),
          );
    try {
      final streamed = await _httpClient.send(request).timeout(voiceTimeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(voiceTimeout);
      if (response.statusCode == 413) {
        throw const GatewayException('Фотография получилась слишком большой.');
      }
      if (response.statusCode == 415 || response.statusCode == 422) {
        throw const GatewayException('Этот файл не похож на фотографию.');
      }
      _requireSuccess(response);
      return ConversationMessage.fromJson(_decodeObject(response));
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось отправить фотографию.');
    }
  }

  @override
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

  @override
  Future<VoiceTurnAudio> sendVoiceTurn({
    required String conversationId,
    required Uint8List audioBytes,
    required String filename,
    required String contentType,
    required Duration recordingDuration,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      serverAddress.resolve('/v1/voice/$conversationId/turn'),
    );
    request.headers.addAll(_traceHeaders());
    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        audioBytes,
        filename: filename,
        contentType: MediaType.parse(contentType),
      ),
    );
    request.fields['recording_duration_ms'] = recordingDuration.inMilliseconds
        .toString();

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
      return VoiceTurnAudio(
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

  @override
  Stream<VoiceStreamEvent> streamVoiceTurn({
    required String conversationId,
    required Uint8List audioBytes,
    required String filename,
    required String contentType,
    required Duration recordingDuration,
  }) async* {
    final request =
        http.MultipartRequest(
            'POST',
            serverAddress.resolve('/v1/voice/$conversationId/turn/stream'),
          )
          ..headers.addAll(_traceHeaders())
          ..fields['recording_duration_ms'] = recordingDuration.inMilliseconds
              .toString()
          ..files.add(
            http.MultipartFile.fromBytes(
              'file',
              audioBytes,
              filename: filename,
              contentType: MediaType.parse(contentType),
            ),
          );
    yield* _sendVoiceStream(
      request,
      fallbackMessage: 'Не удалось отправить голосовое сообщение.',
    );
  }

  @override
  Future<VoiceTurnAudio> sendSpokenImageTurn({
    required String conversationId,
    required Uint8List imageBytes,
    required String imageFilename,
    required String imageContentType,
    required Uint8List audioBytes,
    required String audioFilename,
    required String audioContentType,
    required Duration recordingDuration,
  }) async {
    final request =
        http.MultipartRequest(
            'POST',
            serverAddress.resolve('/v1/multimodal/$conversationId/turn'),
          )
          ..headers.addAll(_traceHeaders())
          ..fields['recording_duration_ms'] = recordingDuration.inMilliseconds
              .toString()
          ..files.add(
            http.MultipartFile.fromBytes(
              'image',
              imageBytes,
              filename: imageFilename,
              contentType: MediaType.parse(imageContentType),
            ),
          )
          ..files.add(
            http.MultipartFile.fromBytes(
              'audio',
              audioBytes,
              filename: audioFilename,
              contentType: MediaType.parse(audioContentType),
            ),
          );
    try {
      final streamedResponse = await _httpClient
          .send(request)
          .timeout(voiceTimeout);
      final response = await http.Response.fromStream(
        streamedResponse,
      ).timeout(voiceTimeout);
      if (response.statusCode == 403) {
        throw const GatewayException(
          'Этот персонаж пока не умеет рассматривать фотографии.',
        );
      }
      if (response.statusCode == 413) {
        throw const GatewayException(
          'Фотография или голосовое сообщение получились слишком большими.',
        );
      }
      if (response.statusCode == 415) {
        throw const GatewayException(
          'Телефон не смог подготовить фотографию или запись.',
        );
      }
      if (response.statusCode == 422) {
        throw const GatewayException(
          'Не удалось расслышать вопрос или рассмотреть фотографию.',
        );
      }
      if (response.statusCode == 503) {
        throw const GatewayException(
          'Сейчас я не могу рассмотреть фотографию. Попробуем позже.',
        );
      }
      if (response.statusCode == 502) {
        throw const GatewayException(
          'Не получилось подготовить ответ. Давай попробуем ещё раз.',
        );
      }
      _requireSuccess(response);
      if (response.bodyBytes.isEmpty) {
        throw const GatewayException('Сервер не вернул голосовой ответ.');
      }
      return VoiceTurnAudio(
        audioBytes: response.bodyBytes,
        contentType:
            response.headers['content-type'] ?? 'application/octet-stream',
        messageId: response.headers['x-family-ai-message-id'],
      );
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException(
        'Не удалось отправить фотографию и голосовой вопрос.',
      );
    }
  }

  @override
  Stream<VoiceStreamEvent> streamSpokenImageTurn({
    required String conversationId,
    required Uint8List imageBytes,
    required String imageFilename,
    required String imageContentType,
    required Uint8List audioBytes,
    required String audioFilename,
    required String audioContentType,
    required Duration recordingDuration,
  }) async* {
    final request =
        http.MultipartRequest(
            'POST',
            serverAddress.resolve('/v1/multimodal/$conversationId/turn/stream'),
          )
          ..headers.addAll(_traceHeaders())
          ..fields['recording_duration_ms'] = recordingDuration.inMilliseconds
              .toString()
          ..files.add(
            http.MultipartFile.fromBytes(
              'image',
              imageBytes,
              filename: imageFilename,
              contentType: MediaType.parse(imageContentType),
            ),
          )
          ..files.add(
            http.MultipartFile.fromBytes(
              'audio',
              audioBytes,
              filename: audioFilename,
              contentType: MediaType.parse(audioContentType),
            ),
          );
    yield* _sendVoiceStream(
      request,
      fallbackMessage: 'Не удалось отправить фотографию и голосовой вопрос.',
    );
  }

  @override
  Future<void> cancelVoiceStream(String turnId) async {
    try {
      await _httpClient
          .delete(serverAddress.resolve('/v1/voice/streams/$turnId'))
          .timeout(timeout);
    } catch (_) {
      // Cancellation is best effort; the local player already stopped.
    }
  }

  @override
  Future<void> reportVoicePlayback({
    required String turnId,
    required Duration duration,
  }) async {
    try {
      await _httpClient
          .post(
            serverAddress.resolve('/v1/voice/streams/$turnId/playback'),
            headers: _traceHeaders(json: true),
            body: jsonEncode({'duration_ms': duration.inMilliseconds}),
          )
          .timeout(timeout);
    } catch (_) {
      // Telemetry must never affect the conversation.
    }
  }

  @override
  Future<SynthesizedAudio> synthesizeText({
    required String conversationId,
    required String text,
  }) async {
    try {
      final response = await _httpClient
          .post(
            serverAddress.resolve('/v1/voice/$conversationId/synthesize'),
            headers: _traceHeaders(json: true),
            body: jsonEncode({'text': text}),
          )
          .timeout(voiceTimeout);
      _requireSuccess(response);
      if (response.bodyBytes.isEmpty) {
        throw const GatewayException('Сервер не вернул голосовой ответ.');
      }
      return SynthesizedAudio(
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

  @override
  Uri resolveMediaUrl(String contentUrl) {
    final uri = Uri.parse(contentUrl);
    return uri.hasScheme ? uri : serverAddress.uri.resolveUri(uri);
  }

  Stream<VoiceStreamEvent> _sendVoiceStream(
    http.MultipartRequest request, {
    required String fallbackMessage,
  }) async* {
    try {
      final response = await _httpClient.send(request).timeout(voiceTimeout);
      if (response.statusCode == 404 || response.statusCode == 405) {
        await response.stream.drain<void>();
        throw const VoiceStreamingUnavailable();
      }
      if (response.statusCode == 409) {
        await response.stream.drain<void>();
        throw const GatewayException(
          'Этот вопрос уже отправлен. Давай дождёмся ответа.',
        );
      }
      if (response.statusCode == 429) {
        await response.stream.drain<void>();
        throw const GatewayException(
          'Я сейчас отвечаю на другой вопрос. Подожди чуточку и попробуй ещё раз.',
        );
      }
      if (response.statusCode == 504) {
        await response.stream.drain<void>();
        throw const GatewayException(
          'Ответ не успел прийти. Давай немного подождём и попробуем ещё раз.',
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        await response.stream.drain<void>();
        throw GatewayException(
          'Сервер ответил с ошибкой ${response.statusCode}.',
        );
      }
      if (response.headers['x-family-ai-voice-protocol'] !=
          'family-ai-voice/2') {
        await response.stream.drain<void>();
        throw const VoiceStreamingUnavailable();
      }
      await for (final line
          in response.stream
              .timeout(voiceTimeout)
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (line.trim().isEmpty) continue;
        yield _decodeVoiceStreamEvent(line);
      }
    } on VoiceStreamingUnavailable {
      rethrow;
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw GatewayException(fallbackMessage);
    }
  }

  VoiceStreamEvent _decodeVoiceStreamEvent(String line) {
    try {
      final body = jsonDecode(line);
      if (body is! Map<String, dynamic> ||
          body['protocol'] != 'family-ai-voice/2') {
        throw const FormatException();
      }
      final type = switch (body['type']) {
        'started' => VoiceStreamEventType.started,
        'message' => VoiceStreamEventType.message,
        'audio' => VoiceStreamEventType.audio,
        'complete' => VoiceStreamEventType.complete,
        'error' => VoiceStreamEventType.error,
        _ => throw const FormatException(),
      };
      Uint8List? audioBytes;
      if (type == VoiceStreamEventType.audio) {
        audioBytes = base64Decode(body['audio_base64'] as String);
      }
      return VoiceStreamEvent(
        type: type,
        turnId: body['turn_id'] as String?,
        messageId: body['message_id'] as String?,
        audioBytes: audioBytes,
        contentType: body['content_type'] as String?,
        audioIndex: body['index'] as int?,
        chunkCount: body['chunk_count'] as int?,
        errorMessage: body['message'] as String?,
      );
    } catch (_) {
      throw const GatewayException('Сервер вернул непонятный голосовой поток.');
    }
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
          .post(uri, headers: _traceHeaders(json: true), body: jsonEncode(body))
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
    if (response.statusCode == 409) {
      throw const GatewayException(
        'Этот вопрос уже отправлен. Давай дождёмся ответа.',
      );
    }
    if (response.statusCode == 429) {
      throw const GatewayException(
        'Я сейчас отвечаю на другой вопрос. Подожди чуточку и попробуй ещё раз.',
      );
    }
    if (response.statusCode == 504) {
      throw const GatewayException(
        'Ответ не успел прийти. Давай немного подождём и попробуем ещё раз.',
      );
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
