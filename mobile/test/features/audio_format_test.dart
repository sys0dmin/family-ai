import 'dart:convert';
import 'dart:typed_data';

import 'package:family_ai_mobile/features/voice/audio_format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Uint8List wav(List<int> samples) {
    final bytes = Uint8List(44 + samples.length);
    bytes.setAll(0, ascii.encode('RIFF'));
    bytes.setAll(8, ascii.encode('WAVE'));
    bytes.setAll(12, ascii.encode('fmt '));
    bytes.setAll(36, ascii.encode('data'));
    bytes.setAll(44, samples);
    final data = ByteData.sublistView(bytes);
    data.setUint32(4, bytes.length - 8, Endian.little);
    data.setUint32(16, 16, Endian.little);
    data.setUint16(20, 1, Endian.little);
    data.setUint16(22, 1, Endian.little);
    data.setUint32(24, 24000, Endian.little);
    data.setUint32(28, 48000, Endian.little);
    data.setUint16(32, 2, Endian.little);
    data.setUint16(34, 16, Endian.little);
    data.setUint32(40, samples.length, Endian.little);
    return bytes;
  }

  test('merges compatible streamed WAV parts for replay cache', () {
    final merged = AudioFormat.mergeWavParts([
      wav(<int>[1, 2]),
      wav(<int>[3, 4, 5, 6]),
    ]);

    expect(merged, isNotNull);
    final data = ByteData.sublistView(merged!);
    expect(data.getUint32(4, Endian.little), merged.length - 8);
    expect(data.getUint32(40, Endian.little), 6);
    expect(merged.sublist(44), <int>[1, 2, 3, 4, 5, 6]);
  });

  test('finalizes streaming WAV sizes for Android playback', () {
    final bytes = Uint8List(48);
    bytes.setAll(0, ascii.encode('RIFF'));
    bytes.setAll(8, ascii.encode('WAVE'));
    bytes.setAll(12, ascii.encode('fmt '));
    bytes.setAll(36, ascii.encode('data'));
    final data = ByteData.sublistView(bytes);
    data.setUint32(4, 0xFFFFFFFF, Endian.little);
    data.setUint32(16, 16, Endian.little);
    data.setUint16(20, 1, Endian.little);
    data.setUint16(22, 1, Endian.little);
    data.setUint32(24, 24000, Endian.little);
    data.setUint32(28, 48000, Endian.little);
    data.setUint16(32, 2, Endian.little);
    data.setUint16(34, 16, Endian.little);
    data.setUint32(40, 0xFFFFFFFF, Endian.little);
    bytes.setAll(44, const <int>[1, 2, 3, 4]);

    final normalized = AudioFormat.normalizeContainer(bytes);
    final normalizedData = ByteData.sublistView(normalized);

    expect(normalizedData.getUint32(4, Endian.little), 40);
    expect(normalizedData.getUint32(40, Endian.little), 4);
    expect(normalized.sublist(44), <int>[1, 2, 3, 4]);
  });

  test('does not copy an already finalized WAV', () {
    final bytes = Uint8List(44);
    bytes.setAll(0, ascii.encode('RIFF'));
    bytes.setAll(8, ascii.encode('WAVE'));
    bytes.setAll(12, ascii.encode('fmt '));
    bytes.setAll(36, ascii.encode('data'));
    final data = ByteData.sublistView(bytes);
    data.setUint32(4, 36, Endian.little);
    data.setUint32(16, 16, Endian.little);
    data.setUint32(40, 0, Endian.little);

    expect(identical(AudioFormat.normalizeContainer(bytes), bytes), isTrue);
  });
}
