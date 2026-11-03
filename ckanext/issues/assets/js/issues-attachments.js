/**
 * Attachment picker for the new-ticket modal and the reply form.
 *
 * The native file input is visually hidden behind an "Upload file" label.
 * Picking files again normally replaces the selection; here new picks are
 * added to it, and each file can be removed from the list before sending.
 * The input's FileList is rebuilt through DataTransfer, so the files still
 * go with the form's own (htmx, multipart) submit.
 *
 * Attached next to issues-modal-htmx (modal dialog) and issues-thread
 * (ticket page wrapper): elements htmx never swaps. The forms inside them
 * are swapped, and CKAN before 2.12 doesn't initialise modules in swapped
 * content, so handlers are delegated from the module element.
 *
 * Limits are checked here only to warn early; the server checks them again.
 */
ckan.module("issues-attachments", function ($) {
    var INPUT = "[data-issues-attach-input]";
    var REMOVE = "[data-issues-attach-remove]";

    return {
        initialize: function () {
            $.proxyAll(this, /_on/);

            // Files picked earlier, per input: the browser forgets them on
            // each pick.
            this.kept = new WeakMap();

            this.el.on("change", INPUT, this._onChange);
            this.el.on("click", REMOVE, this._onRemove);
            // form.reset() (the reply form after sending) empties the input
            // but fires no change event. Capture: reset doesn't bubble
            // everywhere.
            this.el[0].addEventListener("reset", this._onReset, true);
        },

        /**
         * Add the newly picked files to the ones kept from earlier picks.
         *
         * @param {Event} e
         */
        _onChange: function (e) {
            var input = e.currentTarget;
            var maxFiles = parseInt(input.getAttribute("data-max-files"), 10) || 0;
            var files = (this.kept.get(input) || []).slice();
            var notice = "";

            Array.prototype.forEach.call(input.files, function (file) {
                var duplicate = files.some(function (other) {
                    return other.name === file.name && other.size === file.size && other.lastModified === file.lastModified;
                });
                if (!duplicate) {
                    files.push(file);
                }
            });

            if (maxFiles && files.length > maxFiles) {
                files = files.slice(0, maxFiles);
                notice = this._("Only the first {n} files were kept.").replace("{n}", maxFiles);
            }

            this._setFiles(input, files);
            this._render(input, notice);
        },

        /**
         * Drop one file from the selection.
         *
         * @param {Event} e
         */
        _onRemove: function (e) {
            var button = e.currentTarget;
            var list = button.closest("[data-issues-attach-list]");
            var input = list && document.getElementById(list.getAttribute("data-issues-attach-list"));
            if (!input) {
                return;
            }

            var index = parseInt(button.getAttribute("data-issues-attach-remove"), 10);
            var files = Array.prototype.slice.call(input.files);
            files.splice(index, 1);

            this._setFiles(input, files);
            this._render(input);

            // The button is gone; keep focus in the control.
            var next = list.querySelector(REMOVE);
            (next || input).focus();
        },

        /**
         * Clear the lists of a form that was reset, once the reset is done.
         *
         * @param {Event} e
         */
        _onReset: function (e) {
            var form = e.target;
            var self = this;

            setTimeout(function () {
                $(form).find(INPUT).each(function () {
                    self.kept.delete(this);
                    self._render(this);
                });
            }, 0);
        },

        _setFiles: function (input, files) {
            var transfer = new DataTransfer();
            files.forEach(function (file) {
                transfer.items.add(file);
            });
            input.files = transfer.files;
            this.kept.set(input, files);
        },

        /**
         * Rebuild the list of picked files that belongs to an input.
         *
         * @param {HTMLInputElement} input
         * @param {string} [notice] message shown under the files
         */
        _render: function (input, notice) {
            var list = document.querySelector('[data-issues-attach-list="' + input.id + '"]');
            if (!list) {
                return;
            }

            var maxSize = parseInt(input.getAttribute("data-max-size"), 10) || 0;
            var _ = this._;
            var formatSize = this._formatSize;
            list.textContent = "";

            Array.prototype.forEach.call(input.files, function (file, index) {
                var item = $('<li class="issues-attach-item">');
                var size = $('<span class="issues-attach-size">').text(formatSize(file.size));

                item.append($('<span class="issues-attach-name">').text(file.name).attr("title", file.name));
                item.append(size);

                if (maxSize && file.size > maxSize) {
                    item.addClass("is-invalid");
                    size.text(size.text() + " · " + _("too large"));
                }

                item.append(
                    $('<button type="button" class="issues-attach-remove">')
                        .attr("data-issues-attach-remove", String(index))
                        .attr("aria-label", _("Remove") + " " + file.name)
                        .html('<i class="fa fa-times" aria-hidden="true"></i>')
                );

                $(list).append(item);
            });

            if (notice) {
                $(list).append($('<li class="issues-attach-notice" role="status">').text(notice));
            }

            list.hidden = !list.children.length;
        },

        _formatSize: function (bytes) {
            var units = ["B", "KB", "MB", "GB"];
            var size = bytes;
            var unit = 0;
            while (size >= 1024 && unit < units.length - 1) {
                size /= 1024;
                unit += 1;
            }
            return (unit === 0 ? size : size.toFixed(1)) + " " + units[unit];
        }
    };
});
