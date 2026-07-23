import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/gateway_client.dart';
import '../agents/agent.dart';
import '../agents/agent_presentation.dart';
import '../voice/voice_reply_cache.dart';
import '../voice/voice_session.dart';
import 'conversation_models.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    required this.agent,
    required this.gateway,
    this.voiceSession,
    this.voiceReplyCache,
    super.key,
  });

  final Agent agent;
  final GatewayClient gateway;
  final VoiceSession? voiceSession;
  final VoiceReplyCache? voiceReplyCache;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  final List<ConversationMessage> _messages = [];
  String? _conversationId;
  String? _error;
  bool _loading = true;
  bool _sending = false;
  bool _recording = false;
  bool _playing = false;
  String? _replayingMessageId;
  bool _confirmNewConversation = false;
  VoiceSession? _voiceSession;
  VoiceReplyCache? _voiceReplyCache;
  Timer? _recordingTimer;

  VoiceSession get _voice =>
      _voiceSession ??= widget.voiceSession ?? DeviceVoiceSession();
  VoiceReplyCache get _replyCache =>
      _voiceReplyCache ??= widget.voiceReplyCache ?? DeviceVoiceReplyCache();

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    final voiceSession = _voiceSession;
    if (voiceSession != null) {
      unawaited(voiceSession.dispose());
    }
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadHistory() async {
    try {
      final history = await widget.gateway.getLatestConversation(
        widget.agent.id,
      );
      if (!mounted) return;
      setState(() {
        _conversationId = history.conversationId;
        _messages
          ..clear()
          ..addAll(history.messages);
        _loading = false;
      });
      _scrollToBottom();
    } on GatewayException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _send() async {
    final text = _textController.text.trim();
    if (text.isEmpty || _sending) return;
    _textController.clear();
    setState(() {
      _sending = true;
      _error = null;
      _messages.add(
        ConversationMessage(
          id: 'local-${DateTime.now().microsecondsSinceEpoch}',
          role: 'child',
          content: text,
        ),
      );
    });
    _scrollToBottom();

    try {
      final conversationId =
          _conversationId ??
          await widget.gateway.createConversation(widget.agent.id);
      final reply = await widget.gateway.sendTextTurn(conversationId, text);
      if (!mounted) return;
      setState(() {
        _conversationId = conversationId;
        _messages.add(reply);
      });
      _scrollToBottom();
    } on GatewayException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _toggleVoiceRecording() async {
    if (_loading || _sending || _playing) return;
    if (_recording) {
      await _stopAndSendVoice();
      return;
    }

    FocusManager.instance.primaryFocus?.unfocus();
    try {
      await _voice.startRecording();
      if (!mounted) return;
      setState(() {
        _recording = true;
        _error = null;
      });
      _recordingTimer = Timer(const Duration(seconds: 55), _stopAndSendVoice);
    } on VoiceSessionException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Не удалось включить микрофон.');
      }
    }
  }

  Future<void> _stopAndSendVoice() async {
    if (!_recording || _sending) return;
    _recordingTimer?.cancel();
    _recordingTimer = null;
    setState(() {
      _recording = false;
      _sending = true;
      _error = null;
    });

    try {
      final recording = await _voice.stopRecording();
      if (!mounted) return;
      setState(() {
        _messages.add(
          ConversationMessage(
            id: 'local-voice-${DateTime.now().microsecondsSinceEpoch}',
            role: 'child',
            content: '🎙️ Голосовое сообщение',
          ),
        );
      });
      _scrollToBottom();

      final conversationId =
          _conversationId ??
          await widget.gateway.createConversation(widget.agent.id);
      final response = await widget.gateway.sendVoiceTurn(
        conversationId: conversationId,
        audioBytes: recording.bytes,
        filename: recording.filename,
        contentType: recording.contentType,
      );

      ConversationMessage reply = ConversationMessage(
        id:
            response.messageId ??
            'local-reply-${DateTime.now().microsecondsSinceEpoch}',
        role: 'assistant',
        content: '🔊 Голосовой ответ',
      );
      if (response.messageId != null) {
        try {
          reply = await widget.gateway.getMessage(
            conversationId,
            response.messageId!,
          );
        } on GatewayException {
          // The audio response is still useful if message refresh fails.
        }
      }

      if (!mounted) return;
      setState(() {
        _conversationId = conversationId;
        _messages.add(reply);
        _sending = false;
        _playing = true;
      });
      _scrollToBottom();

      try {
        try {
          await _replyCache.write(
            conversationId: conversationId,
            messageId: reply.id,
            bytes: response.audioBytes,
            contentType: response.contentType,
          );
        } catch (_) {
          // Playback remains available even if persistent caching fails.
        }
        await _voice.play(
          response.audioBytes,
          contentType: response.contentType,
        );
      } on VoiceSessionException catch (error) {
        if (mounted) setState(() => _error = error.message);
      } catch (_) {
        if (mounted) {
          setState(() => _error = 'Ответ пришёл, но звук не воспроизвёлся.');
        }
      } finally {
        if (mounted) setState(() => _playing = false);
      }
    } on VoiceSessionException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on GatewayException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted && _sending) setState(() => _sending = false);
    }
  }

  Future<void> _replayVoice(ConversationMessage message) async {
    final conversationId = _conversationId;
    if (conversationId == null ||
        message.isChild ||
        _loading ||
        _sending ||
        _recording ||
        _playing) {
      return;
    }

    setState(() {
      _playing = true;
      _replayingMessageId = message.id;
      _error = null;
    });
    try {
      var audio = await _replyCache.read(
        conversationId: conversationId,
        messageId: message.id,
      );
      if (audio == null) {
        final synthesized = await widget.gateway.synthesizeText(
          conversationId: conversationId,
          text: message.content,
        );
        audio = CachedVoiceReply(
          bytes: synthesized.audioBytes,
          contentType: synthesized.contentType,
        );
        try {
          await _replyCache.write(
            conversationId: conversationId,
            messageId: message.id,
            bytes: audio.bytes,
            contentType: audio.contentType,
          );
        } catch (_) {
          // The freshly synthesized response can still be played.
        }
      }
      await _voice.play(audio.bytes, contentType: audio.contentType);
    } on GatewayException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on VoiceSessionException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Не удалось повторить голосовой ответ.');
      }
    } finally {
      if (mounted) {
        setState(() {
          _playing = false;
          _replayingMessageId = null;
        });
      }
    }
  }

  Future<void> _requestNewConversation() async {
    if (_sending || _recording || _playing) return;
    if (!_confirmNewConversation) {
      setState(() => _confirmNewConversation = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Нажми галочку, чтобы начать новый разговор.'),
        ),
      );
      await Future<void>.delayed(const Duration(seconds: 4));
      if (mounted) setState(() => _confirmNewConversation = false);
      return;
    }

    setState(() {
      _confirmNewConversation = false;
      _sending = true;
      _error = null;
    });
    try {
      final previousConversationId = _conversationId;
      final id = await widget.gateway.createConversation(widget.agent.id);
      if (previousConversationId != null) {
        try {
          await _replyCache.clearConversation(previousConversationId);
        } catch (_) {
          // Cache cleanup must not prevent starting a new conversation.
        }
      }
      if (!mounted) return;
      setState(() {
        _conversationId = id;
        _messages.clear();
      });
    } on GatewayException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _sending = false);
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
              backgroundColor: _recording
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
                  onPressed: _requestNewConversation,
                  tooltip: 'Новый разговор',
                  color: _confirmNewConversation ? Colors.white : null,
                  style: _confirmNewConversation
                      ? IconButton.styleFrom(
                          backgroundColor: const Color(0xFFD87831),
                        )
                      : null,
                  icon: Icon(
                    _confirmNewConversation
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
            Expanded(child: _buildConversation(presentation)),
          if (_error != null && !compactInputMode)
            MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Понятно'),
                ),
              ],
            ),
          _Composer(
            controller: _textController,
            color: presentation.color,
            textEnabled: !_loading && !_sending && !_recording && !_playing,
            voiceEnabled: !_loading && !_sending && !_playing,
            recording: _recording,
            playing: _playing,
            onSend: _send,
            onVoice: _toggleVoiceRecording,
            compact: compactInputMode,
          ),
        ],
      ),
    );
  }

  Widget _buildConversation(AgentPresentation presentation) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_messages.isEmpty) {
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
                      widget.agent.greeting,
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
      controller: _scrollController,
      padding: const EdgeInsets.fromLTRB(14, 18, 14, 24),
      itemCount: _messages.length + (_sending ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == _messages.length) {
          return Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: CircularProgressIndicator(color: presentation.color),
            ),
          );
        }
        return _MessageBubble(
          message: _messages[index],
          presentation: presentation,
          gateway: widget.gateway,
          replaying: _replayingMessageId == _messages[index].id,
          onReplay: _conversationId != null && !_messages[index].isChild
              ? () => _replayVoice(_messages[index])
              : null,
        );
      },
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.message,
    required this.presentation,
    required this.gateway,
    required this.replaying,
    required this.onReplay,
  });

  final ConversationMessage message;
  final AgentPresentation presentation;
  final GatewayClient gateway;
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

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.color,
    required this.textEnabled,
    required this.voiceEnabled,
    required this.recording,
    required this.playing,
    required this.onSend,
    required this.onVoice,
    required this.compact,
  });

  final TextEditingController controller;
  final Color color;
  final bool textEnabled;
  final bool voiceEnabled;
  final bool recording;
  final bool playing;
  final VoidCallback onSend;
  final VoidCallback onVoice;
  final bool compact;

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
              tooltip: recording ? 'Отправить' : 'Сказать',
              style: IconButton.styleFrom(
                backgroundColor: recording ? const Color(0xFFE6534B) : color,
                minimumSize: Size.square(compact ? 48 : 62),
              ),
              icon: Icon(
                recording
                    ? Icons.stop_rounded
                    : playing
                    ? Icons.volume_up_rounded
                    : Icons.mic_rounded,
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
                    hintText: recording
                        ? 'Слушаю…'
                        : playing
                        ? 'Отвечаю…'
                        : 'Напиши сообщение…',
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
            IconButton.filled(
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
