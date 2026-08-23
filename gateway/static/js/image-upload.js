export const DEFAULT_IMAGE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024;

function canvasToBlob(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error('IMAGE_PREPARATION_FAILED')),
      'image/jpeg',
      quality
    );
  });
}

export async function preparePhotoForUpload(file, maxBytes) {
  if (file.size <= maxBytes) return file;
  if (typeof createImageBitmap !== 'function') throw new Error('IMAGE_TOO_LARGE');

  const bitmap = await createImageBitmap(file);
  try {
    let scale = Math.min(1, Math.sqrt((maxBytes * 0.82) / file.size));
    let quality = 0.9;
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d');
      if (!context) throw new Error('IMAGE_PREPARATION_FAILED');
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const blob = await canvasToBlob(canvas, quality);
      canvas.width = 1;
      canvas.height = 1;
      if (blob.size <= maxBytes) {
        const stem = (file.name || 'photo').replace(/\.[^.]+$/, '');
        return new File([blob], `${stem}.jpg`, { type: 'image/jpeg' });
      }
      scale *= 0.82;
      quality = Math.max(0.68, quality - 0.05);
    }
  } finally {
    bitmap.close();
  }
  throw new Error('IMAGE_TOO_LARGE');
}

export function photoErrorMessage(error, maxBytes) {
  const limitMiB = Math.max(1, Math.floor(maxBytes / 1048576));
  if (error?.message === 'IMAGE_TOO_LARGE') {
    return `Фотография больше ${limitMiB} МиБ, и уменьшить её не получилось.`;
  }
  if (error?.message === 'IMAGE_UNSUPPORTED') return 'Подойдут фотографии JPEG, PNG или WebP.';
  if (error?.message === 'IMAGE_INVALID') return 'Файл не удалось прочитать как фотографию.';
  return 'Не получилось рассмотреть фотографию. Давай попробуем ещё раз.';
}
