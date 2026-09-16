(() => {
  const root = document.querySelector('#tryon');
  if (!root) return;

  const photoKey = 'formusense_tryon_photo_v1';
  const canvas = document.querySelector('#tryon-canvas');
  const context = canvas.getContext('2d');
  const upload = document.querySelector('#tryon-upload');
  const empty = document.querySelector('#tryon-empty');
  const status = document.querySelector('#tryon-status');
  const align = document.querySelector('#tryon-align');
  const download = document.querySelector('#tryon-download');
  const clear = document.querySelector('#tryon-clear');
  const opacity = document.querySelector('#tryon-opacity');
  const opacityValue = document.querySelector('#tryon-opacity-value');
  const shadeButtons = [...document.querySelectorAll('[data-tryon-shade]')];
  const steps = ['sudut kiri bibir', 'titik tertinggi bibir', 'sudut kanan bibir', 'titik terendah bibir'];
  let photo = null;
  let points = [];
  let editing = false;
  let selected = document.querySelector('.tryon-shade.is-selected') || shadeButtons[0];
  let estimatedPoints = null;
  try { estimatedPoints = JSON.parse(document.querySelector('#lip-points-data').textContent); }
  catch (cause) { /* Manual placement remains available. */ }

  const draw = () => {
    if (!photo) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(photo, 0, 0, canvas.width, canvas.height);
    if (points.length === 4) {
      const [left, top, right, bottom] = points;
      const width = right.x - left.x;
      context.save();
      context.beginPath();
      context.moveTo(left.x, left.y);
      context.bezierCurveTo(left.x + width * .22, left.y - canvas.height * .015,
        top.x - width * .16, top.y, top.x, top.y);
      context.bezierCurveTo(top.x + width * .16, top.y,
        right.x - width * .22, right.y - canvas.height * .015, right.x, right.y);
      context.bezierCurveTo(right.x - width * .18, right.y + canvas.height * .012,
        bottom.x + width * .25, bottom.y, bottom.x, bottom.y);
      context.bezierCurveTo(bottom.x - width * .25, bottom.y,
        left.x + width * .18, left.y + canvas.height * .012, left.x, left.y);
      context.closePath();
      context.globalCompositeOperation = 'multiply';
      context.globalAlpha = Number(opacity.value) / 100;
      context.fillStyle = selected.dataset.hex;
      context.fill();
      context.restore();
    }
    if (editing) {
      for (const point of points) {
        context.beginPath();
        context.arc(point.x, point.y, 6, 0, Math.PI * 2);
        context.fillStyle = '#ffffff';
        context.fill();
        context.strokeStyle = '#3159a3';
        context.lineWidth = 2;
        context.stroke();
      }
    }
  };

  const setPhoto = (source, useEstimatedPoints = false) => {
    const image = new Image();
    image.onload = () => {
      const scale = Math.min(1, 960 / Math.max(image.width, image.height));
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      photo = image;
      points = useEstimatedPoints && estimatedPoints
        ? ['left', 'top', 'right', 'bottom'].map((name) => ({
          x: estimatedPoints[name][0] * canvas.width,
          y: estimatedPoints[name][1] * canvas.height,
        }))
        : [];
      editing = points.length !== 4;
      canvas.classList.toggle('is-placing', editing);
      canvas.hidden = false;
      empty.hidden = true;
      align.disabled = false;
      download.disabled = editing;
      clear.disabled = false;
      status.textContent = useEstimatedPoints && estimatedPoints
        ? 'Posisi awal diperkirakan AI dari foto. Tekan “Atur posisi bibir” bila belum pas.'
        : `Klik ${steps[0]} pada foto, lalu titik atas, kanan, dan bawah bibir.`;
      draw();
    };
    image.onerror = () => { status.textContent = 'Foto tidak dapat dibuka. Pilih JPG atau PNG lain.'; };
    image.src = source;
  };

  if (root.dataset.photoScanned === 'true') {
    try {
      const saved = sessionStorage.getItem(photoKey);
      if (saved) setPhoto(saved, true);
    } catch (cause) { /* Local photo upload remains available. */ }
  }

  upload.addEventListener('change', () => {
    const file = upload.files[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      status.textContent = 'Pilih foto JPG atau PNG.';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setPhoto(reader.result);
    reader.onerror = () => { status.textContent = 'Foto tidak dapat dibuka. Pilih JPG atau PNG lain.'; };
    reader.readAsDataURL(file);
  });

  for (const button of shadeButtons) {
    button.addEventListener('click', () => {
      if (selected) selected.classList.remove('is-selected');
      selected = button;
      selected.classList.add('is-selected');
      status.textContent = points.length === 4
        ? `Pratinjau ${button.dataset.name}. Hasil visual dapat berbeda dari produk asli.`
        : `Warna ${button.dataset.name} dipilih. Klik empat titik bibir pada foto untuk menerapkannya.`;
      draw();
    });
  }

  opacity.addEventListener('input', () => {
    opacityValue.value = `${opacity.value}%`;
    draw();
  });

  align.addEventListener('click', () => {
    if (!photo) return;
    points = [];
    editing = true;
    download.disabled = true;
    canvas.classList.add('is-placing');
    status.textContent = `Klik ${steps[0]} pada foto.`;
    draw();
    canvas.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  canvas.addEventListener('pointerdown', (event) => {
    if (!editing) return;
    const bounds = canvas.getBoundingClientRect();
    points.push({
      x: (event.clientX - bounds.left) * canvas.width / bounds.width,
      y: (event.clientY - bounds.top) * canvas.height / bounds.height,
    });
    if (points.length === 4) {
      editing = false;
      download.disabled = false;
      canvas.classList.remove('is-placing');
      status.textContent = `Posisi bibir disesuaikan. Pratinjau shade ${selected.dataset.name} siap.`;
    } else {
      status.textContent = `Sekarang klik ${steps[points.length]} pada foto.`;
    }
    draw();
  });

  download.addEventListener('click', () => {
    if (!photo || points.length !== 4) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'formusense-pratinjau-shade.png';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, 'image/png');
  });

  clear.addEventListener('click', () => {
    photo = null;
    points = [];
    editing = false;
    canvas.hidden = true;
    canvas.classList.remove('is-placing');
    empty.hidden = false;
    upload.value = '';
    align.disabled = true;
    download.disabled = true;
    clear.disabled = true;
    status.textContent = 'Foto dihapus dari pratinjau browser ini.';
    try { sessionStorage.removeItem(photoKey); } catch (cause) { /* Storage is optional. */ }
  });
})();
