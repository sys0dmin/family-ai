import 'package:family_ai_mobile/core/config/server_address.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ServerAddress', () {
    test('adds http scheme and normalizes trailing slash', () {
      final address = ServerAddress.parse(' 192.168.31.173:8000/ ');

      expect(address.value, 'http://192.168.31.173:8000');
      expect(
        address.resolve('/healthz').toString(),
        'http://192.168.31.173:8000/healthz',
      );
    });

    test('keeps https addresses', () {
      expect(
        ServerAddress.parse('https://family.example').value,
        'https://family.example',
      );
    });

    test('rejects unsupported schemes and paths', () {
      expect(
        () => ServerAddress.parse('ftp://192.168.31.173'),
        throwsA(isA<ServerAddressFormatException>()),
      );
      expect(
        () => ServerAddress.parse('http://192.168.31.173:8000/admin'),
        throwsA(isA<ServerAddressFormatException>()),
      );
    });

    test('rejects credentials, query and fragment', () {
      for (final input in [
        'http://user:pass@server.local',
        'http://server.local?token=value',
        'http://server.local#history',
      ]) {
        expect(
          () => ServerAddress.parse(input),
          throwsA(isA<ServerAddressFormatException>()),
        );
      }
    });
  });
}
