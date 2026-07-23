import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/gateway_client.dart';
import '../voice/voice_session.dart';
import 'calibration_models.dart';

class CalibrationScreen extends StatefulWidget {
  const CalibrationScreen({
    required this.gateway,
    required this.calibration,
    this.voiceSession,
    super.key,
  });

  final GatewayClient gateway;
  final ActiveCalibration calibration;
  final VoiceSession? voiceSession;

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  late final VoiceSession _voice = widget.voiceSession ?? DeviceVoiceSession();
  late final Set<String> _collected = {
    ...widget.calibration.collectedPromptIds,
  };
  int _index = 0;
  bool _busy = true;
  bool _recording = false;
  bool _finished = false;
  String? _error;
  Timer? _recordingTimer;

  CalibrationPrompt get _prompt => widget.calibration.prompts[_index];

  @override
  void initState() {
    super.initState();
    _index = widget.calibration.prompts.indexWhere(
      (prompt) => !_collected.contains(prompt.id),
    );
    if (_index < 0) {
      _index = widget.calibration.prompts.length - 1;
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _completeCollectedSession(),
      );
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) => _preparePrompt());
    }
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    unawaited(_voice.dispose());
    super.dispose();
  }

  Future<void> _preparePrompt() async {
    if (!mounted || _finished) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final audio = await widget.gateway.getCalibrationPromptAudio(
        sessionId: widget.calibration.sessionId!,
        promptId: _prompt.id,
      );
      await _voice.play(audio.audioBytes, contentType: audio.contentType);
      if (!mounted) return;
      if (_prompt.isSilence) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
        await _recordSilence();
      } else {
        setState(() => _busy = false);
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = 'Не получилось услышать задание. Нажми ещё раз.';
      });
    }
  }

  Future<void> _completeCollectedSession() async {
    try {
      await widget.gateway.completeCalibration(widget.calibration.sessionId!);
      if (!mounted) return;
      setState(() {
        _finished = true;
        _busy = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = 'Не получилось запустить проверку. Нажми ещё раз.';
      });
    }
  }

  Future<void> _recordSilence() async {
    try {
      await _voice.startRecording();
      if (mounted) setState(() => _recording = true);
      await Future<void>.delayed(const Duration(seconds: 3));
      final recording = await _voice.stopRecording();
      if (mounted) setState(() => _recording = false);
      await _uploadAndAdvance(recording);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _recording = false;
        _error = 'Тихая проверка не записалась. Попробуем ещё раз.';
      });
    }
  }

  Future<void> _toggleSpeechRecording() async {
    if (_busy || _prompt.isSilence) return;
    if (!_recording) {
      try {
        await _voice.startRecording();
        _recordingTimer = Timer(
          const Duration(seconds: 12),
          _stopSpeechRecording,
        );
        if (mounted) setState(() => _recording = true);
      } catch (error) {
        if (mounted) setState(() => _error = error.toString());
      }
      return;
    }
    await _stopSpeechRecording();
  }

  Future<void> _stopSpeechRecording() async {
    if (!_recording) return;
    _recordingTimer?.cancel();
    setState(() {
      _recording = false;
      _busy = true;
      _error = null;
    });
    try {
      final recording = await _voice.stopRecording();
      await _uploadAndAdvance(recording);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = 'Запись не отправилась. Давай повторим.';
      });
    }
  }

  Future<void> _uploadAndAdvance(RecordedVoice recording) async {
    await widget.gateway.uploadCalibrationSample(
      sessionId: widget.calibration.sessionId!,
      promptId: _prompt.id,
      recording: recording,
    );
    _collected.add(_prompt.id);
    final next = widget.calibration.prompts.indexWhere(
      (prompt) => !_collected.contains(prompt.id),
    );
    if (next < 0) {
      await widget.gateway.completeCalibration(widget.calibration.sessionId!);
      if (!mounted) return;
      setState(() {
        _finished = true;
        _busy = false;
      });
      return;
    }
    if (!mounted) return;
    setState(() {
      _index = next;
      _busy = true;
    });
    await _preparePrompt();
  }

  @override
  Widget build(BuildContext context) {
    final total = widget.calibration.prompts.length;
    final completed = _collected.length;
    return Scaffold(
      backgroundColor: const Color(0xFFF2F8FF),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        title: const Text(
          'Настраиваем слух',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: constraints.maxHeight - 36,
                ),
                child: _finished
                    ? _FinishedCalibration(total: total)
                    : Column(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Column(
                            children: [
                              LinearProgressIndicator(
                                value: completed / total,
                                minHeight: 10,
                                borderRadius: BorderRadius.circular(20),
                              ),
                              const SizedBox(height: 24),
                              Text(
                                _prompt.icon,
                                style: const TextStyle(fontSize: 96),
                              ),
                              const SizedBox(height: 12),
                              Text(
                                _prompt.isSilence
                                    ? 'Слушаем тишину'
                                    : _prompt.phrase,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontSize: 24,
                                  fontWeight: FontWeight.w800,
                                  height: 1.25,
                                ),
                              ),
                              const SizedBox(height: 10),
                              Text(
                                _statusText(),
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontSize: 16,
                                  color: Color(0xFF607086),
                                ),
                              ),
                              if (_error != null) ...[
                                const SizedBox(height: 12),
                                Text(
                                  _error!,
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(
                                    color: Color(0xFFC7463B),
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ],
                          ),
                          Padding(
                            padding: const EdgeInsets.only(top: 28),
                            child: Column(
                              children: [
                                if (_error != null)
                                  FilledButton.icon(
                                    onPressed: _collected.length == total
                                        ? _completeCollectedSession
                                        : _preparePrompt,
                                    icon: const Icon(Icons.replay_rounded),
                                    label: const Text('Ещё раз'),
                                  )
                                else
                                  _CalibrationAction(
                                    busy: _busy,
                                    recording: _recording,
                                    silence: _prompt.isSilence,
                                    onPressed: _toggleSpeechRecording,
                                  ),
                                const SizedBox(height: 18),
                                Text(
                                  '${completed + 1} из $total',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFF607086),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
              ),
            );
          },
        ),
      ),
    );
  }

  String _statusText() {
    if (_prompt.isSilence) {
      return _recording ? 'Тихо-тихо…' : 'Сейчас всё произойдёт само';
    }
    if (_busy) return 'Слушаем задание…';
    if (_recording) return 'Говори, а потом нажми ещё раз';
    return 'Нажми микрофон и повтори фразу';
  }
}

class _CalibrationAction extends StatelessWidget {
  const _CalibrationAction({
    required this.busy,
    required this.recording,
    required this.silence,
    required this.onPressed,
  });

  final bool busy;
  final bool recording;
  final bool silence;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 148,
      height: 148,
      child: FilledButton(
        key: const Key('calibration-action'),
        onPressed: busy || silence ? null : onPressed,
        style: FilledButton.styleFrom(
          shape: const CircleBorder(),
          backgroundColor: recording
              ? const Color(0xFFE6534B)
              : const Color(0xFF287FB0),
        ),
        child: busy
            ? const SizedBox(
                width: 42,
                height: 42,
                child: CircularProgressIndicator(color: Colors.white),
              )
            : Icon(
                recording ? Icons.stop_rounded : Icons.mic_rounded,
                size: 68,
              ),
      ),
    );
  }
}

class _FinishedCalibration extends StatelessWidget {
  const _FinishedCalibration({required this.total});

  final int total;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('🎉', style: TextStyle(fontSize: 100)),
          const SizedBox(height: 18),
          const Text(
            'Всё получилось!',
            style: TextStyle(fontSize: 30, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 10),
          Text(
            '$total заданий готовы. Теперь сервер сам настроит слух.',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 17, color: Color(0xFF607086)),
          ),
          const SizedBox(height: 28),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.home_rounded),
            label: const Text('К друзьям'),
          ),
        ],
      ),
    );
  }
}
