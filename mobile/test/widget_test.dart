import 'dart:convert';

import 'package:family_ai_mobile/app.dart';
import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/storage/server_address_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class MemoryServerAddressStore implements ServerAddressStore {
  ServerAddress? value;

  @override
  Future<ServerAddress?> load() async => value;

  @override
  Future<void> save(ServerAddress address) async => value = address;
}

void main() {
  testWidgets('validates and saves a manually entered Gateway address', (
    tester,
  ) async {
    final store = MemoryServerAddressStore();
    final client = MockClient((request) async {
      if (request.url.path == '/healthz') {
        return http.Response(
          jsonEncode({'status': 'ok', 'service': 'ai-gateway'}),
          200,
        );
      }
      if (request.url.path == '/v1/agents') {
        return http.Response(jsonEncode({'items': []}), 200);
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      FamilyAiApp(serverAddressStore: store, httpClient: client),
    );
    await tester.pumpAndSettle();

    expect(find.text('Где живёт Family AI?'), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('server-address-field')),
      '192.168.31.173:8000',
    );
    await tester.tap(find.byKey(const Key('connect-button')));
    await tester.pumpAndSettle();

    expect(store.value?.value, 'http://192.168.31.173:8000');
    expect(find.text('Клуб любопытных'), findsOneWidget);
  });
}
