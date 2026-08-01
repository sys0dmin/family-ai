import 'dart:convert';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('loads and starts a configured activity', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        if (request.method == 'GET') {
          expect(request.url.queryParameters['agent_id'], 'tech_guide');
          return http.Response(
            jsonEncode({
              'schema_version': 1,
              'items': [
                {
                  'id': 'build_computer',
                  'version': 1,
                  'agent_id': 'tech_guide',
                  'title': 'Собираем компьютер',
                  'short_title': 'Компьютер',
                  'description': 'Выбираем детали',
                  'icon': '🖥️',
                  'color': '#3567C8',
                  'total_steps': 4,
                },
              ],
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        expect(request.url.path, contains('/build_computer/start'));
        return http.Response(
          jsonEncode({
            'session': {
              'id': 'session-1',
              'activity_id': 'build_computer',
              'title': 'Собираем компьютер',
              'icon': '🖥️',
              'color': '#3567C8',
              'status': 'active',
              'current_step': 0,
              'total_steps': 4,
              'current_step_title': 'Процессор',
              'current_step_icon': '🧠',
            },
            'message': {
              'id': 'message-1',
              'role': 'assistant',
              'content': 'Начинаем сборку!',
              'media': [],
            },
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final activities = await gateway.getActivities('tech_guide');
    final started = await gateway.startActivity(
      'conversation-1',
      activities.single.id,
    );

    expect(activities.single.icon, '🖥️');
    expect(started.session.currentStepTitle, 'Процессор');
    expect(started.message.content, 'Начинаем сборку!');
  });
}
