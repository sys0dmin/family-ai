import 'package:shared_preferences/shared_preferences.dart';

import '../config/server_address.dart';

abstract interface class ServerAddressStore {
  Future<ServerAddress?> load();

  Future<void> save(ServerAddress address);
}

class SharedPreferencesServerAddressStore implements ServerAddressStore {
  static const _key = 'family_ai_server_address';

  final SharedPreferencesAsync _preferences = SharedPreferencesAsync();

  @override
  Future<ServerAddress?> load() async {
    final value = await _preferences.getString(_key);
    if (value == null) return null;
    try {
      return ServerAddress.parse(value);
    } on ServerAddressFormatException {
      await _preferences.remove(_key);
      return null;
    }
  }

  @override
  Future<void> save(ServerAddress address) {
    return _preferences.setString(_key, address.value);
  }
}
