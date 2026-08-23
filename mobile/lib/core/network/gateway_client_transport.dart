part of 'gateway_client.dart';

final Random _secureRandom = Random.secure();

const String _appVersion = String.fromEnvironment(
  'FAMILY_AI_APP_VERSION',
  defaultValue: 'development',
);
const String _sourceCommit = String.fromEnvironment(
  'FAMILY_AI_SOURCE_COMMIT',
  defaultValue: 'development',
);

String _newRequestId() {
  final bytes = List<int>.generate(16, (_) => _secureRandom.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes
      .map((value) => value.toRadixString(16).padLeft(2, '0'))
      .join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

Map<String, String> _identityHeaders({bool json = false}) => {
  'X-Family-AI-App-Version': _appVersion,
  'X-Family-AI-App-Commit': _sourceCommit,
  if (json) 'Content-Type': 'application/json',
};

Map<String, String> _traceHeaders({bool json = false}) => {
  ..._identityHeaders(json: json),
  'X-Request-ID': _newRequestId(),
};

extension _GatewayTransportOperations on GatewayClient {
  Future<http.Response> _get(Uri uri) async {
    try {
      final response = await _httpClient
          .get(uri, headers: _identityHeaders())
          .timeout(timeout);
      return _requireSuccess(response);
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось связаться с сервером.');
    }
  }

  Future<http.Response> _postJson(Uri uri, Map<String, dynamic> body) async {
    try {
      final response = await _httpClient
          .post(uri, headers: _traceHeaders(json: true), body: jsonEncode(body))
          .timeout(timeout);
      return _requireSuccess(response);
    } on GatewayException {
      rethrow;
    } catch (_) {
      throw const GatewayException('Не удалось связаться с сервером.');
    }
  }

  http.Response _requireSuccess(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response;
    }
    if (response.statusCode == 409) {
      throw const GatewayException(
        'Этот вопрос уже отправлен. Давай дождёмся ответа.',
      );
    }
    if (response.statusCode == 429) {
      throw const GatewayException(
        'Я сейчас отвечаю на другой вопрос. Подожди чуточку и попробуй ещё раз.',
      );
    }
    if (response.statusCode == 504) {
      throw const GatewayException(
        'Ответ не успел прийти. Давай немного подождём и попробуем ещё раз.',
      );
    }
    throw GatewayException('Сервер ответил с ошибкой ${response.statusCode}.');
  }

  Map<String, dynamic> _decodeObject(http.Response response) {
    try {
      final value = jsonDecode(utf8.decode(response.bodyBytes));
      if (value is Map<String, dynamic>) return value;
    } catch (_) {
      // The caller receives a stable error without leaking response details.
    }
    throw const GatewayException('Сервер вернул непонятный ответ.');
  }
}
