import 'dart:io';
import 'dart:typed_data';

import 'package:family_ai_mobile/features/voice/voice_reply_cache.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('family-ai-cache-test-');
  });

  tearDown(() async {
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  });

  test('stores, reads and clears a voice reply by conversation', () async {
    final cache = DeviceVoiceReplyCache(rootDirectory: directory);
    final bytes = Uint8List.fromList(<int>[0x52, 0x49, 0x46, 0x46, 1, 2, 3]);

    await cache.write(
      conversationId: 'conversation/1',
      messageId: 'message/1',
      bytes: bytes,
      contentType: 'application/octet-stream',
    );
    final cached = await cache.read(
      conversationId: 'conversation/1',
      messageId: 'message/1',
    );

    expect(cached?.bytes, bytes);
    expect(cached?.contentType, 'audio/wav');

    await cache.clearConversation('conversation/1');

    expect(
      await cache.read(
        conversationId: 'conversation/1',
        messageId: 'message/1',
      ),
      isNull,
    );
  });

  test('removes the oldest files when the size limit is exceeded', () async {
    final cache = DeviceVoiceReplyCache(rootDirectory: directory, maxBytes: 12);
    final bytes = Uint8List.fromList(<int>[0x52, 0x49, 0x46, 0x46, 1, 2, 3]);

    await cache.write(
      conversationId: 'conversation-1',
      messageId: 'message-1',
      bytes: bytes,
      contentType: 'audio/wav',
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await cache.write(
      conversationId: 'conversation-1',
      messageId: 'message-2',
      bytes: bytes,
      contentType: 'audio/wav',
    );

    expect(
      await cache.read(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
      isNull,
    );
    expect(
      await cache.read(
        conversationId: 'conversation-1',
        messageId: 'message-2',
      ),
      isNotNull,
    );
  });
}
