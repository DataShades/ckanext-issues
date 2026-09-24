/**
 * Ticket thread behaviour.
 *
 * Attached to the ticket page wrapper, which htmx never swaps; handlers are
 * delegated from it so they keep working after htmx replaces the thread or a
 * single message.
 */
ckan.module("issues-thread", function ($) {
    return {
        initialize: function () {
            $.proxyAll(this, /_on/);

            this.el.on("click", "[data-issues-toggle-edit]", this._onToggleEdit);
            this.el.on("keydown", "[data-issues-edit-form] textarea", this._onEditKeydown);
            this.el.on("keydown", "form textarea", this._onSubmitShortcut);
            this.el.on("input", "textarea[data-issues-autogrow]", this._onAutogrow);
            // AddMessageView sends this via the HX-Trigger-After-Settle header
            // on success; htmx fires it on the reply form once the new thread
            // is in place and it bubbles up to us.
            this.el.on("issues:message-added", this._onMessageAdded);
        },

        /**
         * Toggle the inline edit form of a message.
         *
         * @param {Event} e
         */
        _onToggleEdit: function (e) {
            var id = $(e.currentTarget).attr("data-issues-toggle-edit");
            var form = this.el.find("#message-edit-form-" + id);

            this._setEditing(id, form.prop("hidden"));
        },

        /**
         * Esc cancels an inline edit.
         *
         * @param {KeyboardEvent} e
         */
        _onEditKeydown: function (e) {
            if (e.key !== "Escape") {
                return;
            }

            e.preventDefault();
            var id = $(e.currentTarget).closest("[data-issues-edit-form]").attr("data-issues-edit-form");
            this._setEditing(id, false);
        },

        /**
         * Ctrl/Cmd+Enter submits the reply or edit form.
         *
         * @param {KeyboardEvent} e
         */
        _onSubmitShortcut: function (e) {
            if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) {
                return;
            }

            e.preventDefault();
            var form = e.currentTarget.form;

            // The submit button is disabled while a request is in flight, but
            // requestSubmit() doesn't care; don't send the same text twice.
            if (!form || form.classList.contains("htmx-request")) {
                return;
            }

            if (form.requestSubmit) {
                form.requestSubmit();
            } else {
                htmx.trigger(form, "submit");
            }
        },

        /**
         * Grow a textarea to fit its content.
         *
         * @param {Event} e
         */
        _onAutogrow: function (e) {
            var textarea = e.currentTarget;
            var borders = textarea.offsetHeight - textarea.clientHeight;

            textarea.style.height = "auto";
            textarea.style.height = textarea.scrollHeight + borders + "px";
        },

        /**
         * Clear the reply form (and any previous error) once the server
         * confirms the message was added, then bring the new message into
         * view.
         */
        _onMessageAdded: function () {
            var form = this.el.find("#reply-form");
            if (form.length) {
                form[0].reset();
                this.el.find("#reply-form-errors").empty();
                this.el.find("#reply-textarea").css("height", "");
            }

            var message = this.el.find(".message-card.is-new");
            if (!message.length) {
                return;
            }

            message[0].scrollIntoView({
                block: "nearest",
                behavior: this._reducedMotion() ? "auto" : "smooth"
            });
            message[0].focus({ preventScroll: true });
        },

        /**
         * Show or hide the inline edit form of a message.
         *
         * @param {string} id message id
         * @param {boolean} editing
         */
        _setEditing: function (id, editing) {
            var content = this.el.find("#message-content-" + id);
            var wrapper = this.el.find("#message-edit-form-" + id);
            var toggle = this.el.find("#message-edit-toggle-" + id);

            if (!content.length || !wrapper.length) {
                return;
            }

            content.prop("hidden", editing);
            wrapper.prop("hidden", !editing);
            toggle.attr("aria-expanded", String(editing));

            if (editing) {
                var textarea = wrapper.find("textarea")[0];
                textarea.focus();
                textarea.setSelectionRange(textarea.value.length, textarea.value.length);
            } else {
                // Drop unsaved changes so reopening starts from the saved text.
                wrapper.find("form")[0].reset();
                wrapper.find("textarea").css("height", "");
                toggle.trigger("focus");
            }
        },

        _reducedMotion: function () {
            return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        }
    };
});
