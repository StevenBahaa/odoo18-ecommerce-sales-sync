from odoo import api, fields, models,_
from odoo.exceptions import UserError

class EcommerceSallaMapper(models.AbstractModel):
    _name = "ecommerce.salla.mapper"
    _description = "Salla Payload Mapper"

    def _get_event_type(self ,payload):
        """Return the event type from a Salla/mock payload.

        Real order parsing is intentionally deferred to UC-06.
        """

        if not isinstance(payload, dict):
            return False

        return (
            payload.get("event")
            or payload.get("event_type")
            or payload.get("type")
            or False
        )


    def _parse_order_payload(self, payload):
        """Placeholder for UC-06.

        UC-06 will parse Salla/mock order payloads into ecommerce.external.order
        staging records.
        """
        raise UserError(
            _("Salla order payload parsing will be implemented in UC-06.")
        )

    def _parse_authorize_payload(self, payload):
        """Placeholder for UC-15.

        UC-15 will handle app.store.authorize events and token redaction.
        """
        raise UserError(
            _("Salla authorization payload handling will be implemented in UC-15.")
        )
        
