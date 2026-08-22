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

class _ActivityLaunchButton extends StatelessWidget {
  const _ActivityLaunchButton({required this.enabled, required this.onPressed});

  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
      child: Semantics(
        button: true,
        label: 'Выбрать приключение или занятие',
        child: FilledButton.tonalIcon(
          key: const Key('activity-launch'),
          onPressed: enabled ? onPressed : null,
          icon: const Text('✨', style: TextStyle(fontSize: 28)),
          label: const Text(
            'Приключение',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
          ),
          style: FilledButton.styleFrom(
            minimumSize: const Size(double.infinity, 58),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
            ),
          ),
        ),
      ),
    );
  }
}

class _ActiveActivityCard extends StatelessWidget {
  const _ActiveActivityCard({
    required this.session,
    required this.enabled,
    required this.onStop,
    required this.onLeave,
    required this.onResume,
  });

  final ActivitySession session;
  final bool enabled;
  final VoidCallback onStop;
  final VoidCallback onLeave;
  final VoidCallback onResume;

  @override
  Widget build(BuildContext context) {
    final progress = session.totalSteps == 0
        ? 0.0
        : session.currentStep / session.totalSteps;
    return Container(
      key: const Key('active-activity'),
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3D2),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Text(
            session.currentStepIcon ?? session.icon,
            style: const TextStyle(fontSize: 34),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  session.currentStepTitle ?? session.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                LinearProgressIndicator(
                  value: progress.clamp(0, 1),
                  borderRadius: BorderRadius.circular(8),
                ),
              ],
            ),
          ),
          IconButton.filledTonal(
            onPressed: enabled ? onLeave : null,
            tooltip: 'Просто поговорить',
            icon: const Icon(Icons.chat_bubble_outline_rounded),
          ),
          if (session.isPaused)
            IconButton.filled(
              key: const Key('activity-resume'),
              onPressed: enabled ? onResume : null,
              tooltip: 'Продолжить приключение',
              icon: const Icon(Icons.play_arrow_rounded),
            )
          else
            IconButton.filledTonal(
              onPressed: enabled ? onStop : null,
              tooltip: 'Остановить приключение',
              icon: const Icon(Icons.stop_rounded),
            ),
        ],
      ),
    );
  }
}

class _ActivityPicker extends StatelessWidget {
  const _ActivityPicker({required this.activities});

  final List<ActivitySummary> activities;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 4, 18, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Куда отправимся?',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 14),
            ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * 0.65,
              ),
              child: GridView.builder(
                shrinkWrap: true,
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 220,
                  mainAxisExtent: 190,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                ),
                itemCount: activities.length,
                itemBuilder: (context, index) {
                  final activity = activities[index];
                  return Semantics(
                    button: true,
                    label: activity.title,
                    child: InkWell(
                      key: Key('activity-${activity.id}'),
                      onTap: () => Navigator.pop(context, activity),
                      borderRadius: BorderRadius.circular(24),
                      child: Ink(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF3F0FF),
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              activity.icon,
                              style: const TextStyle(fontSize: 62),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              activity.shortTitle,
                              maxLines: 2,
                              textAlign: TextAlign.center,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 17,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PendingPhotoPreview extends StatelessWidget {
  const _PendingPhotoPreview({required this.bytes});

  final Uint8List bytes;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('pending-photo-preview'),
      height: 112,
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      color: const Color(0xFFFFFDF8),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Image.memory(bytes, fit: BoxFit.cover),
      ),
    );
  }
}

class _PhotoSourceSheet extends StatelessWidget {
  const _PhotoSourceSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 6, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Что покажем?',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: _PhotoSourceButton(
                    key: const Key('photo-source-camera'),
                    icon: Icons.photo_camera_rounded,
                    label: 'Камера',
                    color: const Color(0xFF327BB5),
                    onTap: () => Navigator.pop(context, PhotoSource.camera),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: _PhotoSourceButton(
                    key: const Key('photo-source-gallery'),
                    icon: Icons.photo_library_rounded,
                    label: 'Галерея',
                    color: const Color(0xFF5A8F62),
                    onTap: () => Navigator.pop(context, PhotoSource.gallery),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PhotoSourceButton extends StatelessWidget {
  const _PhotoSourceButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    super.key,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(24),
        child: Ink(
          height: 138,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: color.withValues(alpha: 0.35), width: 2),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 64, color: color),
              const SizedBox(height: 8),
              Text(
                label,
                style: TextStyle(
                  color: color,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
