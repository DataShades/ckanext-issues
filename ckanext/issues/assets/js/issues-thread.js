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
            // AddMessageView sends this via the HX-Trigger header on success;
            // htmx fires it on the reply form and it bubbles up to us.
            this.el.on("issues:message-added", this._onMessageAdded);
        },

        /**
         * Toggle the inline edit form of a message.
         *
         * @param {Event} e
         */
        _onToggleEdit: function (e) {
            var id = $(e.currentTarget).attr("data-issues-toggle-edit");
            var content = this.el.find("#message-content-" + id);
            var form = this.el.find("#message-edit-form-" + id);

            if (!content.length || !form.length) {
                return;
            }

            var showForm = content.is(":visible");
            content.toggle(!showForm);
            form.toggle(showForm);
        },

        /**
         * Clear the reply form (and any previous error) once the server
         * confirms the message was added.
         */
        _onMessageAdded: function () {
            var form = this.el.find("#reply-form");
            if (!form.length) {
                return;
            }

            form[0].reset();
            this.el.find("#reply-form-errors").empty();
            this.el.find("#reply-textarea").css("height", "auto");
            this.el.find("#reply-char-count").text("0");
        }
    };
});
