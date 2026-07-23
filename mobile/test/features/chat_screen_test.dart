import 'dart:convert';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:family_ai_mobile/features/agents/agent.dart';
import 'package:family_ai_mobile/features/conversations/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _agent = Agent(
  id: 'tech_guide',
  displayName: 'Байтик',
  description: 'Объясняет ИТ',
  icon: '🦝',
  color: 'navy',
  greeting:
      'Хочешь заглянуть внутрь компьютерного мира и узнать, как папа создаёт '
      'надёжные серверы, облака и умные программы?',
);

GatewayClient _emptyHistoryGateway() {
  return GatewayClient(
    serverAddress: ServerAddress.parse('http://server.local'),
    httpClient: MockClient((request) async {
      return http.Response(
        jsonEncode({
          'conversation_id': null,
          'agent_id': 'tech_guide',
          'messages': [],
          'history_truncated': false,
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }),
  );
}

Future<void> _pumpChat(WidgetTester tester) async {
  await tester.pumpWidget(
    MaterialApp(
      home: ChatScreen(agent: _agent, gateway: _emptyHistoryGateway()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('empty chat fits a short landscape viewport', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(844, 390);
    addTearDown(tester.view.reset);

    await _pumpChat(tester);

    expect(tester.takeException(), isNull);
    expect(find.text('Байтик'), findsOneWidget);
  });

  testWidgets('empty chat fits when the software keyboard is visible', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(430, 900);
    tester.view.viewInsets = const FakeViewPadding(bottom: 400);
    addTearDown(tester.view.reset);

    await _pumpChat(tester);

    expect(tester.takeException(), isNull);
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('composer fits landscape with the software keyboard visible', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(844, 390);
    tester.view.viewInsets = const FakeViewPadding(bottom: 260);
    addTearDown(tester.view.reset);

    await _pumpChat(tester);

    expect(tester.takeException(), isNull);
    expect(find.byType(AppBar), findsNothing);
    expect(find.byType(TextField), findsOneWidget);
  });
}
