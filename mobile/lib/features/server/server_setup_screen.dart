import 'package:flutter/material.dart';

import '../../core/config/server_address.dart';
import '../../core/network/gateway_client.dart';

class ServerSetupScreen extends StatefulWidget {
  const ServerSetupScreen({
    required this.onConnect,
    this.initialAddress,
    super.key,
  });

  final String? initialAddress;
  final Future<void> Function(ServerAddress address) onConnect;

  @override
  State<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

class _ServerSetupScreenState extends State<ServerSetupScreen> {
  late final TextEditingController _controller;
  bool _connecting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialAddress ?? '');
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (_connecting) return;
    ServerAddress address;
    try {
      address = ServerAddress.parse(_controller.text);
    } on ServerAddressFormatException catch (error) {
      setState(() => _error = error.message);
      return;
    }

    setState(() {
      _connecting = true;
      _error = null;
    });
    try {
      await widget.onConnect(address);
    } on GatewayException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Не удалось проверить сервер.');
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Card(
                elevation: 0,
                color: const Color(0xFFE7F0FD),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(32),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 88,
                        height: 88,
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(
                          Icons.dns_rounded,
                          size: 48,
                          color: Color(0xFF356FC0),
                        ),
                      ),
                      const SizedBox(height: 22),
                      Text(
                        'Где живёт Family AI?',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Введи адрес домашнего Gateway. Приложение проверит его и запомнит.',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      TextField(
                        key: const Key('server-address-field'),
                        controller: _controller,
                        enabled: !_connecting,
                        keyboardType: TextInputType.url,
                        autocorrect: false,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => _connect(),
                        decoration: InputDecoration(
                          labelText: 'Адрес сервера',
                          hintText: '192.168.31.173:8000',
                          prefixIcon: const Icon(Icons.lan_rounded),
                          errorText: _error,
                        ),
                      ),
                      const SizedBox(height: 18),
                      SizedBox(
                        width: double.infinity,
                        height: 56,
                        child: FilledButton.icon(
                          key: const Key('connect-button'),
                          onPressed: _connecting ? null : _connect,
                          icon: _connecting
                              ? const SizedBox.square(
                                  dimension: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.link_rounded),
                          label: Text(
                            _connecting ? 'Проверяю…' : 'Подключиться',
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
