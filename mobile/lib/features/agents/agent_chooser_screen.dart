import 'package:flutter/material.dart';

import '../../core/config/server_address.dart';
import '../../core/network/gateway_client.dart';
import '../conversations/chat_screen.dart';
import 'agent.dart';
import 'agent_presentation.dart';

class AgentChooserScreen extends StatefulWidget {
  const AgentChooserScreen({
    required this.gateway,
    required this.serverAddress,
    required this.onChangeServer,
    super.key,
  });

  final GatewayClient gateway;
  final ServerAddress serverAddress;
  final VoidCallback onChangeServer;

  @override
  State<AgentChooserScreen> createState() => _AgentChooserScreenState();
}

class _AgentChooserScreenState extends State<AgentChooserScreen> {
  late Future<List<Agent>> _agents;

  @override
  void initState() {
    super.initState();
    _agents = widget.gateway.getAgents();
  }

  void _reload() => setState(() => _agents = widget.gateway.getAgents());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Клуб любопытных',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            Text('С кем поговорим?', style: TextStyle(fontSize: 13)),
          ],
        ),
        actions: [
          IconButton(
            onPressed: widget.onChangeServer,
            tooltip: 'Изменить сервер',
            icon: const Icon(Icons.dns_rounded),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: FutureBuilder<List<Agent>>(
        future: _agents,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _ConnectionError(
              address: widget.serverAddress.value,
              onRetry: _reload,
              onChangeServer: widget.onChangeServer,
            );
          }
          final agents = snapshot.data ?? const <Agent>[];
          return LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth >= 900
                  ? 4
                  : constraints.maxWidth >= 600
                  ? 3
                  : 2;
              return GridView.builder(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: columns,
                  mainAxisSpacing: 12,
                  crossAxisSpacing: 12,
                  childAspectRatio: constraints.maxWidth < 430 ? 0.68 : 0.74,
                ),
                itemCount: agents.length,
                itemBuilder: (context, index) {
                  final agent = agents[index];
                  return _AgentCard(
                    agent: agent,
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) =>
                            ChatScreen(agent: agent, gateway: widget.gateway),
                      ),
                    ),
                  );
                },
              );
            },
          );
        },
      ),
    );
  }
}

class _AgentCard extends StatelessWidget {
  const _AgentCard({required this.agent, required this.onTap});

  final Agent agent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final presentation = presentationFor(agent.id);
    return Semantics(
      button: true,
      label: '${agent.displayName}. ${agent.description}',
      child: Material(
        color: presentation.softColor,
        borderRadius: BorderRadius.circular(28),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Positioned(
                top: 8,
                left: 0,
                right: 0,
                bottom: 50,
                child: Image.asset(presentation.asset, fit: BoxFit.contain),
              ),
              Positioned(
                left: 10,
                top: 10,
                child: CircleAvatar(
                  radius: 19,
                  backgroundColor: Colors.white.withValues(alpha: 0.88),
                  child: Text(agent.icon, style: const TextStyle(fontSize: 19)),
                ),
              ),
              Align(
                alignment: Alignment.bottomCenter,
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 14,
                  ),
                  color: Colors.white.withValues(alpha: 0.86),
                  child: Text(
                    agent.displayName,
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      fontSize: 16,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ConnectionError extends StatelessWidget {
  const _ConnectionError({
    required this.address,
    required this.onRetry,
    required this.onChangeServer,
  });

  final String address;
  final VoidCallback onRetry;
  final VoidCallback onChangeServer;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.cloud_off_rounded,
              size: 72,
              color: Color(0xFFD87831),
            ),
            const SizedBox(height: 16),
            const Text(
              'Не вижу домашний сервер',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text(address, textAlign: TextAlign.center),
            const SizedBox(height: 20),
            Wrap(
              spacing: 10,
              children: [
                FilledButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Ещё раз'),
                ),
                OutlinedButton.icon(
                  onPressed: onChangeServer,
                  icon: const Icon(Icons.dns_rounded),
                  label: const Text('Другой адрес'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
