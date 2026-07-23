import 'dart:convert';
import 'dart:typed_data';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('sends a WAV voice turn and reads the assistant message id', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/voice/conversation-1/turn');
        expect(
          request.headers['content-type'],
          contains('multipart/form-data'),
        );
        expect(request.bodyBytes, containsAllInOrder(<int>[82, 73, 70, 70]));
        return http.Response.bytes(
          <int>[1, 2, 3, 4],
          200,
          headers: {
            'content-type': 'audio/wav',
            'x-family-ai-message-id': 'message-2',
          },
        );
      }),
    );

    final response = await gateway.sendVoiceTurn(
      conversationId: 'conversation-1',
      audioBytes: Uint8List.fromList(<int>[82, 73, 70, 70]),
      filename: 'voice.wav',
      contentType: 'audio/wav',
    );

    expect(response.audioBytes, <int>[1, 2, 3, 4]);
    expect(response.contentType, 'audio/wav');
    expect(response.messageId, 'message-2');
  });

  test('synthesizes an existing assistant message', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/voice/conversation-1/synthesize');
        expect(jsonDecode(request.body), <String, dynamic>{
          'text': 'Привет, Лера!',
        });
        return http.Response.bytes(
          <int>[73, 68, 51],
          200,
          headers: {'content-type': 'audio/mpeg'},
        );
      }),
    );

    final response = await gateway.synthesizeText(
      conversationId: 'conversation-1',
      text: 'Привет, Лера!',
    );

    expect(response.audioBytes, <int>[73, 68, 51]);
    expect(response.contentType, 'audio/mpeg');
  });
}
