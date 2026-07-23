import 'dart:convert';
import 'dart:typed_data';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:family_ai_mobile/features/agents/agent.dart';
import 'package:family_ai_mobile/features/conversations/chat_screen.dart';
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

class _FakeVoiceSession implements VoiceSession {
  int starts = 0;
  int stops = 0;
  int plays = 0;
  Uint8List? playedBytes;
  String? playedContentType;

  @override
  Future<void> startRecording() async {
    starts += 1;
  }

  @override
  Future<RecordedVoice> stopRecording() async {
    stops += 1;
    return RecordedVoice(bytes: Uint8List.fromList(<int>[82, 73, 70, 70]));
  }

  @override
  Future<void> play(Uint8List audioBytes, {required String contentType}) async {
    plays += 1;
    playedBytes = audioBytes;
    playedContentType = contentType;
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
}
