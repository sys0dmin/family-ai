import 'package:flutter/material.dart';

import '../agents/agent.dart';
import '../agents/agent_presentation.dart';
import 'conversation_gateway.dart';
import 'conversation_models.dart';
import 'voice_chat_controller.dart';

class ChatConversationView extends StatelessWidget {
  const ChatConversationView({
    required this.agent,
    required this.presentation,
    required this.gateway,
    required this.messages,
    required this.loading,
    required this.waiting,
    required this.scrollController,
    required this.replayingMessageId,
    required this.onReplay,
    super.key,
  });

  final Agent agent;
  final AgentPresentation presentation;
  final ConversationGateway gateway;
  final List<ConversationMessage> messages;
  final bool loading;
  final bool waiting;
  final ScrollController scrollController;
  final String? replayingMessageId;
  final ValueChanged<ConversationMessage> onReplay;

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (messages.isEmpty) {
      return LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxHeight < 420;
          final greetingMaxHeight = (constraints.maxHeight * 0.28).clamp(
            48.0,
            110.0,
          );
          return Padding(
            padding: EdgeInsets.all(compact ? 12 : 28),
            child: Column(
              children: [
                Expanded(
                  child: Center(
                    child: Image.asset(presentation.asset, fit: BoxFit.contain),
                  ),
                ),
                SizedBox(height: compact ? 6 : 10),
                ConstrainedBox(
                  constraints: BoxConstraints(maxHeight: greetingMaxHeight),
                  child: SingleChildScrollView(
                    child: Text(
                      agent.greeting,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 17),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      );
    }
    return ListView.builder(
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(14, 18, 14, 24),
      itemCount: messages.length + (waiting ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == messages.length) {
          return Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: CircularProgressIndicator(color: presentation.color),
            ),
          );
        }
        final message = messages[index];
        return ChatMessageBubble(
          message: message,
          presentation: presentation,
          gateway: gateway,
          replaying: replayingMessageId == message.id,
          onReplay: message.isChild ? null : () => onReplay(message),
        );
      },
    );
  }
}

class ChatMessageBubble extends StatelessWidget {
  const ChatMessageBubble({
    required this.message,
    required this.presentation,
    required this.gateway,
    required this.replaying,
    required this.onReplay,
    super.key,
  });

  final ConversationMessage message;
  final AgentPresentation presentation;
  final ConversationGateway gateway;
  final bool replaying;
  final VoidCallback? onReplay;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: message.isChild ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 640),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: message.isChild
              ? const Color(0xFFF0EEE8)
              : presentation.softColor,
          borderRadius: BorderRadius.circular(20).copyWith(
            bottomRight: message.isChild ? const Radius.circular(5) : null,
            bottomLeft: message.isChild ? null : const Radius.circular(5),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              message.content,
              style: const TextStyle(fontSize: 16, height: 1.4),
            ),
            if (!message.isChild && onReplay != null) ...[
              const SizedBox(height: 8),
              IconButton.filledTonal(
                key: Key('replay-${message.id}'),
                onPressed: replaying ? null : onReplay,
                tooltip: 'Повторить голосом',
                icon: replaying
                    ? const SizedBox.square(
                        dimension: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.volume_up_rounded),
              ),
            ],
            for (final media in message.media.where(
              (item) => item.mediaType == 'image',
            )) ...[
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: Image.network(
                  gateway.resolveMediaUrl(media.contentUrl).toString(),
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) => const SizedBox.shrink(),
                ),
              ),
              if (media.attribution.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 5),
                  child: Text(
                    media.attribution,
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class ChatComposer extends StatelessWidget {
  const ChatComposer({
    required this.controller,
    required this.color,
    required this.textEnabled,
    required this.voiceEnabled,
    required this.stage,
    required this.onSend,
    required this.onVoice,
    required this.onCancelVoice,
    required this.compact,
    super.key,
  });

  final TextEditingController controller;
  final Color color;
  final bool textEnabled;
  final bool voiceEnabled;
  final VoiceTurnStage stage;
  final VoidCallback onSend;
  final VoidCallback onVoice;
  final VoidCallback onCancelVoice;
  final bool compact;

  bool get _recording => stage == VoiceTurnStage.listening;
  bool get _voiceActive => switch (stage) {
    VoiceTurnStage.listening ||
    VoiceTurnStage.understanding ||
    VoiceTurnStage.thinking ||
    VoiceTurnStage.speaking => true,
    _ => false,
  };

  String get _hint => switch (stage) {
    VoiceTurnStage.listening => 'Слушаю…',
    VoiceTurnStage.understanding => 'Понимаю…',
    VoiceTurnStage.thinking => 'Думаю…',
    VoiceTurnStage.speaking => 'Отвечаю…',
    VoiceTurnStage.error => 'Попробуем ещё раз',
    _ => 'Напиши сообщение…',
  };

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: compact
            ? const EdgeInsets.symmetric(horizontal: 8, vertical: 4)
            : const EdgeInsets.fromLTRB(12, 10, 12, 12),
        decoration: const BoxDecoration(
          color: Color(0xFFFFFDF8),
          border: Border(top: BorderSide(color: Color(0xFFE7E3DB))),
        ),
        child: Row(
          children: [
            IconButton.filled(
              key: const Key('voice-button'),
              onPressed: voiceEnabled ? onVoice : null,
              tooltip: _recording ? 'Отправить' : 'Сказать',
              style: IconButton.styleFrom(
                backgroundColor: _recording ? const Color(0xFFE6534B) : color,
                minimumSize: Size.square(compact ? 48 : 62),
              ),
              icon: Icon(
                _recording ? Icons.stop_rounded : Icons.mic_rounded,
                size: compact ? 26 : 32,
              ),
            ),
            SizedBox(width: compact ? 6 : 10),
            Expanded(
              child: SizedBox(
                height: compact ? 48 : null,
                child: TextField(
                  controller: controller,
                  enabled: textEnabled,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => onSend(),
                  decoration: InputDecoration(
                    hintText: _hint,
                    isDense: compact,
                    contentPadding: compact
                        ? const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 12,
                          )
                        : null,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            if (_voiceActive)
              IconButton.filled(
                key: const Key('cancel-voice-turn'),
                onPressed: onCancelVoice,
                tooltip: 'Отменить',
                style: IconButton.styleFrom(
                  backgroundColor: const Color(0xFFE6534B),
                  minimumSize: Size.square(compact ? 48 : 54),
                ),
                icon: const Icon(Icons.close_rounded),
              )
            else
              IconButton.filled(
                key: const Key('send-text-button'),
                onPressed: textEnabled ? onSend : null,
                style: IconButton.styleFrom(
                  backgroundColor: color,
                  minimumSize: Size.square(compact ? 48 : 54),
                ),
                icon: const Icon(Icons.arrow_upward_rounded),
              ),
          ],
        ),
      ),
    );
  }
}
