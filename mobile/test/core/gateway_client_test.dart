import 'dart:convert';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('health check accepts only Family AI Gateway', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('192.168.31.173:8000'),
      httpClient: MockClient((request) async {
        expect(request.url.path, '/healthz');
        expect(request.headers['X-Family-AI-App-Version'], 'development');
        expect(request.headers['X-Family-AI-App-Commit'], 'development');
        return http.Response(
          jsonEncode({'status': 'ok', 'service': 'ai-gateway'}),
          200,
        );
      }),
    );

    await expectLater(gateway.checkHealth(), completes);
  });

  test('loads child-safe agent manifest', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'tech_guide',
                'display_name': 'Байтик',
                'description': 'Объясняет ИТ',
                'icon': '🦝',
                'color': 'navy',
                'greeting': 'Привет!',
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final agents = await gateway.getAgents();

    expect(agents.single.id, 'tech_guide');
    expect(agents.single.displayName, 'Байтик');
  });

  test('loads only the selected agent conversation', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        expect(request.url.queryParameters['agent_id'], 'outdoor_guide');
        return http.Response(
          jsonEncode({
            'conversation_id': 'conversation-1',
            'agent_id': 'outdoor_guide',
            'messages': [
              {
                'id': 'message-1',
                'conversation_id': 'conversation-1',
                'role': 'assistant',
                'content': 'Пойдём в поход с родителями!',
                'created_at': '2026-07-19T12:00:00Z',
                'media': [],
              },
            ],
            'history_truncated': false,
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final history = await gateway.getLatestConversation('outdoor_guide');

    expect(history.conversationId, 'conversation-1');
    expect(history.messages.single.content, 'Пойдём в поход с родителями!');
  });
}
