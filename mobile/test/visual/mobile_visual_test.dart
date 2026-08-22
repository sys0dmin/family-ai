import 'dart:convert';
import 'dart:io';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:family_ai_mobile/features/agents/agent.dart';
import 'package:family_ai_mobile/features/agents/agent_chooser_screen.dart';
import 'package:family_ai_mobile/features/conversations/chat_screen.dart';
import 'package:family_ai_mobile/features/voice/voice_reply_cache.dart';
import 'package:family_ai_mobile/features/voice/voice_session.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _serverAddress = 'http://server.local';
const _agent = Agent(
  id: 'tech_guide',
  displayName: 'Байтик',
  description: 'Объясняет компьютеры, серверы и работу папы.',
  icon: '🦝',
  color: 'navy',
  greeting:
      'Хочешь заглянуть внутрь компьютерного мира и узнать, как папа создаёт '
      'надёжные серверы, облака и умные программы?',
  supportsImageUpload: true,
  supportsSpokenImageQuestion: true,
  imageUploadMaxBytes: 10 * 1024 * 1024,
);
const _alice = Agent(
  id: 'space_guide',
  displayName: 'Алиса Селезнёва',
  description: 'Рассказывает о космосе и ведёт межпланетные приключения.',
  icon: '🚀',
  color: 'cosmos',
  greeting: 'Полетели к звёздам!',
  supportsImageUpload: true,
  supportsSpokenImageQuestion: true,
  imageUploadMaxBytes: 10 * 1024 * 1024,
);

class _VisualVoiceSession implements VoiceSession {
  @override
  Future<void> cancelRecording() async {}

  @override
  Future<void> dispose() async {}

  @override
  Future<void> play(
    Uint8List audioBytes, {
    required String contentType,
    void Function()? onStarted,
  }) async {
    onStarted?.call();
  }

  @override
  Future<void> startRecording() async {}

  @override
  Future<RecordedVoice> stopRecording() async =>
      RecordedVoice(bytes: Uint8List(0), duration: Duration.zero);

  @override
  Future<void> stopPlayback() async {}
}

class _VisualReplyCache implements VoiceReplyCache {
  @override
  Future<void> clearConversation(String conversationId) async {}

  @override
  Future<CachedVoiceReply?> read({
    required String conversationId,
    required String messageId,
  }) async => null;

  @override
  Future<void> write({
    required String conversationId,
    required String messageId,
    required Uint8List bytes,
    required String contentType,
  }) async {}
}

ThemeData _theme() => ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: const Color(0xFF356FC0),
    surface: const Color(0xFFFFFDF8),
  ),
  scaffoldBackgroundColor: const Color(0xFFFFFDF8),
  fontFamily: 'VisualRoboto',
  inputDecorationTheme: const InputDecorationTheme(
    filled: true,
    fillColor: Colors.white,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.all(Radius.circular(20)),
      borderSide: BorderSide.none,
    ),
  ),
);

GatewayClient _gateway({bool includeAgents = false}) {
  return GatewayClient(
    serverAddress: ServerAddress.parse(_serverAddress),
    httpClient: MockClient((request) async {
      if (request.url.path == '/v1/agents' && includeAgents) {
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'teacher_friend',
                'display_name': 'Учитель-друг',
                'description': 'Самый умный друг и учитель.',
                'icon': 'У',
                'color': 'blue',
                'greeting': 'Что интересного узнаем?',
              },
              {
                'id': 'outdoor_guide',
                'display_name': 'Мурка',
                'description': 'Походница и гид по природе.',
                'icon': 'М',
                'color': 'forest',
                'greeting': 'Идём изучать природу!',
              },
              {
                'id': 'tech_guide',
                'display_name': 'Байтик',
                'description': 'Папин проводник в мир ИТ.',
                'icon': 'Б',
                'color': 'navy',
                'greeting': 'Заглянем внутрь компьютера?',
              },
              {
                'id': 'space_guide',
                'display_name': 'Алиса',
                'description': 'Путешественница по планетам.',
                'icon': 'А',
                'color': 'cosmos',
                'greeting': 'Полетели к звёздам!',
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }
      if (request.url.path == '/v1/activities') {
        return http.Response(jsonEncode({'items': <Object>[]}), 200);
      }
      if (request.url.path == '/v1/conversations/latest') {
        return http.Response(
          jsonEncode({
            'conversation_id': null,
            'agent_id': 'tech_guide',
            'messages': <Object>[],
            'history_truncated': false,
          }),
          200,
        );
      }
      return http.Response('not found', 404);
    }),
  );
}

Future<void> _loadVisualFont() async {
  var directory = File(Platform.resolvedExecutable).parent;
  File? font;
  for (var level = 0; level < 8; level += 1) {
    final candidate = File(
      '${directory.path}/bin/cache/artifacts/material_fonts/roboto-regular.ttf',
    );
    if (candidate.existsSync()) {
      font = candidate;
      break;
    }
    directory = directory.parent;
  }
  if (font == null) {
    throw StateError('Flutter Roboto test font was not found');
  }
  final bytes = font.readAsBytesSync();
  await (FontLoader(
    'VisualRoboto',
  )..addFont(Future.value(ByteData.sublistView(bytes)))).load();
}

Future<void> _configureViewport(
  WidgetTester tester,
  Size size, {
  double keyboardHeight = 0,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  tester.view.viewInsets = FakeViewPadding(bottom: keyboardHeight);
  addTearDown(tester.view.reset);
}

Future<void> _pumpChat(WidgetTester tester, {Agent agent = _agent}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: _theme(),
      home: ChatScreen(
        agent: agent,
        gateway: _gateway(),
        voiceSession: _VisualVoiceSession(),
        voiceReplyCache: _VisualReplyCache(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull);
}

void main() {
  setUpAll(_loadVisualFont);

  testWidgets('agent chooser portrait visual baseline', (tester) async {
    await _configureViewport(tester, const Size(430, 900));
    await tester.pumpWidget(
      MaterialApp(
        theme: _theme(),
        home: AgentChooserScreen(
          gateway: _gateway(includeAgents: true),
          serverAddress: ServerAddress.parse(_serverAddress),
          onChangeServer: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Учитель-друг'), findsOneWidget);

    await expectLater(
      find.byType(Scaffold),
      matchesGoldenFile('goldens/agent-chooser-portrait.png'),
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('chat portrait visual baseline', (tester) async {
    await _configureViewport(tester, const Size(430, 900));
    await _pumpChat(tester);

    await expectLater(
      find.byType(Scaffold),
      matchesGoldenFile('goldens/chat-portrait.png'),
    );
  });

  testWidgets('Alice app bar avatar visual baseline', (tester) async {
    await _configureViewport(tester, const Size(430, 900));
    await _pumpChat(tester, agent: _alice);

    await expectLater(
      find.byType(CircleAvatar),
      matchesGoldenFile('goldens/alice-chat-avatar.png'),
    );
  });

  testWidgets('chat portrait keyboard visual baseline', (tester) async {
    await _configureViewport(tester, const Size(430, 900), keyboardHeight: 400);
    await _pumpChat(tester);

    await expectLater(
      find.byType(Scaffold),
      matchesGoldenFile('goldens/chat-portrait-keyboard.png'),
    );
  });

  testWidgets('chat landscape visual baseline', (tester) async {
    await _configureViewport(tester, const Size(844, 390));
    await _pumpChat(tester);

    await expectLater(
      find.byType(Scaffold),
      matchesGoldenFile('goldens/chat-landscape.png'),
    );
  });

  testWidgets('chat landscape keyboard visual baseline', (tester) async {
    await _configureViewport(tester, const Size(844, 390), keyboardHeight: 260);
    await _pumpChat(tester);

    await expectLater(
      find.byType(Scaffold),
      matchesGoldenFile('goldens/chat-landscape-keyboard.png'),
    );
  });
}
