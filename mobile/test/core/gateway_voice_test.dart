import 'dart:convert';
import 'dart:typed_data';

import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:family_ai_mobile/core/network/gateway_client.dart';
import 'package:family_ai_mobile/features/voice/voice_session.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('decodes Voice 2.0 NDJSON audio parts', () async {
    final events = <Map<String, dynamic>>[
      {'type': 'started', 'protocol': 'family-ai-voice/2', 'turn_id': 'turn-1'},
      {
        'type': 'message',
        'protocol': 'family-ai-voice/2',
        'message_id': 'message-2',
        'chunk_count': 1,
      },
      {
        'type': 'audio',
        'protocol': 'family-ai-voice/2',
        'index': 0,
        'content_type': 'audio/wav',
        'audio_base64': base64Encode(<int>[1, 2, 3]),
      },
      {'type': 'complete', 'protocol': 'family-ai-voice/2'},
    ];
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        expect(request.url.path, '/v1/voice/conversation-1/turn/stream');
        return http.Response(
          '${events.map(jsonEncode).join('\n')}\n',
          200,
          headers: {
            'content-type': 'application/x-ndjson',
            'x-family-ai-voice-protocol': 'family-ai-voice/2',
          },
        );
      }),
    );

    final decoded = await gateway
        .streamVoiceTurn(
          conversationId: 'conversation-1',
          audioBytes: Uint8List.fromList(<int>[82, 73, 70, 70]),
          filename: 'voice.wav',
          contentType: 'audio/wav',
          recordingDuration: const Duration(seconds: 1),
        )
        .toList();

    expect(decoded, hasLength(4));
    expect(decoded.first.turnId, 'turn-1');
    expect(decoded[1].messageId, 'message-2');
    expect(decoded[2].audioBytes, <int>[1, 2, 3]);
    expect(decoded[2].contentType, 'audio/wav');
  });

  test('sends a WAV voice turn and reads the assistant message id', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/voice/conversation-1/turn');
        expect(
          request.headers['x-request-id'],
          matches(
            RegExp(
              r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
            ),
          ),
        );
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

  test('shows a child-friendly multimodal provider error', () async {
    final gateway = GatewayClient(
      serverAddress: ServerAddress.parse('http://server.local'),
      httpClient: MockClient(
        (_) async => http.Response(
          '{"detail":"Multimodal providers are temporarily unavailable"}',
          502,
        ),
      ),
    );

    await expectLater(
      gateway.sendSpokenImageTurn(
        conversationId: 'conversation-1',
        imageBytes: Uint8List.fromList(<int>[137, 80, 78, 71]),
        imageFilename: 'photo.png',
        imageContentType: 'image/png',
        audioBytes: Uint8List.fromList(<int>[82, 73, 70, 70]),
        audioFilename: 'voice.wav',
        audioContentType: 'audio/wav',
        recordingDuration: const Duration(seconds: 1),
      ),
      throwsA(
        isA<GatewayException>().having(
          (error) => error.message,
          'message',
          'Не получилось подготовить ответ. Давай попробуем ещё раз.',
        ),
      ),
    );
  });

  test('shows child-friendly overload and timeout messages', () async {
    final cases = <(int, String)>[
      (
        429,
        'Я сейчас отвечаю на другой вопрос. Подожди чуточку и попробуй ещё раз.',
      ),
      (
        504,
        'Ответ не успел прийти. Давай немного подождём и попробуем ещё раз.',
      ),
    ];

    for (final testCase in cases) {
      final gateway = GatewayClient(
        serverAddress: ServerAddress.parse('http://server.local'),
        httpClient: MockClient((_) async => http.Response('', testCase.$1)),
      );

      await expectLater(
        gateway
            .streamVoiceTurn(
              conversationId: 'conversation-1',
              audioBytes: Uint8List.fromList(<int>[82, 73, 70, 70]),
              filename: 'voice.wav',
              contentType: 'audio/wav',
              recordingDuration: const Duration(seconds: 1),
            )
            .toList(),
        throwsA(
          isA<GatewayException>().having(
            (error) => error.message,
            'message',
            testCase.$2,
          ),
        ),
      );
    }
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
