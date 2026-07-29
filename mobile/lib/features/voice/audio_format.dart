import 'dart:typed_data';

class AudioFormat {
  const AudioFormat({required this.extension, required this.mimeType});

  final String extension;
  final String mimeType;

  static Uint8List? mergeWavParts(List<Uint8List> parts) {
    if (parts.isEmpty) return null;
    final parsed = parts.map(_parseWavPart).toList(growable: false);
    if (parsed.any((part) => part == null)) return null;
    final wavParts = parsed.cast<_WavPart>();
    final format = wavParts.first.format;
    if (wavParts.any((part) => !_bytesEqual(part.format, format))) {
      return null;
    }

    final data = BytesBuilder(copy: false);
    for (final part in wavParts) {
      data.add(part.data);
    }
    final joinedData = data.takeBytes();
    final result = Uint8List(wavParts.first.dataOffset + joinedData.length);
    result.setRange(0, wavParts.first.dataOffset, wavParts.first.prefix);
    result.setRange(wavParts.first.dataOffset, result.length, joinedData);
    final sizes = ByteData.sublistView(result);
    sizes.setUint32(4, result.length - 8, Endian.little);
    sizes.setUint32(
      wavParts.first.dataOffset - 4,
      joinedData.length,
      Endian.little,
    );
    return result;
  }

  static Uint8List normalizeContainer(Uint8List bytes) {
    if (!_startsWith(bytes, const <int>[0x52, 0x49, 0x46, 0x46]) ||
        bytes.length < 12 ||
        !_matchesAt(bytes, 8, const <int>[0x57, 0x41, 0x56, 0x45])) {
      return bytes;
    }

    var chunkOffset = 12;
    while (chunkOffset + 8 <= bytes.length) {
      final isData = _matchesAt(bytes, chunkOffset, const <int>[
        0x64,
        0x61,
        0x74,
        0x61,
      ]);
      final chunkSize = ByteData.sublistView(
        bytes,
        chunkOffset + 4,
        chunkOffset + 8,
      ).getUint32(0, Endian.little);
      if (isData) {
        final actualRiffSize = bytes.length - 8;
        final actualDataSize = bytes.length - chunkOffset - 8;
        final currentRiffSize = ByteData.sublistView(
          bytes,
          4,
          8,
        ).getUint32(0, Endian.little);
        if (currentRiffSize == actualRiffSize && chunkSize == actualDataSize) {
          return bytes;
        }

        final normalized = Uint8List.fromList(bytes);
        final normalizedData = ByteData.sublistView(normalized);
        normalizedData.setUint32(4, actualRiffSize, Endian.little);
        normalizedData.setUint32(
          chunkOffset + 4,
          actualDataSize,
          Endian.little,
        );
        return normalized;
      }
      if (chunkSize == 0xFFFFFFFF) return bytes;
      chunkOffset += 8 + chunkSize + (chunkSize.isOdd ? 1 : 0);
    }
    return bytes;
  }

  static AudioFormat detect(String contentType, Uint8List bytes) {
    final declaredMimeType = contentType.split(';').first.trim().toLowerCase();

    if (_startsWith(bytes, const <int>[0x52, 0x49, 0x46, 0x46])) {
      return const AudioFormat(extension: 'wav', mimeType: 'audio/wav');
    }
    if (_startsWith(bytes, const <int>[0x49, 0x44, 0x33]) ||
        (bytes.length >= 2 && bytes[0] == 0xFF && (bytes[1] & 0xE0) == 0xE0)) {
      return const AudioFormat(extension: 'mp3', mimeType: 'audio/mpeg');
    }
    if (_startsWith(bytes, const <int>[0x4F, 0x67, 0x67, 0x53])) {
      return const AudioFormat(extension: 'ogg', mimeType: 'audio/ogg');
    }

    return switch (declaredMimeType) {
      'audio/wav' || 'audio/x-wav' => const AudioFormat(
        extension: 'wav',
        mimeType: 'audio/wav',
      ),
      'audio/mpeg' || 'audio/mp3' => const AudioFormat(
        extension: 'mp3',
        mimeType: 'audio/mpeg',
      ),
      'audio/ogg' => const AudioFormat(extension: 'ogg', mimeType: 'audio/ogg'),
      'audio/mp4' || 'audio/x-m4a' => const AudioFormat(
        extension: 'm4a',
        mimeType: 'audio/mp4',
      ),
      _ => const AudioFormat(
        extension: 'audio',
        mimeType: 'application/octet-stream',
      ),
    };
  }

  static bool _startsWith(Uint8List bytes, List<int> signature) {
    return _matchesAt(bytes, 0, signature);
  }

  static _WavPart? _parseWavPart(Uint8List source) {
    final bytes = normalizeContainer(source);
    if (bytes.length < 12 ||
        !_startsWith(bytes, const <int>[0x52, 0x49, 0x46, 0x46]) ||
        !_matchesAt(bytes, 8, const <int>[0x57, 0x41, 0x56, 0x45])) {
      return null;
    }
    Uint8List? format;
    var chunkOffset = 12;
    while (chunkOffset + 8 <= bytes.length) {
      final chunkSize = ByteData.sublistView(
        bytes,
        chunkOffset + 4,
        chunkOffset + 8,
      ).getUint32(0, Endian.little);
      final payloadOffset = chunkOffset + 8;
      final payloadEnd = payloadOffset + chunkSize;
      if (payloadEnd > bytes.length) return null;
      if (_matchesAt(bytes, chunkOffset, const <int>[0x66, 0x6D, 0x74, 0x20])) {
        format = Uint8List.sublistView(bytes, payloadOffset, payloadEnd);
      }
      if (_matchesAt(bytes, chunkOffset, const <int>[0x64, 0x61, 0x74, 0x61])) {
        if (format == null) return null;
        return _WavPart(
          prefix: Uint8List.sublistView(bytes, 0, payloadOffset),
          dataOffset: payloadOffset,
          format: format,
          data: Uint8List.sublistView(bytes, payloadOffset, payloadEnd),
        );
      }
      chunkOffset = payloadEnd + (chunkSize.isOdd ? 1 : 0);
    }
    return null;
  }

  static bool _bytesEqual(Uint8List left, Uint8List right) {
    if (left.length != right.length) return false;
    for (var index = 0; index < left.length; index += 1) {
      if (left[index] != right[index]) return false;
    }
    return true;
  }

  static bool _matchesAt(Uint8List bytes, int offset, List<int> signature) {
    if (bytes.length < offset + signature.length) return false;
    for (var index = 0; index < signature.length; index += 1) {
      if (bytes[offset + index] != signature[index]) return false;
    }
    return true;
  }
}

class _WavPart {
  const _WavPart({
    required this.prefix,
    required this.dataOffset,
    required this.format,
    required this.data,
  });

  final Uint8List prefix;
  final int dataOffset;
  final Uint8List format;
  final Uint8List data;
}
