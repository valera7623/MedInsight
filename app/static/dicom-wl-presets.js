/**
 * Shared DICOM window/level presets for 2D and 3D viewers.
 * Values match app/services/dicom_volume.py WINDOW_PRESETS (0–255 grayscale).
 */
const DicomWlPresets = (() => {
  const PRESETS = [
    { id: 'default', label: 'Default' },
    { id: 'bone', label: 'Bone' },
    { id: 'lung', label: 'Lung' },
    { id: 'brain', label: 'Brain' },
    { id: 'abdomen', label: 'Abdomen' },
    { id: 'liver', label: 'Liver' },
  ];

  const PRESET_WL = {
    default: { center: 128, width: 256 },
    lung: { center: 90, width: 360 },
    bone: { center: 210, width: 100 },
    brain: { center: 128, width: 72 },
    abdomen: { center: 130, width: 180 },
    liver: { center: 140, width: 110 },
  };

  const DEFAULT_WL = PRESET_WL.default;

  function applyToImageData(imageData, center, width) {
    const data = imageData.data;
    const low = center - width / 2;
    const high = center + width / 2;
    const range = Math.max(high - low, 1);
    for (let i = 0; i < data.length; i += 4) {
      const v = data[i];
      const clipped = v < low ? low : v > high ? high : v;
      const out = Math.round(((clipped - low) / range) * 255);
      data[i] = out;
      data[i + 1] = out;
      data[i + 2] = out;
    }
    return imageData;
  }

  function isDefault(center, width) {
    return center === DEFAULT_WL.center && width === DEFAULT_WL.width;
  }

  return { PRESETS, PRESET_WL, DEFAULT_WL, applyToImageData, isDefault };
})();

window.DicomWlPresets = DicomWlPresets;
