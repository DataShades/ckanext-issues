/**
 * Ticket-creation modal: show a loading placeholder while htmx fetches the
 * form, and initialise the Markdown help popover once it has loaded.
 */
ckan.module("issues-modal-htmx", function ($) {
    return {
        initialize: function () {
            $.proxyAll(this, /_on/);

            this.body = this.el.find(".issues-ticket-modal-body");
            this.placeholder = this.body.html();

            // The trigger's hx-get fires on the same click that opens the
            // modal, so reset here to hide the previous form/response until
            // the fresh form arrives.
            this.el[0].closest(".modal").addEventListener("show.bs.modal", this._onModalShow);
            htmx.on("htmx:afterSettle", this._onHTMXafterSettle);
        },

        _onModalShow: function () {
            this.body.html(this.placeholder);
        },

        _onHTMXafterSettle: function (e) {
            if ($.fn.popover !== undefined) {
                $('[data-bs-toggle="popover"]').popover();
            }
        }
    };
});
