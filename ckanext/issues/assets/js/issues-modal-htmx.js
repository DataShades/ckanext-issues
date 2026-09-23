/**
 * Ticket-creation modal: initialise the Markdown help popover once htmx has
 * loaded the form into the modal.
 */
ckan.module("issues-modal-htmx", function ($) {
    return {
        initialize: function () {
            $.proxyAll(this, /_on/);

            htmx.on("htmx:afterSettle", this._onHTMXafterSettle);
        },

        _onHTMXafterSettle: function (e) {
            if ($.fn.popover !== undefined) {
                $('[data-bs-toggle="popover"]').popover();
            }
        }
    };
});
