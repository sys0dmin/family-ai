import 'package:flutter/material.dart';

import '../agents/agent.dart';
import '../agents/agent_presentation.dart';
import '../voice/voice_reply_cache.dart';
import '../voice/voice_session.dart';
import 'chat_widgets.dart';
import 'conversation_controller.dart';
import 'conversation_gateway.dart';
import 'voice_chat_controller.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    required this.agent,
    required this.gateway,
    this.voiceSession,
    this.voiceReplyCache,
    super.key,
  });

  final Agent agent;
  final ConversationGateway gateway;
  final VoiceSession? voiceSession;
  final VoiceReplyCache? voiceReplyCache;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  late final VoiceReplyCache _replyCache;
  late final ConversationController _conversation;
  late final VoiceChatController _voice;

  @override
  void initState() {
    super.initState();
    _replyCache = widget.voiceReplyCache ?? DeviceVoiceReplyCache();
    _conversation = ConversationController(
      widget.agent,
      widget.gateway,
      _replyCache,
    )..addListener(_onControllerChanged);
    _voice = VoiceChatController(
      widget.gateway,
      _conversation,
      widget.voiceSession ?? DeviceVoiceSession(),
      _replyCache,
    )..addListener(_onControllerChanged);
    _conversation.loadHistory();
  }

  @override
  void dispose() {
    _voice
      ..removeListener(_onControllerChanged)
      ..dispose();
    _conversation
      ..removeListener(_onControllerChanged)
      ..dispose();
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onControllerChanged() {
    if (!mounted) return;
    setState(() {});
    _scrollToBottom();
  }

  Future<void> _sendText() async {
    final text = _textController.text.trim();
    if (text.isEmpty) return;
    _textController.clear();
    await _conversation.sendText(text);
  }

  Future<void> _requestNewConversation() async {
    final created = await _conversation.requestNewConversation();
    if (!created && _conversation.confirmNewConversation && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Нажми галочку, чтобы начать новый разговор.'),
        ),
      );
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final presentation = presentationFor(widget.agent.id);
    final mediaQuery = MediaQuery.of(context);
    final compactInputMode =
        mediaQuery.orientation == Orientation.landscape &&
        mediaQuery.viewInsets.bottom > 0;
    return Scaffold(
      appBar: compactInputMode
          ? null
          : AppBar(
              backgroundColor: _voice.recording
                  ? const Color(0xFFFFE2DE)
                  : presentation.softColor,
              title: Row(
                children: [
                  CircleAvatar(
                    backgroundColor: Colors.white,
                    backgroundImage: AssetImage(presentation.asset),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      widget.agent.displayName,
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                  ),
                ],
              ),
              actions: [
                IconButton(
                  onPressed: _conversation.busy
                      ? null
                      : _requestNewConversation,
                  tooltip: 'Новый разговор',
                  color: _conversation.confirmNewConversation
                      ? Colors.white
                      : null,
                  style: _conversation.confirmNewConversation
                      ? IconButton.styleFrom(
                          backgroundColor: const Color(0xFFD87831),
                        )
                      : null,
                  icon: Icon(
                    _conversation.confirmNewConversation
                        ? Icons.check_rounded
                        : Icons.refresh_rounded,
                  ),
                ),
                const SizedBox(width: 8),
              ],
            ),
      body: Column(
        children: [
          if (compactInputMode)
            const Spacer()
          else
            Expanded(
              child: ChatConversationView(
                agent: widget.agent,
                presentation: presentation,
                gateway: widget.gateway,
                messages: _conversation.messages,
                loading: _conversation.loading,
                waiting:
                    _conversation.sendingText ||
                    _voice.stage == VoiceTurnStage.thinking,
                scrollController: _scrollController,
                replayingMessageId: _voice.replayingMessageId,
                onReplay: _voice.replay,
              ),
            ),
          if (_conversation.error != null && !compactInputMode)
            MaterialBanner(
              content: Text(_conversation.error!),
              actions: [
                TextButton(
                  onPressed: _conversation.clearError,
                  child: const Text('Понятно'),
                ),
              ],
            ),
          ChatComposer(
            controller: _textController,
            color: presentation.color,
            textEnabled: !_conversation.busy && !_voice.active,
            voiceEnabled:
                !_conversation.loading &&
                !_conversation.sendingText &&
                (!_voice.active || _voice.recording),
            stage: _voice.stage,
            onSend: _sendText,
            onVoice: () {
              FocusManager.instance.primaryFocus?.unfocus();
              _voice.toggleRecording();
            },
            onCancelVoice: _voice.cancel,
            compact: compactInputMode,
          ),
        ],
      ),
    );
  }
}
