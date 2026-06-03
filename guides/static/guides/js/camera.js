/**
 * IrritecCamera — módulo de cámara para Irritec Tracking
 * Usa MediaDevices.getUserMedia() para acceder a la cámara del dispositivo.
 * Permite sacar múltiples fotos sin cerrar la cámara.
 */
(function () {
  'use strict';

  var stream = null;
  var photoCallback = null;
  var photoCount = 0;

  /* ── Construye el modal en el DOM (se llama una sola vez) ── */
  function buildModal() {
    if (document.getElementById('irritecCameraModal')) return;

    var modal = document.createElement('div');
    modal.id = 'irritecCameraModal';
    modal.style.cssText = [
      'display:none',
      'position:fixed',
      'top:0', 'left:0', 'right:0', 'bottom:0',
      'background:#000',
      'z-index:99999',
      'flex-direction:column',
      '-webkit-overflow-scrolling:touch',
    ].join(';');

    modal.innerHTML =
      '<div id="irCamViewport" style="flex:1;position:relative;overflow:hidden;">' +
        '<video id="irCamVideo" autoplay playsinline muted ' +
               'style="width:100%;height:100%;object-fit:cover;display:block;"></video>' +
        '<div id="irCamFlash" style="position:absolute;inset:0;background:#fff;' +
             'opacity:0;pointer-events:none;transition:opacity 0.12s;"></div>' +
        '<div id="irCamThumbs" style="position:absolute;bottom:10px;left:10px;' +
             'display:flex;gap:6px;flex-wrap:wrap;max-width:70%;"></div>' +
      '</div>' +
      '<div style="background:#111;padding:18px 20px 36px;' +
                  'display:flex;align-items:center;justify-content:space-between;gap:14px;">' +
        '<button id="irCamClose" type="button" ' +
                'style="flex:1;padding:13px 8px;background:#2d7a35;color:#fff;border:none;' +
                       'border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;">' +
          'Listo' +
        '</button>' +
        '<button id="irCamCapture" type="button" ' +
                'style="width:72px;height:72px;border-radius:50%;background:#fff;' +
                       'border:5px solid #2d7a35;font-size:28px;cursor:pointer;' +
                       'flex-shrink:0;display:flex;align-items:center;justify-content:center;">' +
          '&#128247;' +
        '</button>' +
        '<div id="irCamCount" ' +
             'style="flex:1;text-align:right;color:#aaa;font-size:14px;font-weight:600;">' +
          '0 fotos' +
        '</div>' +
      '</div>';

    document.body.appendChild(modal);

    document.getElementById('irCamClose').addEventListener('click', close);
    document.getElementById('irCamCapture').addEventListener('click', capture);
  }

  /* ── Abre la cámara ── */
  function open(onPhoto) {
    photoCallback = onPhoto;
    buildModal();

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      onUnsupported();
      return;
    }

    var constraints = {
      video: { facingMode: { ideal: 'environment' } },
      audio: false
    };

    navigator.mediaDevices.getUserMedia(constraints)
      .then(function (s) {
        stream = s;
        photoCount = 0;
        document.getElementById('irCamCount').textContent = '0 fotos';
        document.getElementById('irCamThumbs').innerHTML = '';

        var video = document.getElementById('irCamVideo');
        video.srcObject = stream;

        var modal = document.getElementById('irritecCameraModal');
        modal.style.display = 'flex';
      })
      .catch(function (err) {
        console.warn('[IrritecCamera] getUserMedia falló:', err.name, err.message);
        onUnsupported();
      });
  }

  /* ── Captura un fotograma ── */
  function capture() {
    var video = document.getElementById('irCamVideo');
    if (!video || !stream) return;

    var canvas = document.createElement('canvas');
    canvas.width  = video.videoWidth  || 1280;
    canvas.height = video.videoHeight || 720;
    canvas.getContext('2d').drawImage(video, 0, 0);

    /* efecto flash */
    var flash = document.getElementById('irCamFlash');
    flash.style.opacity = '0.75';
    setTimeout(function () { flash.style.opacity = '0'; }, 130);

    canvas.toBlob(function (blob) {
      var filename = 'foto_' + Date.now() + '.jpg';
      var file = new File([blob], filename, { type: 'image/jpeg' });

      /* miniatura dentro del modal */
      var thumb = document.createElement('img');
      thumb.src = URL.createObjectURL(blob);
      thumb.style.cssText =
        'width:52px;height:52px;object-fit:cover;border-radius:6px;border:2px solid #2d7a35;';
      document.getElementById('irCamThumbs').appendChild(thumb);

      photoCount++;
      document.getElementById('irCamCount').textContent =
        photoCount + ' foto' + (photoCount !== 1 ? 's' : '');

      if (typeof photoCallback === 'function') {
        photoCallback(file);
      }
    }, 'image/jpeg', 0.88);
  }

  /* ── Cierra la cámara y libera el stream ── */
  function close() {
    if (stream) {
      stream.getTracks().forEach(function (t) { t.stop(); });
      stream = null;
    }
    var modal = document.getElementById('irritecCameraModal');
    if (modal) modal.style.display = 'none';
  }

  /* ── Fallback cuando getUserMedia no está disponible ── */
  function onUnsupported() {
    var fallback = document.getElementById('irCamFallback');
    if (fallback) {
      fallback.click();
    } else {
      alert('Tu navegador no permite acceder a la cámara. Usa la opción Galería.');
    }
  }

  /* ── API pública ── */
  window.IrritecCamera = {
    open: open,
    close: close,
    capture: capture
  };

}());
