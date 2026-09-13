import 'dart:convert';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('loads clinic catalog and decodes a deterministic action', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        if (request.method == 'GET') {
          return http.Response(
            jsonEncode({
              'schema_version': 1,
              'items': [
                {
                  'id': 'teddy_after_walk',
                  'version': 1,
                  'title': 'Осмотр после прогулки',
                  'short_title': 'Мишка устал',
                  'description': 'Поможем мишке',
                  'patient_name': 'Мишка Топа',
                  'patient_icon': '🧸',
                  'color': '#45B7A8',
                },
              ],
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        expect(request.url.path, contains('/actions/give_water'));
        return http.Response(
          jsonEncode({
            'session': _sessionJson(),
            'message': {
              'id': 'message-1',
              'role': 'assistant',
              'content': 'Мишка попил воды.',
              'media': [],
            },
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final cases = await gateway.getClinicCases();
    final result = await gateway.performClinicAction(
      'conversation-1',
      'give_water',
    );

    expect(cases.single.patientName, 'Мишка Топа');
    expect(result.session.vitals.single.value, '88');
    expect(result.messageId, 'message-1');
  });
}

Map<String, Object> _sessionJson() => {
  'id': 'session-1',
  'case_id': 'teddy_after_walk',
  'title': 'Осмотр после прогулки',
  'patient_name': 'Мишка Топа',
  'patient_icon': '🧸',
  'color': '#45B7A8',
  'status': 'active',
  'vitals': [
    {
      'id': 'heart',
      'icon': '💚',
      'label': 'Сердце',
      'value': '88',
      'unit': 'уд/мин',
      'state': 'calm',
    },
  ],
  'actions': [
    {'id': 'give_water', 'icon': '🥤', 'label': 'Дать воду', 'completed': true},
  ],
};
