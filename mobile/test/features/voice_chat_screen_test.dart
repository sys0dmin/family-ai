import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:family_ai_mobile/features/agents/agent.dart';
import 'package:family_ai_mobile/features/conversations/chat_screen.dart';
import 'package:family_ai_mobile/features/conversations/photo_picker.dart';
import 'package:family_ai_mobile/features/voice/voice_reply_cache.dart';
import 'package:family_ai_mobile/features/voice/voice_session.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _agent = Agent(
  id: 'teacher',
  displayName: 'Teacher',
  description: 'Friend',
  icon: 'bear',
  color: 'blue',
  greeting: 'Hello',
);

const _visionAgent = Agent(
  id: 'teacher',
  displayName: 'Teacher',
  description: 'Friend',
  icon: 'bear',
  color: 'blue',
  greeting: 'Hello',
  supportsImageUpload: true,
  supportsSpokenImageQuestion: true,
  imageUploadMaxBytes: 10 * 1024 * 1024,
);

class _FakeVoiceSession implements VoiceSession {
  int starts = 0;
  int stops = 0;
  int plays = 0;
  Uint8List? playedBytes;
  String? playedContentType;
  Completer<void>? playGate;

  @override
  Future<void> startRecording() async {
    starts += 1;
  }

  @override
  Future<RecordedVoice> stopRecording() async {
    stops += 1;
    return RecordedVoice(
      bytes: Uint8List.fromList(<int>[82, 73, 70, 70]),
      duration: const Duration(milliseconds: 1250),
    );
  }

  @override
  Future<void> play(Uint8List audioBytes, {required String contentType}) async {
    plays += 1;
    playedBytes = audioBytes;
    playedContentType = contentType;
    await playGate?.future;
  }

  @override
  Future<void> cancelRecording() async {}

  @override
  Future<void> dispose() async {}

  @override
  Future<void> stopPlayback() async {}
}

class _FakeVoiceReplyCache implements VoiceReplyCache {
  final Map<String, CachedVoiceReply> entries = {};
  final List<String> clearedConversations = [];

  String _key(String conversationId, String messageId) {
    return '$conversationId/$messageId';
  }

  @override
  Future<CachedVoiceReply?> read({
    required String conversationId,
    required String messageId,
  }) async {
    return entries[_key(conversationId, messageId)];
  }

  @override
  Future<void> write({
    required String conversationId,
    required String messageId,
    required Uint8List bytes,
    required String contentType,
  }) async {
    entries[_key(conversationId, messageId)] = CachedVoiceReply(
      bytes: bytes,
      contentType: contentType,
    );
  }

  @override
  Future<void> clearConversation(String conversationId) async {
    clearedConversations.add(conversationId);
    entries.removeWhere((key, _) => key.startsWith('$conversationId/'));
  }
}

class _FakePhotoPicker implements PhotoPicker {
  PhotoSource? source;

  @override
  Future<PickedPhoto?> pick(PhotoSource source, {required int maxBytes}) async {
    this.source = source;
    return PickedPhoto(
      bytes: base64Decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
        'YAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
      ),
      filename: 'photo.png',
      contentType: 'image/png',
    );
  }
}

GatewayClient _voiceGateway({VoidCallback? onMessageFetched}) {
  return GatewayClient(
    serverAddress: ServerAddress.parse('http://server.local'),
    httpClient: MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path == '/v1/conversations/latest') {
        return http.Response(
          jsonEncode({
            'conversation_id': null,
            'agent_id': 'teacher',
            'messages': <Object>[],
            'history_truncated': false,
          }),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/conversations/') {
        return http.Response(
          jsonEncode({'conversation_id': 'conversation-1'}),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/voice/conversation-1/turn') {
        return http.Response.bytes(
          <int>[10, 20, 30],
          200,
          headers: {
            'content-type': 'audio/wav',
            'x-family-ai-message-id': 'message-2',
          },
        );
      }
      if (request.method == 'GET' &&
          request.url.path ==
              '/v1/conversations/conversation-1/messages/message-2') {
        onMessageFetched?.call();
        return http.Response(
          jsonEncode({
            'id': 'message-2',
            'role': 'assistant',
            'content':
                '\u041f\u0440\u0438\u0432\u0435\u0442, '
                '\u041b\u0435\u0440\u0430!',
            'media': <Object>[],
          }),
          200,
        );
      }
      return http.Response('Not found', 404);
    }),
  );
}

GatewayClient _historyGateway({required VoidCallback onSynthesize}) {
  return GatewayClient(
    serverAddress: ServerAddress.parse('http://server.local'),
    httpClient: MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path == '/v1/conversations/latest') {
        return http.Response(
          jsonEncode({
            'conversation_id': 'conversation-1',
            'agent_id': 'teacher',
            'messages': [
              {
                'id': 'old-message',
                'role': 'assistant',
                'content': 'Old answer',
                'media': <Object>[],
              },
            ],
            'history_truncated': false,
          }),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/voice/conversation-1/synthesize') {
        onSynthesize();
        return http.Response.bytes(
          <int>[73, 68, 51, 1],
          200,
          headers: {'content-type': 'audio/mpeg'},
        );
      }
      return http.Response('Not found', 404);
    }),
  );
}

GatewayClient _multimodalGateway({
  required ValueChanged<http.Request> onTurn,
  required VoidCallback onMessageFetched,
}) {
  return GatewayClient(
    serverAddress: ServerAddress.parse('http://server.local'),
    httpClient: MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path == '/v1/conversations/latest') {
        return http.Response(
          jsonEncode({
            'conversation_id': null,
            'agent_id': 'teacher',
            'messages': <Object>[],
            'history_truncated': false,
          }),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/conversations/') {
        return http.Response(
          jsonEncode({'conversation_id': 'conversation-1'}),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/multimodal/conversation-1/turn') {
        onTurn(request);
        return http.Response.bytes(
          <int>[30, 40, 50],
          200,
          headers: {
            'content-type': 'audio/wav',
            'x-family-ai-message-id': 'multimodal-message',
          },
        );
      }
      if (request.method == 'GET' &&
          request.url.path ==
              '/v1/conversations/conversation-1/messages/multimodal-message') {
        onMessageFetched();
        return http.Response(
          jsonEncode({
            'id': 'multimodal-message',
            'role': 'assistant',
            'content': 'Я рассмотрел фотографию.',
            'media': <Object>[],
          }),
          200,
        );
      }
      return http.Response('Not found', 404);
    }),
  );
}

GatewayClient _pendingVoiceGateway(Completer<http.Response> voiceResponse) {
  return GatewayClient(
    serverAddress: ServerAddress.parse('http://server.local'),
    httpClient: MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path == '/v1/conversations/latest') {
        return http.Response(
          jsonEncode({
            'conversation_id': null,
            'agent_id': 'teacher',
            'messages': <Object>[],
            'history_truncated': false,
          }),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/conversations/') {
        return http.Response(
          jsonEncode({'conversation_id': 'conversation-1'}),
          200,
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/v1/voice/conversation-1/turn') {
        return voiceResponse.future;
      }
      return http.Response('Not found', 404);
    }),
  );
}

void main() {
  testWidgets('records, sends and plays a voice turn', (tester) async {
    final voice = _FakeVoiceSession();
    final cache = _FakeVoiceReplyCache();
    var messageFetched = false;
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          agent: _agent,
          gateway: _voiceGateway(onMessageFetched: () => messageFetched = true),
          voiceSession: voice,
          voiceReplyCache: cache,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('voice-button')));
    await tester.pump();

    expect(voice.starts, 1);
    expect(find.byIcon(Icons.stop_rounded), findsOneWidget);

    await tester.tap(find.byKey(const Key('voice-button')));
    await tester.pumpAndSettle();

    expect(voice.stops, 1);
    expect(voice.playedBytes, <int>[10, 20, 30]);
    expect(voice.playedContentType, 'audio/wav');
    expect(messageFetched, isTrue);
    expect(cache.entries, hasLength(1));

    await tester.tap(find.byKey(const Key('replay-message-2')));
    await tester.pumpAndSettle();

    expect(voice.plays, 2);
  });

  testWidgets('synthesizes and caches an old reply on first replay', (
    tester,
  ) async {
    final voice = _FakeVoiceSession();
    final cache = _FakeVoiceReplyCache();
    var synthesizeCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          agent: _agent,
          gateway: _historyGateway(onSynthesize: () => synthesizeCalls += 1),
          voiceSession: voice,
          voiceReplyCache: cache,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('replay-old-message')));
    await tester.pumpAndSettle();

    expect(synthesizeCalls, 1);
    expect(voice.plays, 1);
    expect(cache.entries, hasLength(1));
  });

  testWidgets('shows voice stages and ignores a cancelled pending reply', (
    tester,
  ) async {
    final voice = _FakeVoiceSession();
    final response = Completer<http.Response>();
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          agent: _agent,
          gateway: _pendingVoiceGateway(response),
          voiceSession: voice,
          voiceReplyCache: _FakeVoiceReplyCache(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('voice-button')));
    await tester.pump();
    expect(find.text('Слушаю…'), findsOneWidget);

    await tester.tap(find.byKey(const Key('voice-button')));
    await tester.pump();
    expect(find.text('Понимаю…'), findsOneWidget);
    expect(find.byKey(const Key('cancel-voice-turn')), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Думаю…'), findsOneWidget);

    await tester.tap(find.byKey(const Key('cancel-voice-turn')));
    await tester.pump();
    expect(find.byKey(const Key('cancel-voice-turn')), findsNothing);

    response.complete(
      http.Response.bytes(
        <int>[10, 20, 30],
        200,
        headers: {
          'content-type': 'audio/wav',
          'x-family-ai-message-id': 'cancelled-message',
        },
      ),
    );
    await tester.pumpAndSettle();

    expect(voice.plays, 0);
    expect(find.byKey(const Key('replay-cancelled-message')), findsNothing);
  });

  testWidgets('shows the speaking stage while audio is playing', (
    tester,
  ) async {
    final voice = _FakeVoiceSession()..playGate = Completer<void>();
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          agent: _agent,
          gateway: _voiceGateway(),
          voiceSession: voice,
          voiceReplyCache: _FakeVoiceReplyCache(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('voice-button')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('voice-button')));
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pump();

    expect(find.text('Отвечаю…'), findsOneWidget);
    expect(find.byKey(const Key('cancel-voice-turn')), findsOneWidget);

    voice.playGate!.complete();
    await tester.pumpAndSettle();
    expect(find.text('Напиши сообщение…'), findsOneWidget);
  });

  testWidgets(
    'chooses camera, records a question, and sends one spoken image turn',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final voice = _FakeVoiceSession();
      final photoPicker = _FakePhotoPicker();
      var multimodalTurns = 0;
      var messageFetches = 0;
      http.Request? multimodalRequest;
      await tester.pumpWidget(
        MaterialApp(
          home: ChatScreen(
            agent: _visionAgent,
            gateway: _multimodalGateway(
              onTurn: (request) {
                multimodalTurns += 1;
                multimodalRequest = request;
              },
              onMessageFetched: () => messageFetches += 1,
            ),
            voiceSession: voice,
            voiceReplyCache: _FakeVoiceReplyCache(),
            photoPicker: photoPicker,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('photo-button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('photo-source-camera')), findsOneWidget);

      await tester.tap(find.byKey(const Key('photo-source-camera')));
      await tester.pump();
      expect(photoPicker.source, PhotoSource.camera);
      expect(voice.starts, 1);
      expect(find.byKey(const Key('pending-photo-preview')), findsOneWidget);
      expect(find.text('Слушаю…'), findsOneWidget);

      await tester.tap(find.byKey(const Key('voice-button')));
      await tester.pumpAndSettle();

      expect(multimodalTurns, 1);
      expect(messageFetches, 1);
      expect(
        multimodalRequest!.headers['content-type'],
        startsWith('multipart/form-data; boundary='),
      );
      final requestBody = utf8.decode(
        multimodalRequest!.bodyBytes,
        allowMalformed: true,
      );
      expect(requestBody, contains('name="recording_duration_ms"'));
      expect(requestBody, contains('1250'));
      expect(requestBody, contains('name="image"; filename="photo.png"'));
      expect(requestBody.toLowerCase(), contains('content-type: image/png'));
      expect(
        requestBody,
        contains('name="audio"; filename="lera-voice.wav"'),
      );
      expect(requestBody.toLowerCase(), contains('content-type: audio/wav'));
      expect(voice.stops, 1);
      expect(voice.playedBytes, <int>[30, 40, 50]);
      expect(find.byKey(const Key('pending-photo-preview')), findsNothing);
    },
  );
}
