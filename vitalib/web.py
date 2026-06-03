class Web:
    @staticmethod
    def is_mobile(request):
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
        mobile = any(device in user_agent for device in [
            "mobile",
            "android",
            "iphone",
            "ipad",
            "ipod",
            "windows phone",
        ])
        return mobile