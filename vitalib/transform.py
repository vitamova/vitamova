class Transform:
    class Language:
        def __init__ (self, language):
            self.language = language
        def code_to_name(self):
            if self.language == "en":
                return "English"
            elif self.language == "es":
                return "Spanish"
            elif self.language == "fr":
                return "French"
            elif self.language == "de":
                return "German"
            elif self.language == "it":
                return "Italian"
            elif self.language == "ja":
                return "Japanese"
            elif self.language == "ko":
                return "Korean"
            elif self.language == "pt":
                return "Portuguese"
            elif self.language == "ru":
                return "Russian"
            elif self.language == "zh":
                return "Chinese"
            elif self.language == "uk":
                return "Ukrainian"
            else:
                return "Unknown"