"""Lookup tables used when upgrading GEDCOM 5.5.1 data to the 7.0 model."""

from __future__ import annotations

#: 5.5.1 LANGUAGE_ID names (and common vendor spellings) mapped to BCP 47 tags.
LANGUAGES: dict[str, str] = {
    "AFRIKAANS": "af", "ALBANIAN": "sq", "ARABIC": "ar", "ARMENIAN": "hy", "BASQUE": "eu",
    "BULGARIAN": "bg", "CATALAN": "ca", "CHINESE": "zh", "CROATIAN": "hr", "CZECH": "cs",
    "DANISH": "da", "DUTCH": "nl", "ENGLISH": "en", "ESPERANTO": "eo", "ESTONIAN": "et",
    "FINNISH": "fi", "FRENCH": "fr", "GALICIAN": "gl", "GERMAN": "de", "GREEK": "el",
    "HEBREW": "he", "HINDI": "hi", "HUNGARIAN": "hu", "ICELANDIC": "is", "INDONESIAN": "id",
    "IRISH": "ga", "ITALIAN": "it", "JAPANESE": "ja", "KOREAN": "ko", "LATIN": "la",
    "LATVIAN": "lv", "LITHUANIAN": "lt", "NAHUATL": "nah", "NORWEGIAN": "no", "PERSIAN": "fa",
    "POLISH": "pl", "PORTUGUESE": "pt", "ROMANIAN": "ro", "RUSSIAN": "ru", "SERBIAN": "sr",
    "SLOVAK": "sk", "SLOVENE": "sl", "SPANISH": "es", "ESPAÑOL": "es", "ESPANOL": "es",
    "SWEDISH": "sv", "TAGALOG": "tl", "THAI": "th", "TURKISH": "tr", "UKRAINIAN": "uk",
    "VIETNAMESE": "vi", "WELSH": "cy", "YIDDISH": "yi",
}

#: 5.5.1 multimedia FORM values (file extensions) mapped to media types.
MEDIA_TYPES: dict[str, str] = {
    "AVI": "video/x-msvideo", "BMP": "image/bmp", "DOC": "application/msword",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "GIF": "image/gif", "HEIC": "image/heic", "HTM": "text/html", "HTML": "text/html",
    "JPEG": "image/jpeg", "JPG": "image/jpeg", "M4A": "audio/mp4", "MOV": "video/quicktime",
    "MP3": "audio/mpeg", "MP4": "video/mp4", "OGG": "audio/ogg", "OLE": "application/x-ole",
    "PCX": "image/x-pcx", "PDF": "application/pdf", "PNG": "image/png", "SVG": "image/svg+xml",
    "TIF": "image/tiff", "TIFF": "image/tiff", "TXT": "text/plain", "WAV": "audio/wav",
    "WEBP": "image/webp", "WMA": "audio/x-ms-wma", "WMV": "video/x-ms-wmv",
}
UNKNOWN_MEDIA_TYPE = "application/octet-stream"

#: Free-text 5.5.1 ``RELA`` / role words (English and Spanish) mapped to 7.0 ``ROLE`` values.
ROLE_WORDS: dict[str, str] = {
    "godparent": "GODP", "godfather": "GODP", "godmother": "GODP", "godparents": "GODP",
    "sponsor": "GODP", "padrino": "GODP", "madrina": "GODP", "padrinos": "GODP",
    "witness": "WITN", "testigo": "WITN", "testiga": "WITN", "testigos": "WITN",
    "father": "FATH", "padre": "FATH", "mother": "MOTH", "madre": "MOTH",
    "parent": "PARENT", "friend": "FRIEND", "amigo": "FRIEND", "amiga": "FRIEND",
    "neighbor": "NGHBR", "neighbour": "NGHBR", "vecino": "NGHBR", "vecina": "NGHBR",
    "clergy": "CLERGY", "priest": "CLERGY", "sacerdote": "CLERGY", "cura": "CLERGY",
    "párroco": "CLERGY", "parroco": "CLERGY", "officiator": "OFFICIATOR",
    "oficiante": "OFFICIATOR", "spouse": "SPOU", "cónyuge": "SPOU", "conyuge": "SPOU",
    "husband": "HUSB", "esposo": "HUSB", "wife": "WIFE", "esposa": "WIFE",
    "child": "CHIL", "hijo": "CHIL", "hija": "CHIL", "twin": "MULTIPLE",
    "gemelo": "MULTIPLE", "gemela": "MULTIPLE", "multiple": "MULTIPLE",
}

PEDIGREE_WORDS: dict[str, str] = {
    "adopted": "ADOPTED", "birth": "BIRTH", "foster": "FOSTER", "sealing": "SEALING",
    "natural": "BIRTH", "biological": "BIRTH", "adoptado": "ADOPTED", "adoptada": "ADOPTED",
}

NAME_TYPE_WORDS: dict[str, str] = {
    "aka": "AKA", "birth": "BIRTH", "immigrant": "IMMIGRANT", "maiden": "MAIDEN",
    "married": "MARRIED", "professional": "PROFESSIONAL", "nickname": "AKA",
}

MEDIUM_WORDS: dict[str, str] = {
    word.lower(): word
    for word in (
        "AUDIO BOOK CARD ELECTRONIC FICHE FILM MAGAZINE MANUSCRIPT MAP NEWSPAPER PHOTO "
        "TOMBSTONE VIDEO"
    ).split()
} | {"photograph": "PHOTO", "foto": "PHOTO", "document": "ELECTRONIC", "libro": "BOOK"}

#: 5.5.1 AGE keywords and their 7.0 equivalents (age, phrase).
AGE_KEYWORDS: dict[str, tuple[str, str]] = {
    "CHILD": ("< 8y", "Child"),
    "INFANT": ("< 1y", "Infant"),
    "STILLBORN": ("0y", "Stillborn"),
}

#: 5.5.1 identifier tags that become ``EXID`` with these registered TYPE URIs.
EXID_TYPES: dict[str, str] = {
    "AFN": "https://gedcom.io/terms/v7/AFN",
    "RFN": "https://gedcom.io/terms/v7/RFN",
    "RIN": "https://gedcom.io/terms/v7/RIN",
}
