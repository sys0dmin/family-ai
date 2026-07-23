import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'core/config/server_address.dart';
import 'core/network/gateway_client.dart';
import 'core/storage/server_address_store.dart';
import 'features/agents/agent_chooser_screen.dart';
import 'features/server/server_setup_screen.dart';

class FamilyAiApp extends StatefulWidget {
  const FamilyAiApp({
    required this.serverAddressStore,
    required this.httpClient,
    super.key,
  });

  final ServerAddressStore serverAddressStore;
  final http.Client httpClient;

  @override
  State<FamilyAiApp> createState() => _FamilyAiAppState();
}

class _FamilyAiAppState extends State<FamilyAiApp> {
  ServerAddress? _serverAddress;
  ServerAddress? _lastServerAddress;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadServerAddress();
  }

  Future<void> _loadServerAddress() async {
    final address = await widget.serverAddressStore.load();
    if (!mounted) return;
    setState(() {
      _serverAddress = address;
      _lastServerAddress = address;
      _loading = false;
    });
  }

  Future<void> _configureServer(ServerAddress address) async {
    final gateway = GatewayClient(
      serverAddress: address,
      httpClient: widget.httpClient,
    );
    await gateway.checkHealth();
    await widget.serverAddressStore.save(address);
    if (!mounted) return;
    setState(() {
      _serverAddress = address;
      _lastServerAddress = address;
    });
  }

  @override
  void dispose() {
    widget.httpClient.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Family AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF356FC0),
          surface: const Color(0xFFFFFDF8),
        ),
        scaffoldBackgroundColor: const Color(0xFFFFFDF8),
        fontFamily: 'sans-serif',
        inputDecorationTheme: const InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.all(Radius.circular(20)),
            borderSide: BorderSide.none,
          ),
        ),
      ),
      home: _buildHome(),
    );
  }

  Widget _buildHome() {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final address = _serverAddress;
    if (address == null) {
      return ServerSetupScreen(
        initialAddress: _lastServerAddress?.value,
        onConnect: _configureServer,
      );
    }
    return AgentChooserScreen(
      gateway: GatewayClient(
        serverAddress: address,
        httpClient: widget.httpClient,
      ),
      serverAddress: address,
      onChangeServer: () => setState(() => _serverAddress = null),
    );
  }
}
