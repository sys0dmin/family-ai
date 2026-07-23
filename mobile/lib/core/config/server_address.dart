class ServerAddressFormatException implements Exception {
  const ServerAddressFormatException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ServerAddress {
  ServerAddress._(this.uri);

  final Uri uri;

  String get value => uri.toString();

  factory ServerAddress.parse(String input) {
    var candidate = input.trim();
    if (candidate.isEmpty) {
      throw const ServerAddressFormatException('Введите адрес сервера.');
    }
    if (!candidate.contains('://')) {
      candidate = 'http://$candidate';
    }

    final uri = Uri.tryParse(candidate);
    if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
      throw const ServerAddressFormatException(
        'Адрес сервера записан неверно.',
      );
    }
    if (uri.scheme != 'http' && uri.scheme != 'https') {
      throw const ServerAddressFormatException(
        'Используйте адрес http:// или https://.',
      );
    }
    if (uri.userInfo.isNotEmpty ||
        uri.query.isNotEmpty ||
        uri.fragment.isNotEmpty) {
      throw const ServerAddressFormatException(
        'В адресе не должно быть логина, параметров или ссылки на раздел.',
      );
    }
    if (uri.path.isNotEmpty && uri.path != '/') {
      throw const ServerAddressFormatException(
        'Укажите адрес сервера без пути.',
      );
    }

    return ServerAddress._(
      Uri(
        scheme: uri.scheme,
        host: uri.host,
        port: uri.hasPort ? uri.port : null,
      ),
    );
  }

  Uri resolve(String path, {Map<String, dynamic>? queryParameters}) {
    return uri.replace(path: path, queryParameters: queryParameters);
  }

  @override
  bool operator ==(Object other) => other is ServerAddress && other.uri == uri;

  @override
  int get hashCode => uri.hashCode;
}
