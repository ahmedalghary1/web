from drf_spectacular.extensions import OpenApiAuthenticationExtension


class DeviceAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "updates.api.DeviceAuthentication"
    name = "DeviceToken"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-Device-Token",
                "description": "Device secret. Also send X-Device-ID from authenticated registration."}
