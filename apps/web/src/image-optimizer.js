const DEFAULT_MAX_EDGE = 2048;
// Leave multipart overhead below the common 1 MB reverse-proxy request limit.
const DEFAULT_TARGET_BYTES = 900 * 1024;
const MIN_EDGE = 1024;

export function containedImageSize(width, height, maximumEdge = DEFAULT_MAX_EDGE) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error("This photo could not be read. Choose another photo and try again.");
  }
  const scale = Math.min(1, maximumEdge / Math.max(width, height));
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("This photo could not be read. Choose a JPEG, PNG, or WebP photo."));
    };
    image.src = url;
  });
}

function encode(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

function optimizedName(name, type) {
  const stem = name.replace(/\.[^.]+$/, "") || "wearo-photo";
  return `${stem}-optimized.${type === "image/webp" ? "webp" : "jpg"}`;
}

export async function optimizeImageForUpload(file, kind, options = {}) {
  if (!(file instanceof Blob)) throw new Error("Choose a photo to upload.");
  const supportedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  if (!supportedTypes.has(file.type)) {
    throw new Error("Choose a JPEG, PNG, or WebP photo.");
  }

  const maximumEdge = options.maximumEdge || DEFAULT_MAX_EDGE;
  const targetBytes = options.targetBytes || DEFAULT_TARGET_BYTES;
  const image = await loadImage(file);
  const sourceWidth = image.naturalWidth || image.width;
  const sourceHeight = image.naturalHeight || image.height;
  let size = containedImageSize(sourceWidth, sourceHeight, maximumEdge);
  if (file.size <= targetBytes && size.width === sourceWidth && size.height === sourceHeight) {
    return file;
  }

  const preserveTransparency = kind === "PRODUCT" && file.type === "image/png";
  const outputType = preserveTransparency ? "image/webp" : "image/jpeg";
  const qualities = preserveTransparency ? [0.96, 0.92, 0.88] : [0.94, 0.91, 0.88, 0.84];
  let best = null;

  while (Math.max(size.width, size.height) >= MIN_EDGE) {
    const canvas = document.createElement("canvas");
    canvas.width = size.width;
    canvas.height = size.height;
    const context = canvas.getContext("2d", { alpha: preserveTransparency });
    if (!context) throw new Error("This browser could not prepare the photo. Try another browser.");
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    if (!preserveTransparency) {
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, size.width, size.height);
    }
    context.drawImage(image, 0, 0, size.width, size.height);

    for (const quality of qualities) {
      const blob = await encode(canvas, outputType, quality);
      if (!blob) continue;
      best = blob;
      if (blob.size <= targetBytes) {
        return new File([blob], optimizedName(file.name, outputType), {
          type: outputType,
          lastModified: file.lastModified,
        });
      }
    }
    if (Math.max(size.width, size.height) === MIN_EDGE) break;
    size = containedImageSize(size.width, size.height, Math.max(MIN_EDGE, Math.round(Math.max(size.width, size.height) * 0.85)));
  }

  if (!best) throw new Error("This photo could not be optimized. Choose another photo and try again.");
  return new File([best], optimizedName(file.name, outputType), {
    type: outputType,
    lastModified: file.lastModified,
  });
}
