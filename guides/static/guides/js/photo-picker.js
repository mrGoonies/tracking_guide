/**
 * Selector progresivo de fotografías.
 * Mantiene una FileList acumulada en el input con nombre para que FormData y
 * las validaciones Django existentes sigan funcionando sin cambios.
 */
(function () {
    'use strict';

    function fileKey(file) {
        return [file.name, file.size, file.lastModified].join(':');
    }

    function formatSize(bytes) {
        if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function setOutputFiles(input, files) {
        var transfer = new DataTransfer();
        files.forEach(function (file) { transfer.items.add(file); });
        input.files = transfer.files;
    }

    function initPicker(root) {
        var output = root.querySelector('[data-photo-output]');
        var previewList = root.querySelector('[data-photo-previews]');
        var selection = root.querySelector('[data-photo-selection]');
        var count = root.querySelector('[data-photo-count]');
        var maxFiles = Number(root.dataset.maxFiles || 1);
        var files = Array.prototype.slice.call(output.files || []);
        var objectUrls = [];

        function render() {
            objectUrls.forEach(URL.revokeObjectURL);
            objectUrls = [];
            previewList.innerHTML = '';

            files.forEach(function (file, index) {
                var url = URL.createObjectURL(file);
                objectUrls.push(url);

                var item = document.createElement('div');
                item.className = 'photo-preview';

                var image = document.createElement('img');
                image.src = url;
                image.alt = '';

                var info = document.createElement('div');
                info.className = 'photo-preview-info';
                var name = document.createElement('div');
                name.className = 'photo-preview-name';
                name.textContent = file.name;
                var size = document.createElement('div');
                size.className = 'photo-preview-size';
                size.textContent = formatSize(file.size);
                info.appendChild(name);
                info.appendChild(size);

                var remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'photo-remove';
                remove.textContent = 'Quitar';
                remove.setAttribute('aria-label', 'Quitar ' + file.name);
                remove.addEventListener('click', function () {
                    files.splice(index, 1);
                    setOutputFiles(output, files);
                    render();
                    root.querySelector('[data-photo-open="gallery"]').focus();
                });

                item.appendChild(image);
                item.appendChild(info);
                item.appendChild(remove);
                previewList.appendChild(item);
            });

            selection.hidden = files.length === 0;
            count.textContent = files.length === 1
                ? '1 foto seleccionada'
                : files.length + ' fotos seleccionadas';
        }

        function addFiles(incoming) {
            var known = {};
            files.forEach(function (file) { known[fileKey(file)] = true; });
            Array.prototype.forEach.call(incoming, function (file) {
                if (files.length < maxFiles && !known[fileKey(file)]) {
                    files.push(file);
                    known[fileKey(file)] = true;
                }
            });
            setOutputFiles(output, files);
            render();
        }

        root.querySelectorAll('[data-photo-source]').forEach(function (source) {
            source.addEventListener('change', function () {
                addFiles(source.files);
                source.value = '';
            });
        });

        root.querySelectorAll('[data-photo-open]').forEach(function (button) {
            button.addEventListener('click', function () {
                var source = root.querySelector(
                    '[data-photo-source="' + button.dataset.photoOpen + '"]'
                );
                if (source) source.click();
                else output.click();
            });
        });

        output.addEventListener('change', function () {
            files = Array.prototype.slice.call(output.files || []);
            render();
        });
        render();
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof DataTransfer === 'undefined') {
            document.querySelectorAll('[data-photo-picker]').forEach(function (root) {
                root.querySelectorAll('[data-photo-open]').forEach(function (button) {
                    button.addEventListener('click', function () {
                        root.querySelector('[data-photo-output]').click();
                    });
                });
            });
            return;
        }
        document.querySelectorAll('[data-photo-picker]').forEach(initPicker);
    });
}());
