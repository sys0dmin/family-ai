import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app.dart';
import 'core/storage/server_address_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    FamilyAiApp(
      serverAddressStore: SharedPreferencesServerAddressStore(),
      httpClient: http.Client(),
    ),
  );
}
