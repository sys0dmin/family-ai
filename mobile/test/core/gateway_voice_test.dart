import 'dart:convert';
import 'dart:typed_data';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:family_ai_mobile/features/voice/voice_session.dart';
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
        expect(utf8.decode(request.bodyBytes), contains('1250'));
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
      recordingDuration: const Duration(milliseconds: 1250),
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

  test('discovers and uploads a parent-armed calibration sample', () async {
    var activeChecks = 0;
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/v1/stt-calibration/active') {
          activeChecks += 1;
          return http.Response.bytes(
            utf8.encode(
              jsonEncode({
                'active': true,
                'session_id': 'calibration-1',
                'prompts': [
                  {
                    'id': 'speech_01',
                    'kind': 'speech',
                    'phrase': 'Привет, Лера',
                    'icon': '👋',
                  },
                ],
                'collected_prompt_ids': <String>[],
              }),
            ),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        expect(request.method, 'POST');
        expect(
          request.url.path,
          '/v1/stt-calibration/calibration-1/samples/speech_01',
        );
        expect(request.bodyBytes, containsAllInOrder(<int>[82, 73, 70, 70]));
        return http.Response('', 204);
      }),
    );

    final calibration = await gateway.getActiveCalibration();
    await gateway.uploadCalibrationSample(
      sessionId: calibration.sessionId!,
      promptId: calibration.prompts.single.id,
      recording: RecordedVoice(
        bytes: Uint8List.fromList(<int>[82, 73, 70, 70]),
        duration: const Duration(seconds: 1),
      ),
    );

    expect(activeChecks, 1);
    expect(calibration.active, isTrue);
    expect(calibration.prompts.single.phrase, 'Привет, Лера');
  });
}
