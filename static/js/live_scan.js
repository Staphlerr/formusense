/**
 * live_scan.js
 * -------------------------------------------------------------------------
 * Live, client-side face/lip overlay + rough warm/cool hint for the camera
 * step in scan.html. This module does NOT own the camera stream -- your
 * existing camera.js already does that (start-camera/stop-camera/capture-photo).
 * This module only attaches MediaPipe Tasks Vision (WASM, in-browser) to the
 * <video> that camera.js is already playing, and draws on a transparent
 * <canvas> positioned over it. That keeps the two scripts' responsibilities
 * clean: camera.js = stream lifecycle + capture-to-file-input (unchanged),
 * live_scan.js = detection + overlay only.
 *
 * What this gives you:
 *   - A live lip-outline overlay on the camera preview (visual proof the
 *     system is "looking" at the right region before the user commits).
 *   - A rough, explicitly-labeled "perkiraan awal" (initial guess) of
 *     warm/cool, from a simple RGB heuristic sampled at the cheeks.
 *
 * What this deliberately does NOT do:
 *   - It does NOT compute CIELAB or Monk Skin Tone. That precise
 *     measurement only ever runs server-side, once, on the captured frame
 *     (services/color_science.py + services/local_vision.py). The live
 *     hint here is a crude R/G/B proxy for the b-star/a-star axes that
 *     classify_undertone() actually uses, and WILL sometimes disagree with
 *     the final measured result -- expected, and why the hint text always
 *     says "perkiraan awal" and never claims to be the final answer.
 *   - It does NOT touch photo capture/submission at all. camera.js's
 *     captureButton handler is completely unmodified; the file that gets
 *     analyzed server-side is exactly what it already was.
 *
 * Practical demo requirements:
 *   - The MediaPipe WASM runtime + model load from a CDN the first time a
 *     user opens the camera. No internet at the venue -> this feature
 *     fails to initialize. onUnavailable() below is called in that case;
 *     camera.js should just hide the overlay/hint elements and keep
 *     working exactly as it does today (capture does not depend on this
 *     module succeeding).
 *   - If #camera-video is mirrored for display (a typical selfie CSS rule
 *     like `transform: scaleX(-1)`), apply the SAME transform to
 *     #live-overlay in your CSS so the drawn lip outline lines up with
 *     what the user sees. Landmarks here are drawn in the video's raw
 *     (unmirrored) coordinate space, same as camera.js's capture logic
 *     already assumes (see its own translate/scale(-1,1) un-mirror step).
 */

const CDN_BASE = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Same indices as services/local_vision.py's OUTER_LIP contour and its
// cheek sample points (50 / 280), kept small since this is only a live
// *visual* cue, not the measurement itself.
const LIP_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146];
const CHEEK_LEFT = 50;
const CHEEK_RIGHT = 280;
const HINT_INTERVAL_MS = 400; // throttle the text hint so it doesn't flicker every frame

let landmarkerPromise = null; // lazy-loaded once, reused across open/close cycles
let rafId = null;
let lastHintAt = 0;
let runGeneration = 0;

function getLandmarker() {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const { FaceLandmarker, FilesetResolver } = await import(`${CDN_BASE}/vision_bundle.mjs`);
      const filesetResolver = await FilesetResolver.forVisionTasks(`${CDN_BASE}/wasm`);
      return FaceLandmarker.createFromOptions(filesetResolver, {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
        runningMode: "VIDEO",
        numFaces: 1,
      });
    })().catch((error) => {
      landmarkerPromise = null;
      throw error;
    });
  }
  return landmarkerPromise;
}

/**
 * Rough, non-CIELAB warmth heuristic from a sampled patch of skin.
 * Stand-in for classify_undertone()'s a-star/b-star logic, for a one-word live hint only.
 *
 * IMPORTANT: uses RATIOS, not raw channel differences. A raw difference
 * like (r+g)/2 - b grows with overall brightness (more light -> every
 * channel scales up together -> the raw gap between channels grows too),
 * so it falsely reads "more warm" under brighter light even when the
 * actual color (hue) hasn't changed. Dividing by total brightness cancels
 * that out and leaves (approximately) just the hue/chroma signal, which is
 * what "warm/cool" is actually supposed to track.
 */
function roughWarmthHint(r, g, b) {
  const total = r + g + b || 1;
  const yellowBlue = ((r + g) / 2 - b) / total; // + = yellowish/warm-leaning, - = blueish/cool-leaning
  const redGreen = (r - g) / total;
  if (yellowBlue > 0.05 && redGreen > -0.01) return "terlihat warm";
  if (yellowBlue < -0.02) return "terlihat cool";
  return "terlihat netral";
}

// Framing hints are estimates from the detected face outline. They guide
// capture but do not replace the server-side photo quality checks.
function facePositionWarning(landmarks) {
  const xs = landmarks.map((point) => point.x);
  const ys = landmarks.map((point) => point.y);
  const left = Math.min(...xs), right = Math.max(...xs);
  const top = Math.min(...ys), bottom = Math.max(...ys);
  if (left < 0.03 || right > 0.97 || top < 0.03 || bottom > 0.97) {
    return "Sebagian wajah berada di luar bingkai. Geser wajah ke tengah kamera.";
  }
  if (right - left < 0.24 || bottom - top < 0.32) {
    return "Wajah tampak terlalu kecil. Dekatkan sedikit ke kamera.";
  }
  if (Math.abs((left + right) / 2 - 0.5) > 0.2 || Math.abs((top + bottom) / 2 - 0.5) > 0.2) {
    return "Wajah belum di tengah bingkai. Geser posisi kamera atau wajahmu.";
  }
  const lipLeft = landmarks[61], lipRight = landmarks[291];
  if (Math.abs(lipRight.x - lipLeft.x) < 0.07) {
    return "Area bibir tampak kecil. Dekatkan sedikit wajah ke kamera.";
  }
  return null;
}

function samplePixel(ctx, x, y) {
  const d = ctx.getImageData(Math.max(0, x - 2), Math.max(0, y - 2), 4, 4).data;
  let r = 0, g = 0, b = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
  return [r / n, g / n, b / n];
}

/**
 * Starts the live overlay on a <video> that camera.js already has playing.
 * Safe to call every time the camera is opened; the landmarker itself is
 * only loaded once (first call) and reused after.
 *
 * @param {object} el
 * @param {HTMLVideoElement} el.video - camera.js's existing #camera-video, already playing
 * @param {HTMLCanvasElement} el.overlay - transparent canvas positioned exactly over el.video
 * @param {HTMLElement} el.hintText - where "terlihat warm/cool/netral" text goes
 * @param {HTMLElement} el.statusText - where "wajah terdeteksi" / "posisikan wajahmu" goes
 * @param {(warning: string|null) => void} [el.onFaceQuality] - framing guidance for camera.js
 * @param {(error: Error) => void} [onUnavailable] - called if the model can't load;
 *   caller should hide the overlay/hint elements and otherwise change nothing --
 *   camera.js's capture flow works independently of this.
 */
export async function startLiveOverlay(el, onUnavailable) {
  const generation = ++runGeneration;
  lastHintAt = 0;
  let landmarker;
  try {
    landmarker = await getLandmarker();
  } catch (error) {
    console.warn("Live overlay unavailable, camera capture still works normally:", error);
    if (generation === runGeneration && onUnavailable) onUnavailable(error);
    return;
  }
  if (generation !== runGeneration) return;

  // Internal drawing-buffer resolution: native camera pixels, for landmark
  // precision (independent from how big the element is shown on screen).
  el.overlay.width = el.video.videoWidth || 480;
  el.overlay.height = el.video.videoHeight || 360;
  // Displayed (CSS) size: match the video's ACTUAL rendered box exactly
  // (camera-stage video uses object-fit:cover with a max-height, so its
  // rendered size isn't a simple percentage) -- copying clientWidth/Height
  // straight from the live <video> element keeps the overlay pixel-aligned
  // regardless of aspect ratio or container width.
  el.overlay.style.width = `${el.video.clientWidth}px`;
  el.overlay.style.height = `${el.video.clientHeight}px`;
  const overlayCtx = el.overlay.getContext("2d");

  const sampleCanvas = document.createElement("canvas");
  sampleCanvas.width = el.overlay.width;
  sampleCanvas.height = el.overlay.height;
  const sampleCtx = sampleCanvas.getContext("2d", { willReadFrequently: true });

  function drawFrame(timestampMs) {
    if (generation !== runGeneration) return;
    if (el.video.readyState < 2 || el.video.paused || el.video.ended) {
      rafId = requestAnimationFrame(drawFrame);
      return;
    }
    overlayCtx.clearRect(0, 0, el.overlay.width, el.overlay.height);
    sampleCtx.drawImage(el.video, 0, 0, sampleCanvas.width, sampleCanvas.height);

    const result = landmarker.detectForVideo(el.video, timestampMs);
    const landmarks = result.faceLandmarks && result.faceLandmarks[0];

    if (!landmarks) {
      if (el.statusText.textContent !== "Posisikan wajahmu di tengah frame") {
        el.statusText.textContent = "Posisikan wajahmu di tengah frame";
      }
      if (el.hintText.textContent) el.hintText.textContent = "";
      if (timestampMs - lastHintAt > HINT_INTERVAL_MS) {
        lastHintAt = timestampMs;
        el.onFaceQuality?.("Wajah belum terlihat jelas. Hadapkan wajah ke kamera.");
      }
    } else {
      overlayCtx.strokeStyle = "#b9543e";
      overlayCtx.lineWidth = 2;
      overlayCtx.beginPath();
      LIP_OUTER.forEach((idx, i) => {
        const p = landmarks[idx];
        const x = p.x * el.overlay.width;
        const y = p.y * el.overlay.height;
        if (i === 0) overlayCtx.moveTo(x, y); else overlayCtx.lineTo(x, y);
      });
      overlayCtx.closePath();
      overlayCtx.stroke();

      if (timestampMs - lastHintAt > HINT_INTERVAL_MS) {
        lastHintAt = timestampMs;
        const left = landmarks[CHEEK_LEFT];
        const right = landmarks[CHEEK_RIGHT];
        const [r1, g1, b1] = samplePixel(sampleCtx, left.x * sampleCanvas.width, left.y * sampleCanvas.height);
        const [r2, g2, b2] = samplePixel(sampleCtx, right.x * sampleCanvas.width, right.y * sampleCanvas.height);
        const avgR = (r1 + r2) / 2, avgG = (g1 + g2) / 2, avgB = (b1 + b2) / 2;
        const hint = roughWarmthHint(avgR, avgG, avgB);
        // Calibration aid: run `window.FORMUSENSE_DEBUG_WARMTH = true` in the
        // console, then watch these numbers while testing under different
        // lighting / skin tones to pick better thresholds in roughWarmthHint()
        // above. Leave it off (default) for the actual demo -- silent otherwise.
        if (window.FORMUSENSE_DEBUG_WARMTH) {
          const total = avgR + avgG + avgB || 1;
          console.debug("[live_scan] yellowBlue=%s redGreen=%s -> %s",
            (((avgR + avgG) / 2 - avgB) / total).toFixed(3),
            ((avgR - avgG) / total).toFixed(3), hint);
        }
        el.hintText.textContent = `${hint} · perkiraan awal, akan diukur ulang lebih presisi saat kamu ambil foto`;

        if (el.statusText.textContent !== "Wajah terdeteksi") {
          el.statusText.textContent = "Wajah terdeteksi";
        }
        el.onFaceQuality?.(facePositionWarning(landmarks));
      }
    }

    rafId = requestAnimationFrame(drawFrame);
  }

  rafId = requestAnimationFrame(drawFrame);
}

/**
 * Stops the overlay loop and clears the canvas. Does NOT touch the camera
 * stream -- camera.js's stopCamera() still owns that. Safe to call even if
 * startLiveOverlay never successfully started (e.g. model failed to load).
 */
export function stopLiveOverlay(overlay) {
  runGeneration += 1;
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  if (overlay) {
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
  }
}
