import { startLiveOverlay, stopLiveOverlay } from './live_scan.js';

(() => {
  const form = document.querySelector('#scan-form');
  if (!form) return;

  const input = document.querySelector('#photo');
  const startButton = document.querySelector('#start-camera');
  const captureButton = document.querySelector('#capture-photo');
  const stopButton = document.querySelector('#stop-camera');
  const stage = document.querySelector('#camera-stage');
  const video = document.querySelector('#camera-video');
  const error = document.querySelector('#camera-error');
  const previewWrap = document.querySelector('#photo-preview-wrap');
  const preview = document.querySelector('#photo-preview');
  const name = document.querySelector('#photo-name');
  const ready = document.querySelector('#photo-ready');
  const analyzeButton = document.querySelector('#analyze-button');
  // Live overlay elements (added alongside #camera-video in scan.html).
  // Optional by design: if scan.html hasn't been updated yet, or the
  // browser/venue can't load the live-detection model, everything below
  // this comment quietly no-ops and the camera flow behaves exactly as
  // it always has.
  const liveOverlay = document.querySelector('#live-overlay');
  const liveStatus = document.querySelector('#live-status');
  const liveHint = document.querySelector('#live-hint');
  const qualityPanel = document.querySelector('#camera-quality');
  const qualityTitle = document.querySelector('#camera-quality-title');
  const qualityList = document.querySelector('#camera-quality-list');
  let loading = document.querySelector('#scan-loading');
  if (!loading) {
    // A running Django process may still serve an older cached scan template.
    // Keep photo submission and its loading feedback working in that case.
    loading = document.createElement('div');
    loading.id = 'scan-loading';
    loading.className = 'scan-loading';
    loading.setAttribute('role', 'status');
    loading.setAttribute('aria-live', 'polite');
    loading.hidden = true;
    loading.innerHTML = `
      <div class="scan-loading-inner">
        <span class="eyebrow">Analisis foto</span>
        <h1>Mengenali profil bibirmu...</h1>
        <p class="lead">Foto sedang diproses. Hasilnya bisa kamu periksa sebelum melihat rekomendasi.</p>
        <div class="scan-progress" aria-hidden="true"><span></span></div>
        <ol class="scan-loading-steps">
          <li id="loading-photo" class="is-active"><span class="scan-step-icon">1</span><span>Menyiapkan foto</span><small>Sedang diproses</small></li>
          <li id="loading-face"><span class="scan-step-icon">2</span><span>Mencari wajah dan kontur bibir</span><small>Menunggu</small></li>
          <li id="loading-color"><span class="scan-step-icon">3</span><span>Memperkirakan warna dari foto</span><small>Menunggu</small></li>
        </ol>
      </div>`;
    document.body.append(loading);
  }
  const loadingPhoto = loading.querySelector('#loading-photo');
  const loadingFace = loading.querySelector('#loading-face');
  const tryOnPhotoKey = `formusense_tryon_photo_v1_${document.body.dataset.userId}`;
  let stream = null;
  let previewUrl = null;
  let submitting = false;
  let qualityTimer = null;
  let lightingWarning;
  let lightingCheck = 'pending';
  let faceWarning = null;
  let faceCheck = 'pending';
  let lastQualityDisplay = '';

  const renderQuality = () => {
    if (!qualityPanel || !qualityTitle || !qualityList) return;
    const warnings = [lightingWarning, faceWarning].filter(Boolean);
    const state = warnings.length ? 'warning'
      : lightingCheck === 'ready' && faceCheck === 'ready' ? 'good' : 'checking';
    const title = warnings.length ? 'Periksa foto sebelum mengambilnya'
      : state === 'good' ? 'Kondisi foto terlihat cukup baik' : 'Memeriksa kondisi foto…';
    const messages = warnings.length ? warnings : [
      lightingCheck === 'pending' ? 'Mengecek pencahayaan kamera…'
        : lightingCheck === 'unavailable' ? 'Pencahayaan belum dapat dicek otomatis. Periksa pratinjau sebelum mengambil foto.'
        : faceCheck === 'pending' ? 'Cahaya terlihat cukup. Mengecek posisi wajah…'
          : faceCheck === 'unavailable'
            ? 'Cahaya terlihat cukup. Posisi wajah belum dapat dicek otomatis; periksa pratinjau sendiri.'
            : 'Wajah dan cahaya terlihat cukup. Periksa lagi foto setelah diambil.',
    ];
    const displayKey = JSON.stringify([state, title, messages]);
    if (displayKey === lastQualityDisplay) return;
    lastQualityDisplay = displayKey;
    qualityPanel.dataset.state = state;
    qualityTitle.textContent = title;
    qualityList.replaceChildren(...messages.map((message) => {
      const item = document.createElement('li');
      item.textContent = message;
      return item;
    }));
  };

  // Exposure guidance uses frame-center percentiles instead of cheek color, so
  // naturally deeper skin tones alone do not trigger a low-light warning.
  const exposureCanvas = document.createElement('canvas');
  exposureCanvas.width = 80;
  exposureCanvas.height = 60;
  const exposureContext = exposureCanvas.getContext('2d', { willReadFrequently: true });
  const checkLighting = () => {
    if (!stream || video.readyState < 2) return;
    if (!exposureContext) {
      clearInterval(qualityTimer);
      qualityTimer = null;
      lightingCheck = 'unavailable';
      renderQuality();
      return;
    }
    try {
      exposureContext.drawImage(video, 0, 0, 80, 60);
      const pixels = exposureContext.getImageData(12, 6, 56, 48).data;
      const levels = [];
      let sum = 0;
      let glare = 0;
      for (let i = 0; i < pixels.length; i += 4) {
        const luma = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
        levels.push(luma);
        sum += luma;
        if (luma > 245) glare += 1;
      }
      levels.sort((a, b) => a - b);
      const mean = sum / levels.length;
      const p20 = levels[Math.floor(levels.length * 0.2)];
      const p80 = levels[Math.floor(levels.length * 0.8)];
      lightingWarning = p80 < 75 && mean < 60
        ? 'Tampilan kamera tampak kurang terang. Cari cahaya yang menghadap wajah.'
        : (p20 > 185 && mean > 205) || glare / levels.length > 0.33
          ? 'Tampilan kamera terlalu terang atau silau. Hindari cahaya langsung di wajah.'
          : null;
      lightingCheck = 'ready';
      renderQuality();
    } catch (cause) {
      // A browser that disallows reading frames still permits photo capture.
      clearInterval(qualityTimer);
      qualityTimer = null;
      lightingWarning = null;
      lightingCheck = 'unavailable';
      renderQuality();
    }
  };

  analyzeButton.disabled = true;

  const stopCamera = () => {
    if (qualityTimer) clearInterval(qualityTimer);
    qualityTimer = null;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    stage.hidden = true;
    captureButton.hidden = true;
    stopButton.hidden = true;
    startButton.hidden = false;
    stopLiveOverlay(liveOverlay);
    if (liveStatus) liveStatus.textContent = '';
    if (liveHint) liveHint.textContent = '';
  };

  const showPreview = (fromCamera) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const file = input.files[0];
    previewWrap.hidden = !file;
    analyzeButton.disabled = !file;
    if (!file) {
      previewUrl = null;
      preview.removeAttribute('src');
      return;
    }
    name.textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB`;
    ready.textContent = fromCamera
      ? 'Foto berhasil diambil. Periksa hasilnya, lalu tekan Analisis foto.'
      : 'Foto dipilih. Periksa hasilnya, lalu tekan Analisis foto.';
    previewUrl = URL.createObjectURL(file);
    preview.src = previewUrl;
  };

  const cachePhotoForTryOn = (file) => new Promise((resolve) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(file);
    image.onload = () => {
      try {
        const scale = Math.min(1, 960 / Math.max(image.width, image.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(image.width * scale);
        canvas.height = Math.round(image.height * scale);
        canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
        sessionStorage.setItem(tryOnPhotoKey, canvas.toDataURL('image/jpeg', 0.8));
      } catch (cause) {
        // The scan still works if browser storage is unavailable.
      } finally {
        URL.revokeObjectURL(objectUrl);
        resolve();
      }
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      resolve();
    };
    image.src = objectUrl;
  });

  startButton.addEventListener('click', async () => {
    error.hidden = true;
    if (!navigator.mediaDevices?.getUserMedia) {
      error.textContent = 'Kamera langsung tidak tersedia di browser ini. Coba buka lewat HTTPS atau localhost, atau unggah foto.';
      error.hidden = false;
      return;
    }
    startButton.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } },
      });
      video.srcObject = stream;
      stage.hidden = false;
      await video.play();
      lightingWarning = undefined;
      lightingCheck = 'pending';
      faceWarning = null;
      faceCheck = 'pending';
      lastQualityDisplay = '';
      renderQuality();
      qualityTimer = setInterval(checkLighting, 650);
      checkLighting();
      captureButton.hidden = false;
      stopButton.hidden = false;
      startButton.hidden = true;
      stage.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Live detection is best-effort on top of the camera that just opened
      // successfully above -- if the model/CDN fails, we just hide its own
      // elements and leave the already-working capture flow untouched.
      if (liveOverlay && liveStatus && liveHint) {
        liveOverlay.hidden = false;
        liveStatus.hidden = false;
        liveHint.hidden = false;
        startLiveOverlay(
          { video, overlay: liveOverlay, statusText: liveStatus, hintText: liveHint,
            onFaceQuality: (warning) => {
              faceCheck = 'ready';
              faceWarning = warning;
              renderQuality();
            } },
          () => {
            liveOverlay.hidden = true;
            liveStatus.hidden = true;
            liveHint.hidden = true;
            faceCheck = 'unavailable';
            faceWarning = null;
            renderQuality();
          },
        );
      } else {
        faceCheck = 'unavailable';
        renderQuality();
      }
    } catch (cause) {
      stopCamera();
      error.textContent = cause.name === 'NotAllowedError'
        ? 'Izin kamera ditolak. Izinkan kamera di pengaturan browser atau unggah foto.'
        : 'Kamera tidak dapat dibuka. Periksa apakah sedang dipakai aplikasi lain, atau unggah foto.';
      error.hidden = false;
    } finally {
      startButton.disabled = false;
    }
  });

  captureButton.addEventListener('click', () => {
    if (!stream || !video.videoWidth || !video.videoHeight) return;
    captureButton.disabled = true;
    const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext('2d');
    context.translate(canvas.width, 0);
    context.scale(-1, 1);
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      captureButton.disabled = false;
      if (!blob) {
        error.textContent = 'Foto gagal diambil. Coba lagi atau unggah foto.';
        error.hidden = false;
        return;
      }
      try {
        const file = new File([blob], 'foto-kamera.jpg', { type: 'image/jpeg' });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        showPreview(true);
        stopCamera();
        previewWrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
        analyzeButton.focus({ preventScroll: true });
      } catch (cause) {
        error.textContent = 'Browser tidak dapat memasukkan hasil kamera ke formulir. Coba unggah foto melalui tombol pilih foto.';
        error.hidden = false;
      }
    }, 'image/jpeg', 0.88);
  });

  stopButton.addEventListener('click', stopCamera);
  input.addEventListener('change', () => showPreview(false));
  form.addEventListener('submit', async (event) => {
    if (submitting || !input.files[0]) return;
    event.preventDefault();
    submitting = true;
    stopCamera();
    loading.hidden = false;
    document.body.classList.add('scan-is-loading');
    analyzeButton.textContent = 'Menganalisis foto…';
    analyzeButton.setAttribute('aria-busy', 'true');
    analyzeButton.disabled = true;
    try { await cachePhotoForTryOn(input.files[0]); }
    catch (cause) { /* A storage failure must not block the photo upload. */ }
    if (loadingPhoto) {
      loadingPhoto.classList.remove('is-active');
      loadingPhoto.classList.add('is-done');
      const label = loadingPhoto.querySelector('small');
      if (label) label.textContent = 'Selesai';
    }
    if (loadingFace) {
      loadingFace.classList.add('is-active');
      const label = loadingFace.querySelector('small');
      if (label) label.textContent = 'Sedang diproses';
    }
    analyzeButton.disabled = false;
    form.requestSubmit(analyzeButton);
  });
  window.addEventListener('pageshow', () => {
    loading.hidden = true;
    document.body.classList.remove('scan-is-loading');
    submitting = false;
    analyzeButton.textContent = '3 · Analisis foto';
    analyzeButton.removeAttribute('aria-busy');
    analyzeButton.disabled = !input.files[0];
  });
  document.querySelectorAll('button[name="action"][value="manual"], button[name="action"][value="demo"]')
    .forEach((button) => button.addEventListener('click', () => {
      try { sessionStorage.removeItem(tryOnPhotoKey); } catch (cause) { /* Storage is optional. */ }
    }));
  window.addEventListener('pagehide', () => {
    stopCamera();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
})();
