import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../agents/agent.dart';
import '../agents/agent_presentation.dart';
import '../voice/voice_reply_cache.dart';
import '../voice/voice_session.dart';
import 'activity_models.dart';
import 'chat_widgets.dart';
import 'conversation_controller.dart';
import 'conversation_gateway.dart';
import 'photo_picker.dart';
import 'voice_chat_controller.dart';

part 'chat_screen_widgets.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    required this.agent,
    required this.gateway,
    this.voiceSession,
    this.voiceReplyCache,
    this.photoPicker,
    super.key,
  });

  final Agent agent;
  final ConversationGateway gateway;
  final VoiceSession? voiceSession;
  final VoiceReplyCache? voiceReplyCache;
  final PhotoPicker? photoPicker;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  late final VoiceReplyCache _replyCache;
  late final ConversationController _conversation;
  late final VoiceChatController _voice;
  late final PhotoPicker _photoPicker;

  @override
  void initState() {
    super.initState();
    _replyCache = widget.voiceReplyCache ?? DeviceVoiceReplyCache();
    _photoPicker = widget.photoPicker ?? DevicePhotoPicker();
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

  Future<void> _startSpokenImageQuestion() async {
    FocusManager.instance.primaryFocus?.unfocus();
    final source = await showModalBottomSheet<PhotoSource>(
      context: context,
      showDragHandle: true,
      builder: (context) => const _PhotoSourceSheet(),
    );
    if (source == null || !mounted) return;
    try {
      final photo = await _photoPicker.pick(
        source,
        maxBytes: widget.agent.imageUploadMaxBytes ?? 10 * 1024 * 1024,
      );
      if (photo == null || !mounted) return;
      _textController.clear();
      await _voice.startSpokenImageQuestion(photo);
    } on PhotoPickerException catch (error) {
      _conversation.setError(error.message);
    } catch (_) {
      _conversation.setError('Не удалось открыть камеру или фотографию.');
    }
  }

  Future<void> _showActivities() async {
    final activity = await showModalBottomSheet<ActivitySummary>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) =>
          _ActivityPicker(activities: _conversation.activities),
    );
    if (activity == null || !mounted) return;
    final message = await _conversation.startActivity(activity.id);
    if (message != null) await _voice.replay(message);
  }

  Future<void> _stopActivity({required bool leave}) async {
    final message = await _conversation.stopActivity(leave: leave);
    if (message != null) await _voice.replay(message);
  }

  Future<void> _resumeActivity() async {
    final message = await _conversation.resumeActivity();
    if (message != null) await _voice.replay(message);
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
                    child: ClipOval(
                      child: SizedBox.expand(
                        child: Transform.scale(
                          scale: presentation.avatarScale,
                          alignment: presentation.avatarAlignment,
                          child: Image.asset(
                            presentation.asset,
                            key: const Key('agent-avatar-image'),
                            fit: BoxFit.cover,
                            alignment: presentation.avatarAlignment,
                          ),
                        ),
                      ),
                    ),
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
          else ...[
            if (_conversation.activitySession?.isInProgress == true)
              _ActiveActivityCard(
                session: _conversation.activitySession!,
                enabled: !_conversation.busy && !_voice.active,
                onStop: () => _stopActivity(leave: false),
                onLeave: () => _stopActivity(leave: true),
                onResume: _resumeActivity,
              )
            else if (_conversation.activities.isNotEmpty)
              _ActivityLaunchButton(
                enabled: !_conversation.busy && !_voice.active,
                onPressed: _showActivities,
              ),
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
          ],
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
          if (_voice.pendingPhotoBytes != null && !compactInputMode)
            _PendingPhotoPreview(bytes: _voice.pendingPhotoBytes!),
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
            onPhoto:
                widget.agent.supportsSpokenImageQuestion ||
                    widget.agent.supportsImageUpload
                ? _startSpokenImageQuestion
                : null,
            compact: compactInputMode,
          ),
        ],
      ),
    );
  }
}
