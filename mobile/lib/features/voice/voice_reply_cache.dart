import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

import 'audio_format.dart';

class CachedVoiceReply {
  const CachedVoiceReply({required this.bytes, required this.contentType});

  final Uint8List bytes;
  final String contentType;
}

abstract interface class VoiceReplyCache {
  Future<CachedVoiceReply?> read({
    required String conversationId,
    required String messageId,
  });

  Future<void> write({
    required String conversationId,
    required String messageId,
    required Uint8List bytes,
    required String contentType,
  });

  Future<void> clearConversation(String conversationId);
}

class DeviceVoiceReplyCache implements VoiceReplyCache {
  DeviceVoiceReplyCache({
    Directory? rootDirectory,
    this.maxAge = const Duration(days: 10),
    this.maxBytes = 100 * 1024 * 1024,
  }) : _providedRootDirectory = rootDirectory;

  static const _extensions = <String, String>{
    'wav': 'audio/wav',
    'mp3': 'audio/mpeg',
    'ogg': 'audio/ogg',
    'm4a': 'audio/mp4',
    'audio': 'application/octet-stream',
  };

  final Directory? _providedRootDirectory;
  final Duration maxAge;
  final int maxBytes;

  @override
  Future<CachedVoiceReply?> read({
    required String conversationId,
    required String messageId,
  }) async {
    final directory = await _conversationDirectory(conversationId);
    final safeMessageId = _safePathPart(messageId);
    for (final entry in _extensions.entries) {
      final file = File(
        '${directory.path}${Platform.pathSeparator}'
        '$safeMessageId.${entry.key}',
      );
      if (!await file.exists()) continue;
      final modifiedAt = await file.lastModified();
      if (DateTime.now().difference(modifiedAt) > maxAge) {
        await file.delete();
        return null;
      }
      final bytes = await file.readAsBytes();
      await file.setLastModified(DateTime.now());
      return CachedVoiceReply(bytes: bytes, contentType: entry.value);
    }
    return null;
  }

  @override
  Future<void> write({
    required String conversationId,
    required String messageId,
    required Uint8List bytes,
    required String contentType,
  }) async {
    if (bytes.isEmpty) return;
    final normalizedBytes = AudioFormat.normalizeContainer(bytes);
    final directory = await _conversationDirectory(conversationId);
    await directory.create(recursive: true);
    final format = AudioFormat.detect(contentType, normalizedBytes);
    final target = File(
      '${directory.path}${Platform.pathSeparator}'
      '${_safePathPart(messageId)}.${format.extension}',
    );
    final temporary = File(
      '${target.path}.tmp-${DateTime.now().microsecondsSinceEpoch}',
    );
    await temporary.writeAsBytes(normalizedBytes, flush: true);
    if (await target.exists()) await target.delete();
    await temporary.rename(target.path);
    await _prune();
  }

  @override
  Future<void> clearConversation(String conversationId) async {
    final directory = await _conversationDirectory(conversationId);
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  }

  Future<Directory> _rootDirectory() async {
    final provided = _providedRootDirectory;
    if (provided != null) return provided;
    final supportDirectory = await getApplicationSupportDirectory();
    return Directory(
      '${supportDirectory.path}${Platform.pathSeparator}voice-replies',
    );
  }

  Future<Directory> _conversationDirectory(String conversationId) async {
    final root = await _rootDirectory();
    return Directory(
      '${root.path}${Platform.pathSeparator}${_safePathPart(conversationId)}',
    );
  }

  Future<void> _prune() async {
    final root = await _rootDirectory();
    if (!await root.exists()) return;
    final files = await root
        .list(recursive: true)
        .where((entity) => entity is File)
        .cast<File>()
        .toList();
    final now = DateTime.now();
    final retained = <({File file, DateTime modifiedAt, int size})>[];
    for (final file in files) {
      final modifiedAt = await file.lastModified();
      if (now.difference(modifiedAt) > maxAge) {
        await file.delete();
        continue;
      }
      retained.add((
        file: file,
        modifiedAt: modifiedAt,
        size: await file.length(),
      ));
    }

    retained.sort((left, right) {
      return left.modifiedAt.compareTo(right.modifiedAt);
    });
    var totalBytes = retained.fold<int>(0, (total, item) => total + item.size);
    for (final item in retained) {
      if (totalBytes <= maxBytes) break;
      if (await item.file.exists()) await item.file.delete();
      totalBytes -= item.size;
    }
  }

  String _safePathPart(String value) {
    return base64Url.encode(utf8.encode(value)).replaceAll('=', '');
  }
}
