import 'dart:typed_data';

import 'package:image_picker/image_picker.dart';

enum PhotoSource { camera, gallery }

class PickedPhoto {
  const PickedPhoto({
    required this.bytes,
    required this.filename,
    required this.contentType,
  });

  final Uint8List bytes;
  final String filename;
  final String contentType;
}

class PhotoPickerException implements Exception {
  const PhotoPickerException(this.message);

  final String message;
}

abstract interface class PhotoPicker {
  Future<PickedPhoto?> pick(PhotoSource source, {required int maxBytes});
}

class DevicePhotoPicker implements PhotoPicker {
  DevicePhotoPicker({ImagePicker? imagePicker})
    : _imagePicker = imagePicker ?? ImagePicker();

  final ImagePicker _imagePicker;

  @override
  Future<PickedPhoto?> pick(PhotoSource source, {required int maxBytes}) async {
    final photo = await _imagePicker.pickImage(
      source: source == PhotoSource.camera
          ? ImageSource.camera
          : ImageSource.gallery,
      imageQuality: 88,
      maxWidth: 2048,
      maxHeight: 2048,
    );
    if (photo == null) return null;
    final bytes = await photo.readAsBytes();
    if (bytes.length > maxBytes) {
      throw const PhotoPickerException(
        'Фотография получилась слишком большой. Попробуй другую.',
      );
    }
    return PickedPhoto(
      bytes: bytes,
      filename: photo.name,
      contentType: photo.mimeType ?? _contentTypeFor(photo.name),
    );
  }

  static String _contentTypeFor(String filename) {
    final normalized = filename.toLowerCase();
    if (normalized.endsWith('.png')) return 'image/png';
    if (normalized.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }
}
