import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import 'audio_format.dart';

class VoiceSessionException implements Exception {
  const VoiceSessionException(this.message);

  final String message;

  @override
  String toString() => message;
}

class RecordedVoice {
  const RecordedVoice({
    required this.bytes,
    required this.duration,
    this.filename = 'lera-voice.wav',
    this.contentType = 'audio/wav',
  });

  final Uint8List bytes;
  final Duration duration;
  final String filename;
  final String contentType;
}

abstract interface class VoiceSession {
  Future<void> startRecording();

  Future<RecordedVoice> stopRecording();

  Future<void> cancelRecording();

  Future<void> play(
    Uint8List audioBytes, {
    required String contentType,
    void Function()? onStarted,
  });

  Future<void> stopPlayback();

  Future<void> dispose();
}

class DeviceVoiceSession implements VoiceSession {
  DeviceVoiceSession({AudioRecorder? recorder, AudioPlayer? player})
    : _recorder = recorder ?? AudioRecorder(),
      _player = player ?? AudioPlayer();

  final AudioRecorder _recorder;
  final AudioPlayer _player;
  String? _recordingPath;
  DateTime? _recordingStartedAt;
  String? _playbackPath;
  Completer<void>? _playbackStopped;

  @override
  Future<void> startRecording() async {
    if (!await _recorder.hasPermission()) {
      throw const VoiceSessionException(
        'Разреши приложению использовать микрофон.',
      );
    }

    await stopPlayback();
    final temporaryDirectory = await getTemporaryDirectory();
    final path =
        '${temporaryDirectory.path}${Platform.pathSeparator}'
        'lera-${DateTime.now().microsecondsSinceEpoch}.wav';
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
      path: path,
    );
    _recordingPath = path;
    _recordingStartedAt = DateTime.now();
  }

  @override
  Future<RecordedVoice> stopRecording() async {
    final path = await _recorder.stop() ?? _recordingPath;
    final startedAt = _recordingStartedAt;
    _recordingPath = null;
    _recordingStartedAt = null;
    if (path == null) {
      throw const VoiceSessionException('Запись не получилась.');
    }

    final file = File(path);
    try {
      final bytes = await file.readAsBytes();
      if (bytes.isEmpty) {
        throw const VoiceSessionException('Запись получилась пустой.');
      }
      return RecordedVoice(
        bytes: bytes,
        duration: startedAt == null
            ? Duration.zero
            : DateTime.now().difference(startedAt),
      );
    } finally {
      if (await file.exists()) {
        await file.delete();
      }
    }
  }

  @override
  Future<void> cancelRecording() async {
    await _recorder.cancel();
    final path = _recordingPath;
    _recordingPath = null;
    _recordingStartedAt = null;
    if (path == null) return;
    final file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
  }

  @override
  Future<void> play(
    Uint8List audioBytes, {
    required String contentType,
    void Function()? onStarted,
  }) async {
    await stopPlayback();
    final playableBytes = AudioFormat.normalizeContainer(audioBytes);
    final format = AudioFormat.detect(contentType, playableBytes);
    final temporaryDirectory = await getTemporaryDirectory();
    final file = File(
      '${temporaryDirectory.path}${Platform.pathSeparator}'
      'family-ai-answer-${DateTime.now().microsecondsSinceEpoch}.'
      '${format.extension}',
    );
    _playbackPath = file.path;
    final stopped = Completer<void>();
    _playbackStopped = stopped;

    try {
      await file.writeAsBytes(playableBytes, flush: true);
      final completed = _player.onPlayerComplete.first;
      final started = _player.onPlayerStateChanged.firstWhere(
        (state) => state == PlayerState.playing,
      );
      await _player.play(
        DeviceFileSource(file.path, mimeType: format.mimeType),
      );
      await started.timeout(const Duration(seconds: 5));
      onStarted?.call();
      await Future.any(<Future<void>>[
        completed,
        stopped.future,
      ]).timeout(const Duration(minutes: 2));
    } catch (_) {
      throw VoiceSessionException(
        'Телефон не смог проиграть ответ '
        '(${format.mimeType}, ${playableBytes.length} байт).',
      );
    } finally {
      await _player.stop();
      if (identical(_playbackStopped, stopped)) {
        _playbackStopped = null;
      }
      _playbackPath = null;
      if (await file.exists()) {
        await file.delete();
      }
    }
  }

  @override
  Future<void> stopPlayback() async {
    final stopped = _playbackStopped;
    _playbackStopped = null;
    if (stopped != null && !stopped.isCompleted) {
      stopped.complete();
    }
    await _player.stop();
    final path = _playbackPath;
    _playbackPath = null;
    if (path == null) return;
    final file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
  }

  @override
  Future<void> dispose() async {
    await cancelRecording();
    await _recorder.dispose();
    await _player.dispose();
  }
}
